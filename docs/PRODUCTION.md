# Production kurulumu ve işletim

Bu uygulamanın kodu güvenlik ve işletim kontrolleriyle hazırlandı. AWS hesabı, alan adı, network, gerçek secret'lar ve trafik profili verilmediği için canlı dağıtım yapılmadı. Aşağıdaki adımlar deploy işlemini somutlaştırır; demo Compose'u internete açmak production kurulumu değildir.

## 1. Dağıtım seçeneği

AWS için önerilen yerleşim: HTTPS ALB, private subnet'lerde API workload'u, private RDS PostgreSQL, TLS/auth etkin Redis, Secrets Manager, private S3 bucket'lar. API'ye ECS task role veya eşdeğer workload identity verilir. Admin'ler ayrı IAM Identity Center/yönetim rolüyle AWS'ye erişir. RDS/Redis portları internete açılmaz.

`infra/terraform` **mevcut uygulama rolüne müşteri IAM rolleri ekleyen bir modüldür**. VPC, ECS, ALB, DNS, RDS, Redis veya mevcut S3 bucket'ları otomatik kurmaz/değiştirmez. Bilinmeyen AWS ortamına pahalı veya yıkıcı kaynakları varsayarak oluşturmamak için bu sınır açık tutuldu. Standalone sunucuda çalıştırmak için ayrı `compose.production.yaml` da sağlandı; yüksek erişilebilirlik garantisi vermez.

## 2. AWS erişimi

Uygulama task rolü yalnızca ilgili müşteri rollerini `sts:AssumeRole` ile alabilmelidir; mevcut `AmazonS3FullAccess`/admin policy bağlanmış olmamalıdır. Müşteriler AWS IAM kullanıcısı olmak zorunda değildir.

Her müşteri rolü:

- Trust policy'de **tam uygulama role ARN** ve müşteriye özel `ExternalId` şartı.
- `s3:ListBucket`: sadece belirli bucket; `s3:prefix` condition müşteri prefix'iyle sınırlı.
- `s3:GetObject`: yalnızca `arn:aws:s3:::bucket/customer_id/*`.
- SSE-KMS varsa sadece ilgili KMS key için `kms:Decrypt`, `kms:ViaService` ile S3'e sınırlı; KMS key policy de bu role izin vermeli.
- Uygulama her AssumeRole isteğinde ek bir dar session policy gönderir. Customer role'de yazma/silme/list-all-buckets izinleri yoktur.

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Gerçek bucket, müşteri ID/prefix ve uygulama role adını düzenleyin.
terraform init
terraform fmt -check -recursive
terraform validate
terraform test
terraform plan -out=tfplan
# Planı kendi hesabınız için inceleyip onayladığınızda:
terraform apply tfplan
terraform output customer_role_arns
```

State'i erişimi kısıtlı, şifreli, kilitlemeli remote backend'de tutun; yerel state/plan'ı Git'e eklemeyin. Veritabanındaki prefix/role/external ID eşleşmesi Terraform çıktısıyla aynı olmalı. IAM propagation birkaç saniye gecikebilir. Bu sürüm `arn:aws` ve ortak AWS region kullanır; GovCloud/China/çok region için uyarlama gerekir.

## 3. S3 bucket kontrolleri

Mevcut bucket'larda Block Public Access'in dört ayarı etkin, Object Ownership bucket owner enforced olmalı; ACL ile veri açılmamalı. Varsayılan SSE-S3 veya SSE-KMS encryption ayarlayın. Versioning ve lifecycle politikasını veri saklama gereksiniminize göre belirleyin. Silmeyi uygulama yapmaz; versioning admin hatalarına karşı ayrıca faydalıdır.

Bucket policy'de TLS zorunluluğu kullanın; `aws:SecureTransport=false` istekleri reddedilsin. Geniş principal/session ARN izinleri eklemeyin. KMS key policy ve bucket policy'yi müşteri isolation testiyle birlikte inceleyin. [AWS prefix koşulu örneği](https://docs.aws.amazon.com/AmazonS3/latest/userguide/walkthrough1.html), [AWS session policy davranışı](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html).

Mevcut admin erişiminizi kaldırmayın: uygulama rolleri yeni, salt okunur bir erişim yolu sağlar. AWS admin'ler mevcut yetkileri ölçüsünde bütün bucket'ları görebilir; uygulama bunu sağlamaz veya değiştirmez.

## 4. Image ve sırlar

```sh
docker build --target production -t YOUR_REGISTRY/tenantfiles-api:RELEASE ./backend
docker build -t YOUR_REGISTRY/tenantfiles-web:RELEASE ./frontend
```

Python/npm bağımlılıkları lock dosyalarıyla sabitlenmiştir. Base image tag'leri rebuild sırasında güncellenebilir; release sırasında test edilen base digest'leri ve son image digest'lerini kaydedin. CI yüksek/kritik açıkları tarar ve image artifact'ı üretir. Release image'larını registry'ye kendi dağıtım sürecinizle yükleyin, digest ile deploy edin. Docker build'in başarılı olması AWS IAM veya kapasite kabulünün yerine geçmez.

`.env.production.example` ayar isimlerini gösterir; gerçek sırlar repoya/build arg/frontend bundle içine girmez. APP_SECRET için `python3 -c 'import secrets; print(secrets.token_hex(32))'` kullanın. Bütün replica'lar aynı secret, DB ve Redis'i kullanmalı. APP_SECRET rotasyonu mevcut API anahtarlarını ve açık tarayıcı oturumlarını geçersiz kılar; önce yeniden anahtar dağıtımını planlayın.

Production DB için TLS server sertifikasını doğrulayın (`sslmode=verify-full` + CA bundle). Redis için `rediss://` + servisinizin ACL/kullanıcı/parolası; sertifika doğrulamasını kapatmayın. Secret manager'ın değerleri environment'a geçirmesi platformun sorumluluğudur. .env fallback dosyasını 0600 tutun. Workload IAM kimliği için uzun ömürlü AWS key'i image'a koymayın.

## 5. Migration ve başlatma

Deployment sırası: DB yedeği → tek migration job → readiness → API replica'ları → web → smoke test. Migration'ı her replica başlangıcında otomatik çalıştırmayın.

```sh
# Standalone örneği: ayrı manifest, demo compose ile merge edilmez.
cp .env.production.example .env.production
chmod 600 .env.production
# .env.production değerlerini ve infra/certs/rds-ca.pem dosyasını hazırlayın.
export API_IMAGE='YOUR_REGISTRY/tenantfiles-api@sha256:REAL_DIGEST'
export WEB_IMAGE='YOUR_REGISTRY/tenantfiles-web@sha256:REAL_DIGEST'
docker compose -f compose.production.yaml run --rm --no-deps api alembic upgrade head
docker compose -f compose.production.yaml up -d --wait
```

Standalone Docker'ın IAM rolü edinebilmesi ayrıca yapılandırılmalıdır; ECS task metadata/IRSA otomatik olarak bu Compose'a gelmez. EC2 instance profile kullanılıyorsa metadata erişimini ve yalnızca hedef workload'un kimlik almasını dikkatle tasarlayın. Görev bazlı kimlik için ECS tercih edin. Bu repo static AWS credential mount'u varsaymaz.

Uygulama DB kullanıcısı runtime'da şema değiştirebilmemeli. Migration job için ayrı DDL kimliği; runtime için gerekli SELECT + audit INSERT izinleri; operatör CLI için müşteri/key yazma izinleri kullanın. Kod aynı komutları sunar, kimlik ayrımı deployment secret'larıyla yapılır.

## 6. HTTPS, proxy ve hız limiti

Web yalnızca aynı origin'den `/api` çağırır. `PUBLIC_ORIGIN` tam HTTPS origin olmalı; sonunda slash olmamalı. `ALLOWED_HOSTS` gerçek domain, gerekli iç health host adlarıyla sınırlanır. HTTPS cookie için `__Host-` prefix kullanılır; Domain attribute eklenmez.

Standalone kurulumda web `127.0.0.1:8080` dinler. Host üstündeki Caddy/Nginx 443'ü dinleyip buraya proxy edebilir; örnek `infra/Caddyfile.example`. HTTPS redirect ve HSTS edge'de etkinleştirilmelidir. ALB kurulumunda ACM sertifikası ve 80→443 redirect kullanılır.

**Proxy IP'si kritik:** backend yalnızca web container'ının IP'sinden gelen forwarded header'lara güvenir; manifestte bu IP sabittir. `--forwarded-allow-ips='*'` kullanmayın. Web önünde başka proxy varsa Nginx gerçek istemci IP'sini yalnızca o güvenilir proxy'den almalıdır. Aksi halde bütün müşteriler aynı IP limitine takılır.

Host üzerindeki TLS proxy + mevcut production bridge için `infra/nginx-trusted-proxy.conf.example` dosyasını inceleyip Nginx'e `/etc/nginx/conf.d/00-trusted-proxy.conf:ro` olarak mount edin. Örnekteki gateway IP'sini **kendi ağınızda doğrulayın**. ECS/ALB için sadece ALB'nin izin verilen ağ aralıkları ve security group'u güvenilir olmalı; internetten gelen `X-Forwarded-For` doğrudan kabul edilmemeli.

Müşteri başına 120 istek/dakika, login IP başına 10/dakika varsayılandır. Header API authentication için IP başına ek koruma vardır. Paylaşımlı NAT'tan çok müşteri geliyorsa IP limitlerini ölçerek ayarlayın. Redis `noeviction` kullanır: dolduğunda anahtarları atıp limitleri sıfırlamak yerine hata verir. Redis kapasitesini/bağlantılarını alarm ile izleyin. CDN/cache korunan API yollarını cache'lememeli.

## 7. Canlıya çıkış kabulü

1. Gerçek uygulama workload kimliğiyle Amy rolünü üstlenin: Amy prefix list/download başarılı; Atlas prefix list ve **var olduğunu bildiğiniz Atlas test nesnesi** GetObject `AccessDenied` olmalı. Aynısını ters yönde yapın. HTTP'de sadece 404 almak yetmez; yanlış adla zaten olmayan nesne test etmeyin.
2. Doğrudan AWS testinde müşteri rolüyle bucket list-all, PutObject/DeleteObject izni olmadığını IAM policy simulator ve kontrollü staging bucket ile doğrulayın. Gerçek müşteri verisine yazma/silme testi yapmayın.
3. Tarayıcıda Amy→çıkış→Atlas geçişinde Amy adı/verisi/cache görünmemeli. Key revoke/expiry/disable sonrası açık session reddedilmeli. Secure/HttpOnly/Strict cookie, CSP, HSTS ve no-store header'larını edge üzerinde kontrol edin.
4. Gerçek veri hacmiyle CSV limitleri, hata durumları, büyük indirme ve iptal davranışını sınayın. Backend üzerinden trafik geçtiği için throughput/egress bütçesini ölçün.
5. Beklenen eşzamanlı kullanıcı/indirme sayısında yük testi yapın. Bu sürüm `--limit-concurrency 100` ve senkron thread havuzu kullanır; sayı SLA kapasite garantisi değildir. CPU, RSS, DB pool, Redis ve S3 throttling ile p95/p99 latency'yi ölçün; buna göre replica/limit ayarlayın.
6. DB yedeğini ayrı staging DB'ye geri yükleyin. Rastgele seçilen key/müşteri eşlemesi ve audit kayıtlarının geri geldiğini, S3 versioning geri dönüşünün çalıştığını sınayın. RTO/RPO'yu bu ölçümle belirleyin.

Otomatik gerçek AWS salt okunur kontrolü için `scripts/verify_aws_isolation.py` kullanın. Script iki müşteriye ait **mevcut test dosyalarının göreli yolunu** ister ve sadece list/head/get izinlerini sınar. Yazma/silme yapmaz.

## 8. İzleme, yedekleme, olay müdahalesi

- Readiness: PostgreSQL ve Redis. Liveness ayrı. S3 bağımlılığı için kontrollü per-tenant canary ve AWS CloudWatch alarmı kurun.
- Log: yapılandırılmış request JSON; müşteri audit tablosu. 5xx/429 artışı, auth failure artışı, Redis bellek/bağlantı, RDS bağlantı/disk, STS/S3 hata ve indirme bant genişliğini izleyin.
- Audit retention: şirket politikasıyla belirleyin; tarih indeksini kullanarak kontrollü arşiv/purge uygulayın. Bu repo otomatik kayıt silmez. Uzun süre için partition/central immutable log storage planlayın.
- RDS otomatik yedek/PITR + düzenli restore provası. S3 versioning/lifecycle farklı hata sınıflarını kapsar; DB yedeği S3 nesnelerini yedeklemez.
- Redis restart'ında session'ların kaybolması yeniden giriş gerektirir; oturum kaybı veri erişimini açmaz. Rate counters da sıfırlanır; edge/WAF ek koruması korunur.
- Key sızarsa önce `revoke-key`; müşteri topyekûn kapatılacaksa `disable-customer`. Sonra audit + request ID + CloudTrail araştırması. Devam eden indirme geri alınamaz.
- Rollback: önceki image digest'ini geri alabilirsiniz; şema uyumluluğunu kontrol edin. `alembic downgrade` tablo/veri kaybı yaratabilir; production'da körlemesine kullanmayın. Tercih uyumlu migration veya ileri yönlü düzeltmedir.
