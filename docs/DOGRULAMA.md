# Doğrulama kaydı — 9 Eylül 2026

Bu kayıt gerçekleştirilen kontrolleri ve ortam gerektiren kalan işleri ayırır. Test sonuçları canlı AWS kabulü veya kapasite sertifikası değildir.

## Katmanlı FastAPI mimarisi — son doğrulama

- Uygulama `api`, `core`, `model`, `repository`, `schema`, `services`, `util` paketlerine ayrıldı. `main.py` **40 satır**; endpoint veya SQL sorgusu içermez. Servis/repository katmanları FastAPI/Starlette import etmez.
- **151 backend testi geçti**, atlanan test yok. Docker/Linux ortamında gerçek PostgreSQL ve Redis ile bütün test paketi çalıştırıldı. **28 yeni test** katman sınırları, repository transaction sahipliği, uygulamalar arası kaynak/ayar ayrımı, audit başarısızlığında stream kapatma, admin rollback/anahtar iptali ve saat dilimli expiry kontrolünü kapsar.
- Kod kapsamı **%97,16** (914 statement, 26 eksik); yönetim/demo CLI kapsam metriğine dahil değil. Yeni yönetim servisi kapsama dahildir. Pydantic şema modülleri **%100** kapsamda.
- Alembic upgrade/downgrade ve model/DB şema eşitliği geçti. Eşzamanlı aynı prefix kaydında yalnızca bir transaction başarılı oldu. Redis'te 32 eşzamanlı sayaç artışı/TTL testi geçti. Test veritabanı demo DB'den ayrıydı ve testten sonra silindi.
- Ruff lint/format ve Python import/derleme kontrolleri geçti. AWS kabul betiğinin yeni importlarla yardım ekranı çalıştırıldı; gerçek AWS'ye istek yapılmadı.
- Güncel production API image üzerinde masaüstü/mobil **4 Chromium testi geçti**. Giriş, listeleme, CSV önizleme, indirme baytları, oturum ve müşteri değiştirme davranışları korundu. API container sağlıklı ve `localhost:8080` üzerinde çalışıyor.
- Yeni API image için mevcut yerel Trivy veritabanıyla düzeltmesi bulunan HIGH/CRITICAL açık **0**. Docker arşivi ve SHA-256 özeti yenilendi; iki image etiketi ve checksum doğrulandı. Image kimlikleri `output/releases/images.txt` içindedir.
- [Yeni mimari rehberi](FASTAPI_MIMARISI.md), öğrenme rehberi ve API dokümanı güncellendi. URL/JSON sözleşmesi, veritabanı tabloları ve CLI giriş noktaları korunur; eski modül yolları yeni paketlere taşınmıştır. Canlı AWS/production dağıtımı ve yük testiyle ilgili aşağıdaki doğrulama sınırları sürer.

## Önceki Pydantic şema güncellemesi

- `schemas.py` eklendi; giriş, müşteri, oturum, dosya listesi, CSV, health ve özel hata cevapları modellendi. JSON başarı endpoint'leri `response_model` kullanıyor. `pydantic` doğrudan bağımlılık olarak tanımlandı; kilitli sürüm değişmedi.
- **121 backend testi geçti** (`pytest -m 'not integration'`), bunların **22'si yeni HTTP sözleşme testleri**. Kod kapsamı **%94,70**, `schemas.py` kapsamı **%100**. PostgreSQL/Redis için ayrı iki entegrasyon testi bu güncellemede yeniden çalıştırılmadı; ilk teslim sonuçları aşağıdadır.
- Ruff lint/format geçti. Güncel Docker API ile masaüstü ve mobil **4 Chromium testi geçti**: giriş, listeleme, CSV önizleme, indirme baytları, oturum ve müşteri değiştirme doğrulandı.
- API image yeniden oluşturuldu ve çalışan `localhost:8080` uygulamasına uygulandı. Mevcut demo verileri ve anahtarları korundu. Frontend kaynakları değişmedi.
- Yeni API image'ının mevcut yerel Trivy veritabanıyla taramasında düzeltmesi bulunan HIGH/CRITICAL açık **0**. Image arşivi ve SHA-256 özeti yenilendi; arşivin iki image etiketi ve checksum'u doğrulandı. Frontend image önceki doğrulanmış image'dır.
- Öğrenme rehberine **4a. Pydantic** bölümü eklendi; API sözleşmesi ve OpenAPI gerçek modellerle eşleştirildi. Login gövdesinde bilinmeyen ek alanlar artık 422 döndürür. HTTP yanıtındaki yanlış tip/eksik alan temizlenmiş 500 üretir; hata girdileri müşteriye veya loglara yazılmaz.

## İlk teslimde tamamlanan kontroller

| Kontrol | Sonuç |
|---|---|
| Python backend testleri | **101 geçti** |
| Backend kod kapsamı | **%94,13** — app modülleri; yönetim/demo CLI kapsam metriğine dahil değil |
| Gerçek PostgreSQL 17 entegrasyonu | Migration upgrade/downgrade, model/şema eşitliği, çakışan müşteri kaydında eşzamanlılık geçti |
| Gerçek Redis entegrasyonu | 32 eşzamanlı artışta atomik sayaç ve TTL geçti |
| React bileşen/oturum testleri | **6 geçti** |
| Chromium uçtan uca testleri | **4 geçti** — masaüstü ve mobil görünüm |
| TypeScript + React production build | Geçti |
| ESLint, Prettier, Ruff | Geçti |
| Terraform validate | Geçti |
| Terraform mock IAM testleri | **2 geçti** — müşteri kapsamı ve çakışan prefix reddi |
| Docker Compose development/production manifest doğrulaması | Geçti (production örnek env ile) |
| Docker backend/frontend image build | Geçti — Linux ARM64, ayrı Colima Engine |
| Docker container smoke / health | PostgreSQL, Redis, Moto, API ve web sağlıklı; migration tamamlandı |
| Docker üzerinden Chromium uçtan uca testleri | Son image'larda masaüstü/mobil **4 test geçti** |
| Trivy container taraması | Her iki son image'da düzeltmesi bulunan HIGH/CRITICAL açık: **0** |
| Taşınabilir image arşivi | İki image içeren 113 MiB tar.gz, SHA-256 checksum; `docker load` ile yeniden yükleme doğrulandı |
| Python production bağımlılık taraması | Bilinen açık bulunmadı (`pip-audit`, tüm kilitli runtime bağımlılıkları) |
| npm bağımlılık taraması | Bilinen açık bulunmadı |

Backend testleri path traversal, çift encoding, yabancı bucket/prefix parametreleri, müşteri kapsamına bağlı cursor, özel bucket kökü, geçersiz/iptal/expired key, customer disable, secret rotasyonu, Origin/CSRF, hız limiti, Redis arızası, bozuk/büyük CSV, HTML içerikli hücreler, ETag yarış koşulu, streaming kaynak kapatma ve güvenli hata mesajlarını kapsar.

Tarayıcı testleri gerçek React → FastAPI → PostgreSQL/Redis → Moto bağlantısını kullanır. Giriş, klasör gezintisi, arama, liste/kart görünümü, CSV modal, dosya indirme **baytları**, sayfa yenilemede oturum, çıkış ve müşteri değiştirme kontrol edilir. Browser dosya/cache testlerinde başka müşterinin içeriğine erişim reddi doğrulandı. Mobil emülasyon Chromium'dur; gerçek iOS Safari cihaz testi yapılmadı.

Tarayıcı testi ilk oturum kontrolünde query'nin kendi kendine iptal edilmesi sorununu buldu; müşteri dosya cache'i temizlenirken aktif `me` gözlemcisi korunacak şekilde düzeltildi ve React regresyon testi eklendi. Son kaynaklar okunabilir Python/React/CSS biçimine getirildi.

Kullanılan ortam: macOS ARM64, Python 3.13, test/build için Node.js 24. Test bağımlılıklarında Starlette/httpx ve anyio için iki deprecation uyarısı var; testler başarısız olmuyor. Bağımlılık güncellemesinde yeni test client arayüzü değerlendirilmeli.

## Çalıştırılmayan / kanıtlanmayan kontroller

- **Gerçek AWS STS/IAM/S3 kabulü:** müşteri AWS hesabı/rolleri/erişim bağlamı verilmedi; gerçek AWS'ye erişilmedi veya değişiklik uygulanmadı. Moto ve Terraform mock testleri gerçek IAM değerlendirmesini doğrulamaz. Salt okunur kabul betiği ve adımları `PRODUCTION.md` içinde.
- **Production altyapı dağıtımı ve TLS edge:** canlı ortamda çalıştırılmadı. Container taraması yerelde yapıldı. CI tanımlandı; repo henüz bir GitHub remote'una gönderilmediği için CI sonucu yoktur.
- **Yük testi, SLA/RTO/RPO ve yedek restore provası:** hedef trafik/hosting/backup politikası gerektirir. Bu verilere ait performans garantisi üretilmedi.

## Yerel çıktılar

Çalışan Docker demo: `http://localhost:8080`. Anahtarlar `.local/docker-demo-keys.json` dosyasında, gerçek müşteri anahtarları değildir. Docker dışında doğrulanan `5173` demo servisleri kaynak tasarrufu için durduruldu; tekrar başlatılabilir. Ekran görüntüleri `output/playwright/workspace-desktop.png`, `workspace-mobile.png`, `preview-desktop.png`, `preview-mobile.png` altında; görsel olarak incelendi. Bu geçici sonuçlar ve sırlar Git'e alınmaz.

Image'lar `output/releases/tenantfiles-images-linux-arm64.tar.gz`, kimlikleri `images.txt`, dosya bütünlük özeti `SHA256SUMS` içinde. Yerel mimari ARM64'tür; AMD64 dağıtımı için o mimaride build/CI gerekir. İlk container taramasında bulunan taban image açıkları, global pip/ensurepip kaldırılarak ve Nginx/Alpine güncellenerek giderildi. Trivy taraması `--severity HIGH,CRITICAL --ignore-unfixed` kapsamındadır; bilinen bütün düşük/orta önem açıkları veya henüz yaması olmayan açıklar yoktur anlamına gelmez.

Colima/Lima/Trivy kurulumunun ve Homebrew otomatik temizliğinin makine üzerindeki etkileri [yerel ortam notlarında](YEREL_ORTAM.md) kayıtlıdır. Varsayılan Docker context `desktop-linux` olarak korundu.

Geliştirme ortamını tekrar oluşturmak için README'deki komutlar yeterlidir. Demo ve production ayarları bilinçli olarak ayrıdır; yerel test sırlarını gerçek ortama taşımayın.
