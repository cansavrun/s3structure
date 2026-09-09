import hmac
import secrets
from datetime import UTC

from app.core.config import Settings
from app.core.errors import ErrorKind, ServiceError
from app.core.security import KEY_PATTERN, SESSION_PATTERN, digest
from app.model.principal import Principal
from app.repository.api_keys import ApiKeyRepository
from app.repository.customers import CustomerRepository
from app.repository.sessions import SessionRepository
from app.services.audit import AuditService
from app.services.rate_limit import RateLimiter
from app.util.time import now


class AuthService:
    """Kimlik ve oturum kuralları; FastAPI/Request/Response bağımlılığı yoktur."""

    def __init__(
        self,
        settings: Settings,
        customers: CustomerRepository,
        keys: ApiKeyRepository,
        sessions: SessionRepository,
        audit: AuditService,
    ):
        self.settings = settings
        self.customers = customers
        self.keys = keys
        self.sessions = sessions
        self.audit = audit
        self.limiter = RateLimiter(sessions)

    def principal_for_key(self, key_id: str) -> Principal | None:
        key = self.keys.get(key_id)
        if key is None or key.revoked_at is not None:
            return None
        # SQLite timezone'u düşürür. Aware tarihlerin mevcut ofsetini koruruz.
        expiry = key.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= now():
            return None
        customer = self.customers.get(key.customer_id)
        if customer is None or not customer.active:
            return None
        return Principal(customer, key)

    def verify_key(self, raw: str) -> Principal:
        match = KEY_PATTERN.fullmatch(raw) if len(raw) <= 100 else None
        principal = self.principal_for_key(match[1]) if match else None
        actual = digest(self.settings.app_secret.get_secret_value(), raw[:100])
        expected = principal.key.digest if principal else "0" * 64
        valid = hmac.compare_digest(actual, expected)
        if principal is None or not valid:
            self.audit.record("auth.failed", outcome="denied")
            raise ServiceError(
                ErrorKind.UNAUTHENTICATED, "API anahtarı geçersiz veya süresi dolmuş"
            )
        return principal

    def login(self, raw_key: str, old_session: str, client_ip: str) -> tuple[Principal, str]:
        self.limiter.check("auth", client_ip, self.settings.login_limit_per_minute)
        principal = self.verify_key(raw_key)
        raw = secrets.token_urlsafe(32)
        old = old_session if SESSION_PATTERN.fullmatch(old_session) else None
        self.sessions.rotate(old, raw, principal.key.id, self.settings.session_ttl_seconds)
        self.audit.record("auth.login", principal)
        return principal, raw

    def logout(self, raw_session: str) -> None:
        if SESSION_PATTERN.fullmatch(raw_session):
            try:
                self.sessions.delete(raw_session)
            except ServiceError as exc:
                raise ServiceError(
                    ErrorKind.UNAVAILABLE, "Çıkış tamamlanamadı. Yeniden deneyin."
                ) from exc

    def authenticate(self, raw_key: str | None, raw_session: str, client_ip: str) -> Principal:
        if raw_key is not None:
            # Header mevcutsa önceliklidir; geçersiz header çereze geri düşmez.
            self.limiter.check("api-auth", client_ip, self.settings.request_limit_per_minute * 5)
            principal = self.verify_key(raw_key)
        else:
            if not SESSION_PATTERN.fullmatch(raw_session):
                raise ServiceError(ErrorKind.UNAUTHENTICATED, "Lütfen giriş yapın")
            key_id = self.sessions.get_key_id(raw_session)
            # Her istekte DB'den tekrar kontrol: revoke/disable bir sonraki isteği keser.
            principal = self.principal_for_key(key_id) if key_id else None
            if principal is None:
                raise ServiceError(
                    ErrorKind.UNAUTHENTICATED, "Oturum süresi dolmuş. Yeniden giriş yapın."
                )
        self.limiter.check(
            "customer", principal.customer.id, self.settings.request_limit_per_minute
        )
        return principal
