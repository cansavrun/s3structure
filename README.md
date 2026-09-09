# TenantFiles — müşteriye özel S3 dosya portalı

FastAPI + React/TypeScript. Kullanıcı API anahtarıyla giriş yapar; yalnızca kendisine atanmış S3 alanını listeler, CSV dosyalarını tarayıcıda inceler ve dosyaları indirir. AWS hesabı veya konsol erişimi gerekmez.

**Yetki sınırı backend'dedir:** `API key → müşteri → bucket + prefix → müşteri IAM rolü`. Tarayıcıdan gelen bucket veya müşteri seçimine güvenilmez. Ortak bucket/ayrı prefix ve ayrı bucket modelleri desteklenir. Admin erişiminiz mevcut AWS yönetim rollerinizle devam eder; uygulamanın internete açık bir admin endpoint'i yoktur.

## Hızlı başlangıç — Docker

Gereken: çalışan Docker Engine/Desktop ve Docker Compose v2.

**Backend mimarisi:** `app/api`, `core`, `model`, `repository`, `schema`, `services`, `util`. [Katmanların görevleri ve kod üzerinden anlatım](docs/FASTAPI_MIMARISI.md).

**Bu makinedeki hazır demo:** [localhost:8080](http://localhost:8080). Anahtarlar `.local/docker-demo-keys.json` içindedir. Docker Desktop eksik olduğu için bağımsız `tenantfiles` Colima profili kuruldu; [çalıştırma/durdurma ve makine değişiklikleri](docs/YEREL_ORTAM.md). Bu profil için `docker` yerine `scripts/docker_local.sh` kullanabilirsiniz.

**Hazır image arşivi:** `output/releases/tenantfiles-images-linux-arm64.tar.gz` (backend + frontend), yanında `SHA256SUMS`. ARM64 Linux içindir; başka bir Docker Engine'e `docker load -i output/releases/tenantfiles-images-linux-arm64.tar.gz` ile aktarılabilir. x86_64 image için CI veya o mimaride Docker build kullanın.

```sh
make up
make seed
```

1. `make up`, `.env` dosyasını rastgele sırlarla oluşturur; PostgreSQL, Redis, yerel S3 taklidi, API ve web'i başlatır. Veritabanı migration'ı API'den önce tamamlanır.
2. `make seed`, **iki farklı demo müşteri için farklı anahtarlar** üretir. Çıktıdaki `api_key` ile [localhost:8080](http://localhost:8080) adresine giriş yapın.
3. `2026 → 09 → berlin_solar → production.csv → Önizle` yolunu izleyin.
4. Çıkış yapıp diğer anahtarla giriş yaparak müşteri ayrımını deneyin.

```sh
make logs     # Servis logları; key/cookie/body loglanmaz
make down     # Servisleri durdur; PostgreSQL verisini koru
make build    # tenantfiles-api:local ve tenantfiles-web:local image'larını oluştur
```

S3 taklidi Moto bellekte çalışır: yeniden başlatıldığında `make seed` tekrar çalıştırılır. Bu işlem her seferinde yeni, 7 günlük demo anahtarları verir. Demo verisi/anahtarı gerçek AWS ortamına yazılamaz.

## Docker olmadan çalıştırma

Python 3.12–3.13, `uv`, **Node.js 24 LTS**, npm ve `redis-server` gerekir. Node 23 desteklenen geliştirme sürümü değildir.

```sh
cd backend
uv sync --frozen
cd ../frontend
npm ci
cd ..
make demo-local
```

[localhost:5173](http://localhost:5173) açılır. Anahtarlar `.local/demo-keys.json` içindedir; dosya yalnızca kullanıcı tarafından okunabilir ve Git'e alınmaz. Varsayılan yerel veritabanı SQLite'tır. PostgreSQL ile birebir uygulama akışı için:

```sh
# PostgreSQL araçları PATH'te olmalı; macOS EnterpriseDB 17 otomatik bulunur.
# Gerekiyorsa: POSTGRES_BIN=/postgres/bin python3 scripts/local_demo.py --postgres
python3 scripts/local_demo.py --postgres
```

Betik kendi PostgreSQL cluster'ını `.local/postgres` altında oluşturur; mevcut veritabanlarını kullanmaz. Portlar: web `5173`, API `8000`, PostgreSQL `55432`, Redis `56379`, S3 taklidi `55000`. Hepsi yalnızca loopback'e bağlanır. `Ctrl+C` bu betiğin başlattığı servisleri kapatır.

## Örnek S3 düzeni

```text
s3://your-private-customer-data/
├── amy_c001/                     ← Amy müşteri sınırı; sonda / kritik
│   └── 2026/
│       └── 09/
│           ├── berlin_solar/
│           │   ├── production.csv
│           │   ├── summary.csv
│           │   └── readme.txt
│           └── hamburg_wind/
│               └── production.csv
└── atlas_c002/                   ← Farklı müşteri
    └── 2026/09/berlin_solar/production.csv
```

`customer_name` değişebilir; bu yüzden sabit bir müşteri ID'si kullanın (`amy_c001`). Aylar iki basamaklı olsun (`01`…`12`). Dosya yolları müşteriye göre göreli döner: Amy `2026/09/...` görür, bucket adını ve diğer müşterileri görmez. Özel bucket'ın tümü bir müşteriye aitse prefix `""` olabilir. Aynı bucket içinde kapsayan/çakışan prefix kayıtları reddedilir.

## Müşteri ve anahtar yönetimi

Komutlar güvenilir operatör ortamında çalışır. Gerçek ortamda `S3_MODE=sts` ve müşteri role ARN + external ID zorunludur.

```sh
docker compose exec api python -m app.cli add-customer \
  --id amy_c001 --name 'Amy Energy' \
  --bucket your-private-customer-data --prefix 'amy_c001/' \
  --role-arn arn:aws:iam::123456789012:role/tenantfiles-amy_c001 \
  --external-id amy-c001-specific-random-identifier

docker compose exec api python -m app.cli issue-key \
  --customer amy_c001 --name 'Ayşe / operasyon' --days 90

docker compose exec api python -m app.cli list-keys --customer amy_c001
docker compose exec api python -m app.cli revoke-key --id KEY_ID
docker compose exec api python -m app.cli disable-customer --id amy_c001
```

Anahtar yalnızca oluşturulduğu anda gösterilir. Her kişiye/entegrasyona ayrı anahtar verin. Rotasyonda önce yeni anahtar üretin, güvenli kanaldan teslim edin, eski anahtarı iptal edin. İptal edilmiş anahtara bağlı açık oturumlar **sonraki istekte** reddedilir. Daha önce başlamış dosya akışı veya indirilmiş dosya geriye alınamaz.

## Testler

```sh
make test
make lint
cd frontend && npm run build
```

Gerçek servis testleri (`--postgres` demo çalışırken):

```sh
cd backend
TEST_DATABASE_URL=postgresql+psycopg://tenantfiles@127.0.0.1:55432/tenantfiles_test \
TEST_REDIS_URL=redis://127.0.0.1:56379/15 \
uv run --frozen pytest --cov=app --cov-report=term-missing
```

Tarayıcı testleri (yerel demo çalışırken):

```sh
cd frontend
npx playwright install chromium
npm run test:e2e
```

Docker üzerinde tarayıcı testi için `make seed` çıktısını `.local/demo-keys.json` olarak kaydedin; `E2E_BASE_URL=http://localhost:8080 npm run test:e2e` çalıştırın. Testler Chromium masaüstü ve mobil görünümde gerçek backend'e gider; indirme içeriğini de kontrol eder. AWS servis davranışı birim testlerinde Moto ile taklit edilir; Moto, gerçek IAM değerlendirmesinin kanıtı değildir.

GitHub Actions: backend/React testleri, gerçek PostgreSQL ve Redis, Docker build, container üzerinden E2E, bağımlılık/image güvenlik taraması ve Terraform testleri. Başarılı image'lar `docker-images` artifact'ı olarak dışa aktarılır; yayın/dağıtım otomatik yapılmaz. Artifact indirildikten sonra `gunzip -c tenantfiles-images.tar.gz | docker load` ile yüklenebilir.

## Öğrenme ve production

- [Adım adım Python, FastAPI, React rehberi](docs/OGRENME_REHBERI.md)
- [Mimari, tehdit modeli ve güvenlik sınırları](docs/MIMARI_VE_GUVENLIK.md)
- [Production kurulumu, IAM, yedekleme ve işletim](docs/PRODUCTION.md)
- [API sözleşmesi ve kullanım örnekleri](docs/API.md)
- [Çalıştırılan doğrulamalar ve kalan ortam kontrolleri](docs/DOGRULAMA.md)

Bu depo üretim için güvenlik kontrolleri, testler ve dağıtım dosyaları içerir. Canlı ortama alınmış veya gerçek AWS hesabınızda doğrulanmış bir servis değildir. Canlı kabulde HTTPS, gerçek IAM ret testleri, yük testi ve yedekten geri dönüş kontrolü gereklidir; ayrıntılı adımlar production rehberindedir.
