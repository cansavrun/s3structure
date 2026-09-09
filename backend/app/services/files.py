from app.core.config import Settings
from app.core.errors import ErrorKind, ServiceError
from app.model.principal import Principal
from app.repository.s3 import S3Repository
from app.services.audit import AuditService
from app.services.csv_preview import CsvPreviewParser
from app.util.paths import scoped_key


class FileService:
    def __init__(self, storage: S3Repository, audit: AuditService, settings: Settings):
        self.storage = storage
        self.audit = audit
        self.settings = settings

    def list(self, principal: Principal, path: str, cursor: str | None, limit: int) -> dict:
        result = self.storage.list(principal.customer, path, cursor, limit)
        self.audit.record("files.list", principal, path)
        return result

    def preview(self, principal: Principal, path: str) -> dict:
        scoped_key(principal.customer.prefix, path)
        if not path.lower().endswith(".csv"):
            raise ServiceError(
                ErrorKind.UNSUPPORTED, "Önizleme yalnızca CSV dosyaları için kullanılabilir"
            )
        raw, size = self.storage.read_limited(
            principal.customer, path, self.settings.preview_max_bytes
        )
        result = CsvPreviewParser(self.settings).parse(raw, path.split("/")[-1], size)
        self.audit.record("files.preview", principal, path)
        return result

    def download(self, principal: Principal, path: str) -> dict:
        result = self.storage.open_download(principal.customer, path)
        try:
            # İzni kaydederiz; kullanıcının bütün baytları indirdiğini iddia etmeyiz.
            self.audit.record("files.download_authorized", principal, path)
        except Exception:
            result["Body"].close()
            raise
        return result
