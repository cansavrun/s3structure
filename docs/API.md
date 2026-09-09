# API sözleşmesi

Frontend ve API aynı origin'dedir. API anahtarı query string'e yazılmaz. Browser girişinden sonra cookie kullanılır; sunucudan sunucuya entegrasyon için `X-API-Key` header'ı desteklenir.

| Yöntem / yol | Kimlik | İşlev |
|---|---|---|
| `POST /api/auth/login` | JSON API key + tam Origin | Cookie oturumu oluştur |
| `POST /api/auth/logout` | Tam Origin | Mevcut cookie oturumunu iptal et |
| `GET /api/me` | Cookie veya X-API-Key | Müşteri adı/ID, key adı, expiry, önizleme limiti |
| `GET /api/files` | Cookie veya X-API-Key | Tek klasörü sayfalı listele |
| `GET /api/files/preview` | Cookie veya X-API-Key | Sınırlı CSV önizlemesi |
| `GET /api/files/download` | Cookie veya X-API-Key | Orijinal dosyayı akış halinde indir |
| `GET /health/live` | Yok | API process yanıt veriyor mu? |
| `GET /health/ready` | Yok | DB ve Redis ulaşılabilir mi? |

Readiness her müşterinin AWS rolünü veya S3 bucket'ını denemez. Staging kabulünde ayrıca gerçek rol testi gerekir. Geliştirmede Swagger `/api/docs`, OpenAPI `/api/openapi.json`; production'da ikisi de kapalıdır. Nginx'in iç health endpoint'i `/health/web`'dir; backend health yolları internete proxy edilmez.

## Pydantic şemaları

İstek ve yanıt modelleri `backend/app/schema/` içindedir. `pydantic` doğrudan runtime bağımlılığıdır; kesin sürüm `backend/uv.lock` ile kilitlenir.

| İşlem | Şema |
|---|---|
| Giriş isteği | `LoginRequest` — yalnızca `api_key`; ek alanlar 422 |
| Giriş yanıtı | `LoginResponse` → `CustomerResponse` |
| Oturum bilgisi | `MeResponse` → `CustomerResponse` |
| Dosya listesi | `FilePageResponse` → `FolderResponse`, `FileResponse` |
| CSV önizleme | `CsvPreviewResponse` |
| Health | `LiveResponse`, `ReadyResponse` |
| Özel hata handler'ları | `ErrorResponse` |

JSON başarı yanıtları endpoint'teki `response_model` ile doğrulanır; şemada bulunmayan alanlar çıkarılır. Eksik zorunlu alan, yanlış tip veya tutarsız CSV tablosu bir sunucu hatasıdır ve temizlenmiş 500 yanıtı döndürür. CSV hücreleri string kalır; tarih alanları ISO 8601 metni olarak serileştirilir. `next_cursor` alanı zorunludur, son sayfada `null` olur. Download ham bayt akışı, logout gövdesiz 204 olduğu için bu ikisinde JSON modeli yoktur. Bu modeller müşteri yetkilendirmesi ve S3 prefix/IAM kontrollerine ek olarak çalışır.

## Browser login

```http
POST /api/auth/login
Origin: https://files.example.com
Content-Type: application/json

{"api_key":"tf_<key_id>.<secret>"}
```

`200` ve `Set-Cookie: __Host-tenantfiles=...; Secure; HttpOnly; Path=/; SameSite=Strict` döner. HTTP geliştirme ortamında isim `tenantfiles_dev` olur, Secure işareti yoktur. Sonraki isteklerde key taşımayın; `credentials: 'same-origin'` yeterlidir. Login ve logout eksik/yanlış Origin ile 403 alır.

## Python ile entegrasyon

```python
import os
import httpx

headers = {"X-API-Key": os.environ["TENANTFILES_API_KEY"]}
with httpx.Client(base_url="https://files.example.com", headers=headers, timeout=60) as client:
    listing = client.get("/api/files", params={"path": "2026/09/berlin_solar/"})
    listing.raise_for_status()
    print(listing.json()["files"])

    with client.stream("GET", "/api/files/download",
                       params={"path": "2026/09/berlin_solar/production.csv"}) as response:
        response.raise_for_status()
        with open("production.csv", "wb") as output:
            for chunk in response.iter_bytes():
                output.write(chunk)
```

Bu API key header'ı ile cookie olmadan çalışır; Origin browser endpoint'lerinde zorunludur, dosya API header doğrulamasında gerekmez. Bir istekte hem cookie hem X-API-Key gönderilirse **header** doğrulanır; geçersiz header cookie'ye geri düşmez.

## Listeleme

```http
GET /api/files?path=2026%2F09%2Fberlin_solar%2F&limit=100
```

```json
{
  "path": "2026/09/berlin_solar/",
  "folders": [],
  "files": [{
    "name": "production.csv",
    "path": "2026/09/berlin_solar/production.csv",
    "size": 1596,
    "modified_at": "2026-09-09T12:00:00+00:00",
    "is_csv": true
  }],
  "next_cursor": null
}
```

Örnek response içindeki boyut/tarih temsili değerlerdir. `path` boşsa müşteri kökü. `limit` 1–200; `next_cursor` varsa aynı müşteri ve klasörle sonraki istekte `cursor` olarak gönderilir. Cookie/API key olmadan token tek başına erişim vermez. Cursor başka klasör/müşteride veya 15 dakika sonra reddedilir.

## CSV önizleme

```http
GET /api/files/preview?path=2026%2F09%2Fberlin_solar%2Fproduction.csv
```

```json
{"name":"production.csv","headers":["site","kwh"],"rows":[["berlin","120"]],
 "truncated":false,"row_limit":200,"size":20}
```

Hücreler string'dir; backend tarih/sayı/formül çalıştırmaz. `truncated=true` sadece ilk satırların gösterildiğini belirtir. Dosya tamamen incelendi/onaylandı anlamına gelmez.

## Hata davranışı

| Durum | Anlam / yapılacak iş |
|---|---|
| 400 | Geçersiz yol, geçersiz/süresi dolan sayfa token'ı; yolu düzelt/yenile |
| 401 | Eksik/geçersiz/iptal edilmiş/süresi dolmuş anahtar veya oturum; yeniden giriş |
| 403 | Origin veya cross-site kontrolü başarısız |
| 404 | Dosya yok veya depolama izni yok; başkasının verisi olup olmadığı açıklanmaz |
| 409 | Dosya değişti veya arşivde; yeniden dene/yöneticiden restore iste |
| 413 | CSV boyut sınırını aşıyor; orijinali indir |
| 415 | CSV olmayan dosyada önizleme istendi |
| 422 | Alan/CSV biçimi/kodlama/sütun kontrolü başarısız |
| 429 | Hız sınırı; backend `Retry-After: 60` döndürür |
| 500 | Sunucu yanıtı tanımlı şemaya uymuyor; X-Request-ID ile araştırılmalı |
| 503 | DB, Redis veya AWS servisinde geçici hata |

Hata gövdesi `{"detail":"Türkçe açıklama"}` biçimindedir; istek ve yanıt doğrulama hatalarında ayrıca `request_id` bulunur. API cevaplarında `X-Request-ID` sorun araştırmak için kullanılır. Ham Pydantic hata girdileri veya iç yanıt verileri dışarı verilmez. Nginx ve middleware kaynaklı hatalar farklı gövde döndürebilir; frontend JSON olmayan hataları da karşılar. Dosya indirmesi native browser akışıdır; indirme hatası yeni sekmede API hatası olarak görünebilir.
