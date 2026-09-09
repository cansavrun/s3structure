# Bu makinedeki yerel container ortamı

Mevcut Docker CLI 25.0.2 ve Compose 2.24.3 kullanılabilir durumdaydı; Docker Desktop uygulamasının çalıştırılabilir dosyası eksikti. Bu uygulamaya dokunmadan `tenantfiles` adlı ayrı Colima profili oluşturuldu.

- Colima 0.10.3 / Lima 2.2.0; Docker Engine 29.5.2, Linux ARM64.
- Apple VZ, 2 CPU, 3 GiB RAM, 20 GiB sanal disk. Disk tahsisi kullanım ile büyür.
- Ev klasörü VM'e mount edilmedi. SSH config eklenmedi. Varsayılan Docker context değiştirilmedi.
- Docker client auth/config bu depodaki `.local/docker-client` altında ayrıdır; mevcut Docker giriş bilgileri okunmadı/kopyalanmadı.
- Image taraması için Trivy 0.72.0 kuruldu.

Bu makinede komutlar:

```sh
# Profil durmuşsa:
colima start --profile tenantfiles --activate=false --ssh-config=false --mount none \
  --cpus 2 --memory 3 --disk 20 --vm-type vz --binfmt=false

scripts/docker_local.sh compose up -d --wait
scripts/docker_local.sh compose ps
scripts/docker_local.sh compose logs -f api web

# Container'ları durdur; veritabanı volume'unu koru:
scripts/docker_local.sh compose down

# VM'i durdur; image/volume'ları koru ve belleği serbest bırak:
colima stop --profile tenantfiles
```

Makefile kısayolları da kullanılabilir: `make DOCKER=./scripts/docker_local.sh up` ve `make DOCKER=./scripts/docker_local.sh seed`.

Uygulama `http://localhost:8080`; Docker demo anahtarları `.local/docker-demo-keys.json` içinde. Bu anahtarlar ayrı veritabanına bağlıdır; Docker dışındaki `5173` demosunun anahtarlarıyla karıştırmayın.

Normal çalışan Docker Engine olan başka bir makinede bu yardımcı betiğe/Colima'ya gerek yoktur; README'deki `make up` / `make seed` yeterlidir.

## Kurulum yan etkisi

İlk `brew install colima` çağrısı Homebrew'ün otomatik cleanup işlemini de tetikledi; bazı eski keg/cache dosyaları ve bağımlılık sayılmayan `libevent`, `unbound`, `zlib` paketleri kaldırıldı. Bu üç paket tekrar kuruldu (libevent 2.1.13, unbound 1.25.2, zlib 1.3.2); unbound bağımlılığı libnghttp2 1.69.0'a yükseldi. Eski sürüm keg/cache dosyaları geri getirilmedi. Hiçbir unbound servisi başlatılmadı ve mevcut unbound ayar dosyası korunmuştur. Sonraki kurulumlarda otomatik cleanup kapatıldı.

Yeni araçlar işletim sistemi paketleri olarak kalır; Colima profili başlangıçta otomatik çalışan servis olarak kaydedilmedi.
