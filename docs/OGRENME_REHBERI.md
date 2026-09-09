# Kodu okuyarak Python, FastAPI ve React öğrenmek

Bu projede hedef sadece S3'ten dosya getirmek değil: her isteğin hangi müşteriye ait olduğunu kanıtlamak ve o sınırı bütün katmanlarda korumak. Aşağıdaki sırayla okuyun; her adım çalışan bir dosyaya bağlıdır. Önce [FastAPI katman mimarisini](FASTAPI_MIMARISI.md) okuyarak dosyaların neden ayrıldığını ve örnek bir isteğin katmanlar arasında nasıl ilerlediğini görebilirsiniz.

## 1. Önce veri modelini anlayın

`backend/app/model/` üç tablo tanımlar; `model/__init__.py` bunları Alembic için ortak metadata'ya kaydeder:

| Tablo | Neyi temsil eder? | Neden gerekli? |
|---|---|---|
| `customers` | ID, görünen ad, bucket, prefix, IAM rolü, aktiflik | Yetkiyi kullanıcı girdisinden bağımsız tutar |
| `api_keys` | HMAC özeti, müşteri bağlantısı, son kullanma ve iptal tarihleri | Bir müşteriye birden fazla kişi/entegrasyon anahtarı verir |
| `audit_events` | Aktör, işlem, göreli yol, istek ID'si ve sonuç | Kim hangi dosyaya erişti sorusunu cevaplar |

Örneğin `amy_c001` kaydının `prefix` değeri `amy_c001/` ise, gelen `2026/09/berlin_solar/production.csv` yolu bu prefix'e eklenir. Kullanıcı `customer_id=atlas` yazsa bile kimliği değişmez.

Python'daki `class Customer(Base)` bir **sınıf** tanımıdır. Burada SQLAlchemy bu sınıfı veritabanı tablosuna eşler. `Mapped[str]`, alanın Python tarafında metin olduğunu; `mapped_column(String(64), primary_key=True)` ise veritabanındaki kolonun özelliklerini belirtir. Tip ipucu tek başına doğrulama yapmaz: doğrulama için Pydantic veya açık kontroller gerekir.

`customer_id = ForeignKey("customers.id")` anahtarın mevcut bir müşteriye bağlanmasını sağlar. Anahtarı kullanıcı adı gibi bir string'e bağlamadık; isim değişse bile sabit ID korunur.

## 2. Python fonksiyonları, context manager ve kaynak ömrü

`def now() -> datetime:` bir fonksiyondur; `-> datetime` dönüş tipini okuyana ve editöre söyler. UTC tarih kullanmak saat dilimi belirsizliğini azaltır.

```python
with factory.begin() as db:
    service = AdminService(db)
    key, raw = service.issue_key(secret, customer_id, name, days)
```

`with`, bir **context manager** kullanır: blok başarılı biterse transaction commit edilir; hata varsa rollback yapılır ve kaynaklar bırakılır. `cli.py`, ham anahtarı bu bloktan **sonra** gösterir. Böylece kaydedilmeyen anahtarı kullanıcıya vermeyiz.

`api/dependencies.py` içindeki `get_db()` fonksiyonunda `yield session`, FastAPI'ye session'ı geçici olarak teslim eder. İstek bitince `with` kapanır. Böylece bağlantıların unutulup birikmesini önleriz. SQLAlchemy'nin connection pool'u her istekte yeni TCP bağlantısı açmak zorunda kalmadan bağlantıları yeniden kullanır.

`try/finally` ise hata olsa bile temizlik yapar. S3 dosyası okunurken veya kullanıcı indirmeyi bırakırken `body.close()` çağrılması bu nedenle önemlidir.

`repository/s3.py` başındaki `from __future__ import annotations`, tip açıklamalarını tanım anında çalıştırmaz. Sınıfın `list` isimli metodu ile Python'un `list[str]` tipinin isim çakışmasını da önler. Tip adlarını çalışma zamanı işlemi zannetmemek için iyi bir örnektir.

## 3. Ayarlar neden kodun içinde değil?

`backend/app/core/config.py` içindeki `Settings(BaseSettings)`, ortam değişkenlerini okur. Kod aynı kalır; yerelde Moto, production'da STS kullanılır. Veritabanı adresleri ve sırlar `.env`/secret manager ile gelir.

`SecretStr`, bir değerin gösterimini maskeler; şifreleme sağlamaz. Değeri kullanırken bilinçli olarak `.get_secret_value()` çağırırız. `model_validator`, birden çok ayarın birlikte güvenli olup olmadığını kontrol eder: production'da HTTP, SQLite ve yerel S3 endpoint'i reddedilir.

Bu yaklaşımı seçtim çünkü yanlış ortam değişkeni bazen doğru koddan daha tehlikelidir. Production olarak işaretlenmiş servis güvenli olmayan ayarlarla başlamaz.

## 4. FastAPI endpoint ve dependency injection

`backend/app/main.py` uygulamayı bir **factory** ile oluşturur:

```python
def create_app(settings=None, *, session_factory=None, redis_client=None, storage=None):
    ...
```

Factory, testlerde gerçek servis yerine kontrol edilen bağımlılıkları verebilmemizi sağlar. Modül import edilirken AWS çağrısı yapılmaz. `*` sonrasındaki parametrelerin isimle verilmesi gerekir; yanlış sırada parametre geçmek zorlaşır.

`@router.get("", response_model=FilePageResponse)` (`/api/files` router prefix'iyle) bir **decorator**: altındaki fonksiyonun bu HTTP yolunu karşılayacağını ve hangi şemada cevap vereceğini kaydeder. `Query(ge=1, le=200)` sayfa boyutunu sınırlar; tek istekte bütün bucket'ı yükleyemeyiz.

```python
def files(principal: Auth, service: FileServiceDep, ...):
    return service.list(principal, path, cursor, limit)
```

`Auth`, `Annotated[Principal, Depends(authenticate)]` tanımına karşılık gelir. FastAPI endpoint'ten önce `authenticate()` çalıştırır. Başarısızsa endpoint'e hiç girilmez. `Db` istek için database session sağlar; `get_file_service()` bunu kullanan audit servisini ve S3 repository'sini birleştirir. Endpoint'e hazır `FileServiceDep` verilir. Buna **dependency injection** denir: fonksiyon ihtiyaçlarını ilan eder, framework onları sağlar.

Endpoint içinde tekrar tekrar anahtar kontrolü kopyalamadım; bir endpoint'te kontrolü unutmak veri sızıntısı yaratabilirdi. Ortak dependency hem okuma kolaylığı hem güvenlik sağlar.

### 4a. Pydantic: gelen ve giden verinin sözleşmesi

`backend/app/schema/`, HTTP istek ve cevap modellerini özelliklerine göre ayırır: `auth.py`, `customer.py`, `files.py`, `health.py`, `error.py`; ortak `PublicResponse` modeli `base.py` içindedir. SQLAlchemy'deki `Customer` kaydı bucket, prefix ve IAM rolünü saklar. API'deki `CustomerResponse` ise yalnızca `id` ve `name` alanlarını tanımlar. Veritabanına yeni bir kolon eklemek, bu kolonu otomatik olarak müşteriye açmaz.

```python
class CustomerResponse(PublicResponse):
    id: str
    name: str

class FileResponse(PublicResponse):
    name: str
    path: str
    size: int = Field(ge=0)
    modified_at: datetime
    is_csv: bool
```

`PublicResponse`, Pydantic'in `BaseModel` sınıfından türetilmiştir. **Kalıtım**, ortak kuralları her modelde tekrar yazmamamızı sağlar. `Field(ge=0)` negatif dosya boyutunu reddeder. `strict=True`, `"123"` metnini `123` sayısına veya `"false"` metnini boolean'a sessizce dönüştürmez. Böylece servis kodundaki tip hatası fark edilir. Ayarlar için aynı katılığı kullanmıyoruz: ortam değişkenleri metin gelir; `Settings` bu metinleri tanımlı tiplere dönüştürmelidir.

Girişte `LoginRequest` kullanılır. `extra="forbid"`, `api_key` dışındaki alanları 422 ile reddeder; örneğin forma eklenmiş bir `customer_id` kabul edilmez. Bu kontrol anahtar doğrulamasının yerini almaz: alan doğru biçimde olsa da `verify_key()` anahtarın geçerliliğini ayrıca denetler. `SecretStr` değerin gösterimini maskeler. Hata yanıtında kullanıcı girdisini geri yansıtmamak için özel 422 handler'ı da kullanılır.

Başarılı yanıtların ortak ayarı `extra="ignore"` olur: servis yanlışlıkla ek bir `bucket` veya `role_arn` alanı döndürürse Pydantic bunu HTTP cevabına eklemez. Bu kural dosya/klasör gibi iç içe modellerde de uygulanır. Alan filtresi, izin verilen bir metin alanının içine yazılmış sırrı tespit eden bir içerik tarayıcısı değildir; gizli veriyi bu alanlara hiç koymamak gerekir.

```python
@router.get("", response_model=FilePageResponse)
def files(principal: Auth, service: FileServiceDep, ...):
    return service.list(principal, path, cursor, limit)
```

FileService burada Python sözlüğü döndürebilir. **Doğrulama sınırı HTTP çıkışıdır:** FastAPI, `response_model` ile sözlüğü doğrular, alanları filtreler ve JSON'a dönüştürür. Aynı model OpenAPI/Swagger'da cevap yapısını oluşturur. `repository/s3.py` artık S3'ün `datetime` değerini korur; ISO 8601 metnine dönüşümü Pydantic yapar. JSON tarihleri `Z` veya saat dilimi ofseti içerebilir; React bunları tarih olarak yorumlar. [FastAPI response model açıklaması](https://fastapi.tiangolo.com/tutorial/response-model/).

`list[FileResponse]` bir dosya modelleri listesidir; `list[list[str]]` CSV satır ve hücrelerini anlatır. `next_cursor: str | None`, metin veya JSON `null` kabul eder. Varsayılan değer atanmadığı için alanın cevapta bulunması yine zorunludur. CSV modelindeki `model_validator(mode="after")`, alanlar doğrulandıktan sonra satırların sütun sayısını ve satır limitini birlikte kontrol eder. [Pydantic model açıklaması](https://docs.pydantic.dev/latest/concepts/models/).

İstemci yanlış veri gönderirse **422**, servis tanımladığı yanıtı üretemezse **500** döner. `api/errors.py` içindeki `ResponseValidationError` handler'ı ham yanıtı veya doğrulama girdilerini loglamaz; yalnızca olay adı ve istek ID'sini kaydeder. `ErrorResponse`, özel hata handler'larının JSON biçimini de tanımlar. `JSONResponse` doğrudan döndüğünde otomatik response-model doğrulaması çalışmadığından, handler içinde modeli açıkça oluşturup `model_dump(mode="json")` çağırırız.

Dosya indirmesi `StreamingResponse` olarak kalır; dosya baytları JSON değildir. Çıkış endpoint'i de gövdesiz **204** döndürür. İkisinde `response_model=None` bilinçli seçilmiştir; OpenAPI indirmeyi `application/octet-stream` olarak tanımlar. `test_schemas.py`, gerçek endpoint'lerde alan filtreleme, yanlış tip, zorunlu alan, güvenli 500, OpenAPI sözleşmesi ve orijinal indirme baytlarını doğrular.

React'teki `frontend/src/api.ts` tipleri de aynı JSON alanlarını tarif eder. TypeScript tipleri geliştirme sırasında kontrol sağlar; ağdan gelen JSON'u çalışma anında doğrulamaz. Bu projede Pydantic sunucu yanıtını çalışma anında doğrular. API alanları değişirse React tipleri ve tüketen bileşenler de güncellenmelidir.

## 5. `async def` neden her yerde yok?

Boto3, standart SQLAlchemy ve bu projedeki Redis client senkron/bloklayıcıdır. Bu yüzden iş yapan endpoint'ler `def` olarak yazıldı. FastAPI bunları worker thread havuzunda çalıştırır. Bloklayıcı Boto3 çağrısını doğrudan `async def` içine koymak event loop'u durdurabilir.

Middleware ve lifespan, framework'ün asenkron akışına katıldığı için `async def` kullanır. `async` bir fonksiyonu otomatik hızlı yapmaz; kullandığı I/O aracının da buna uygun olması gerekir. Daha fazla eşzamanlı trafik için ölçüm sonrası async S3/DB istemcileri veya yatay ölçekleme değerlendirilebilir. [FastAPI resmi açıklaması](https://fastapi.tiangolo.com/async/).

## 6. API key ile şifre arasındaki fark

`core/security.py` anahtar üretirken `secrets.token_urlsafe(32)` kullanır. 32 rastgele bayt, 256 bit entropi sağlar. Anahtar biçimi:

```text
tf_<public_key_id>.<random_secret>
```

Public ID, veritabanında doğru kaydı hızlı bulmak içindir; gizli bölüm değildir. Ham anahtar veritabanına yazılmaz; `HMAC-SHA256(APP_SECRET, "api-key:" + raw)` özeti saklanır. `hmac.compare_digest` karşılaştırmada kullanılır.

İnsan parolaları düşük entropili olduğundan Argon2 gibi yavaş parola hash'leri ister. Bu projedeki anahtarlar yüksek entropili rastgele sırlar olduğu için HMAC uygundur. Bu yöntemi kullanıcı parolalarına aynen uygulamayın. `APP_SECRET` DB'den ayrı tutulur; değiştirilmesi mevcut anahtarları geçersiz kılar.

## 7. Tarayıcıya neden sürekli API key göndertmiyoruz?

Giriş akışı:

1. React formu anahtarı bellekte tutar ve bir kez `/api/auth/login` adresine yollar.
2. Backend key'i doğrular; rastgele oturum token'ı üretir.
3. Token'ın ayrı `session` amacıyla HMAC-SHA256 özeti Redis key'i olur; değeri API key ID'sidir. Oturumun mutlak TTL'i vardır. APP_SECRET değişirse eski oturumların lookup anahtarı da değişir; erişimleri sonlanır.
4. Backend ham oturum token'ını `HttpOnly`, `SameSite=Strict`, production'da `Secure` çerezle verir.
5. React anahtar alanını temizler. Sonraki isteklerde tarayıcı çerezi kendisi gönderir.

`HttpOnly`, JavaScript'in cookie değerini okumasını engeller. XSS'i tamamen çözmez: zararlı script yine kullanıcının tarayıcısından istek yapabilir. Bu yüzden React'in metin kaçışına, CSP'ye ve üçüncü taraf script kullanmamaya da dikkat ettik.

Her istekte Redis'teki key ID'si veritabanında tekrar doğrulanır. Anahtarın iptal/expiry durumu cache'e alınmaz; iptalden sonraki ilk istekte erişim kesilir. Sadece login anında kontrol etmek, eski session'ları açık bırakırdı.

## 8. S3 klasör sanıldığı gibi klasör değildir

S3 anahtarları metindir. `amy_c001/2026/09/...` gerçek bir disk klasörü değildir; ortak başlangıcı olan object key'lerdir. `Delimiter="/"`, listeleri klasör gibi gruplar.

`util/paths.py` istemci yolunu **normalize etmek yerine reddeder**: `..`, `.`, ters eğik çizgi, kontrol karakteri, tekrar kodlanabilecek `%`, wildcard ve belirsiz parçalar kabul edilmez. AWS key'inizde bu karakterler varsa dosyayı kurala uygun yeniden adlandırın. Bu bilinçli isim sözleşmesidir; S3'ün her olası key adını desteklemeyi hedeflemez.

Sondaki `/` müşteri sınırıdır: `amy_c001` ile başlayan her şey değil, `amy_c001/` altı. Yoksa `amy_c0012/...` yanlışlıkla eşleşebilir.

## 9. AWS'de ikinci güvenlik katmanı

`Storage.client()` müşteri kaydındaki rolü `AssumeRole` ile alır. Role ARN tarayıcıdan gelmez. Ayrıca isteğe özel IAM **session policy** ile bucket/prefix sınırı daraltılır. Gerçek izinler müşteri rolü ile session policy'nin kesişimidir; session policy role yeni izin eklemez. [AWS AssumeRole belgesi](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html).

Ana uygulama rolünün doğrudan S3 admin izni olmamalı. Uygulama yalnızca tanımlı müşteri rollerini üstlenir. Her müşteri rolü yalnızca `s3:ListBucket` ve `s3:GetObject` alır. Yazma ve silme izni yoktur.

Geçici AWS credentials müşteriye gönderilmez. 15 dakikalık credentials 10 dakika cache'lenir; cache anahtarı müşteri ID, bucket, prefix, role ARN ve diğer kapsam ayarlarını içerir. Anahtar/oturum doğrulaması bu cache'den bağımsızdır.

## 10. Dosya indirmek ile CSV incelemek farklı problemler

İndirme `StreamingResponse` kullanır. `chunks()` bir Python **generator**: `yield` ile her seferinde 64 KiB verir. Çok büyük dosyayı tek seferde RAM'e almak zorunda kalmayız. `Content-Disposition: attachment` ve `application/octet-stream`, HTML dosyasının uygulama origin'inde çalıştırılması yerine indirilmesini sağlar. UTF-8 dosya adları header'a güvenli biçimde kodlanır.

CSV önizlemesi ise sınırlı bir veri dönüşümüdür: varsayılan en fazla 5 MiB, 200 veri satırı ve 100 sütun. `HEAD` ile boyut ve ETag okunur; `GET` çağrısında `IfMatch` kullanılır. Böylece boyut kontrolü ile okuma arasında değişen dosya için kullanıcı yeniden denemeye yönlendirilir. Okuma ayrıca `limit + 1` baytla sınırlandırılır.

CSV'yi `split(',')` ile parçalamadım: tırnak içinde virgül, satır sonu, BOM, noktalı virgül gibi biçimler için Python `csv` modülü gerekir. Çok büyük CSV önizlemesi reddedilir; indirme açık kalır. Bu ürün kararı bellek tüketimini tahmin edilebilir yapar. 200 satır sınırı tüm dosyanın veri kalitesinin onaylandığı anlamına gelmez.

## 11. React: component, props ve state

`frontend/src/main.tsx` React ağacının girişidir. `QueryClientProvider`, alt bileşenlerin ortak sorgu altyapısını kullanmasını sağlar. `StrictMode` geliştirmede hataları yakalamaya yardım eder.

- `App`: oturum var mı, hata mı, yükleniyor mu kararını verir.
- `Login`: giriş formu ve anahtarın kısa ömürlü state'i.
- `Workspace`: müşteri alanı, yol, arama, liste/kart tercihi ve seçili önizleme.
- `CsvPreview`: erişilebilir modal ve CSV tablosu.
- `Brand`: tekrar kullanılabilir küçük görsel bileşen.

**Props**, üst bileşenden gelen girdilerdir: `<CsvPreview file={preview} customerId={...} onClose={...} />`. **State**, zaman içinde değişen yerel durumdur: `const [path, setPath] = useState('')`. `setPath` çağrısı React'in yeni görünümü hesaplamasını sağlar; DOM'u elle arayıp değiştirmeyiz.

`type FileEntry = {...}` TypeScript sözleşmesidir. `is_csv` boolean olduğu için yanlış alan adını derlemede fark ederiz. TypeScript, internetten gelen JSON'u çalışma zamanında doğrulamaz; burada sözleşmenin sahibi backend'dir. API değişikliklerinde bu tipler ve testler birlikte güncellenir.

## 12. Sunucu verisi neden farklı state'te?

Klasör yolu yerel state'tir; dosya listesi sunucu verisidir. `useInfiniteQuery` sayfalama, yüklenme, hata ve iptal sinyalini yönetir.

```tsx
queryKey: ['files', me.customer.id, path]
```

Müşteri ID'sini key'e ekledim; aynı dosya yolu farklı müşterilerde farklı veridir. Oturum değişiminde ayrıca bütün query cache temizlenir. `Workspace` bileşeninin `key` değeri müşteri ID'sidir; müşteri değişince yerel state de sıfırlanır.

`AbortSignal`, gezinme sırasında eski istekleri iptal edebilmek için `fetch`'e aktarılır. Yanlış klasörün geç gelen yanıtını yeni klasör gibi göstermek istemeyiz.

Arama, yüklü listenin filtrelenmiş görünümüdür; ayrı effect/state'e gerek yoktur. Kod doğrudan `.filter(...)` ile türetir. **Arama yalnızca yüklenen sayfalarda ve mevcut klasörde çalışır**; bütün S3'te recursive arama değildir. [React: effect'e ne zaman gerek yok?](https://react.dev/learn/you-might-not-need-an-effect).

## 13. React effect, form ve erişilebilirlik

Form submit bir kullanıcı olayıdır; giriş isteği submit handler içinde yapılır. `useEffect` içine “anahtar değişirse giriş yap” mantığı koymadım. Böylece kullanıcı yazarken tekrar tekrar giriş denenmez.

`CsvPreview` effect'i ise native `dialog.showModal()` API'siyle senkronizasyon yapar; bu effect için uygun bir kullanımdır. Cleanup fonksiyonu dialog'u kapatır. Escape tuşu, focus sınırı ve önceki odağın geri verilmesi native dialog ile sağlanır. [React effect açıklaması](https://react.dev/learn/synchronizing-with-effects).

Input'larda label, ikon düğmelerinde `aria-label`, hatalarda `role="alert"`, yüklenmelerde `role="status"` vardır. Mobil tasarım yatay taşmayı önler. Hareket azaltma tercihi CSS'te desteklenir.

CSV hücresini `{value}` ile çiziyoruz; `dangerouslySetInnerHTML` kullanmıyoruz. `<script>` yazan bir hücre metin olarak görünür, çalışmaz. Test bu davranışı doğrudan kontrol eder.

## 14. Testleri nasıl okuyacaksınız?

Önce `tests/test_isolation.py` içindeki üç müşterili senaryoları okuyun. Fixture gerçek AWS yerine Moto, her test için ayrı SQLite dosyası ve FakeRedis oluşturur. **Fixture**, testin başlangıç durumunu hazırlayıp sonunda temizleyen fonksiyondur.

`pytest.mark.parametrize`, aynı davranışı birçok yol/senaryoyla çalıştırır. Örneğin path traversal denemeleri üç endpoint'te aynı korumanın bulunduğunu sınar. Mutlu yolun çalışması tek başına yeterli değildir.

`test_integration.py`, taklit yerine gerçek PostgreSQL'de migration upgrade/downgrade ve aynı prefix'i aynı anda kaydetmeye çalışan iki transaction'ı test eder. PostgreSQL advisory lock sebebiyle yalnızca biri başarılı olur. Gerçek Redis testinde paralel isteklerin atomik sayaçtan benzersiz ardışık değer aldığını doğrularız.

React testleri anahtarın depolanmamasını, hata gösterimini ve CSV'nin güvenli çizimini sınar. Playwright ise gerçek browser → React → FastAPI → PostgreSQL/Redis → Moto akışını kullanır. İndirilen dosyanın içeriğini de okur. IAM policy mock testi gerçek AWS kabul testinin yerine geçmez.

## 15. Docker ve migration neden ayrı?

Backend Dockerfile çok aşamalıdır. Build aşaması `uv.lock` içindeki kesin sürümleri kurar; son image'da geliştirme/test araçları bulunmaz. Son process root olmayan UID 10001 ile çalışır. Frontend Node aşamasında derlenir; son image Nginx ve statik dosyaları taşır.

Container taraması ayrıca taban image'ın paketlerini de inceler. İlk tarama, Python'un global pip paketine gömülü eski bağımlılıklar ve eski Nginx/Alpine paketlerinde açıklar buldu. Production container'da paket kurulmadığı için global pip/ensurepip/setuptools/wheel çıkarıldı; Nginx güncel stable tabanına alındı ve işletim sistemi paketleri güncellendi. Son image taramasında düzeltmesi bulunan yüksek/kritik açık kalmadı. Yalnızca `npm audit` veya Python uygulama bağımlılıklarını taramak taban image'ı kapsamaz.

`alembic upgrade head` veritabanı şemasını versiyonlu değiştirir. API her başladığında `create_all()` çalıştırmaz: birden fazla instance başlarken yarış ve kontrolsüz şema değişimi istemeyiz. Deployment tek migration job çalıştırır, sonra API'leri açar.

Öğrenmek için küçük alıştırma: CSV row limit'ini değiştirin; truncation testini yeniden çalıştırın. Ardından bir anahtarı iptal edip açık tarayıcıdaki Yenile düğmesine basın. Güvenlik kararını hem kodda hem görünür davranışta izleyin.
