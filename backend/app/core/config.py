from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Ayarlar koddan ayrılır. SecretStr hata mesajlarında sırları maskeler.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr = SecretStr("sqlite:///./tenantfiles.db")
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    app_secret: SecretStr = Field(min_length=32)
    public_origin: str = "http://localhost:8080"
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver", "api"]
    session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    login_limit_per_minute: int = Field(default=10, ge=1)
    request_limit_per_minute: int = Field(default=120, ge=1)
    preview_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    preview_max_rows: int = Field(default=200, ge=1, le=1000)
    preview_max_columns: int = Field(default=100, ge=1, le=500)
    aws_region: str = "eu-central-1"
    s3_mode: Literal["local", "sts"] = "sts"
    s3_endpoint_url: str | None = None

    @model_validator(mode="after")
    def secure_production(self):
        origin = urlsplit(self.public_origin)
        if origin.scheme not in {"http", "https"} or not origin.netloc:
            raise ValueError("PUBLIC_ORIGIN geçerli bir http(s) origin olmalı")
        if origin.path or origin.query or origin.fragment or origin.username:
            raise ValueError("PUBLIC_ORIGIN yalnızca scheme://host[:port] içermeli")
        if "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS wildcard içeremez")
        if self.environment == "production":
            if origin.scheme != "https":
                raise ValueError("Production HTTPS gerektirir")
            if self.s3_mode != "sts" or self.s3_endpoint_url:
                raise ValueError("Production yalnızca AWS STS modunu destekler")
            if not self.database_url.get_secret_value().startswith("postgresql+psycopg://"):
                raise ValueError("Production PostgreSQL gerektirir")
            db_query = parse_qs(urlsplit(self.database_url.get_secret_value()).query)
            if db_query.get("sslmode") != ["verify-full"]:
                raise ValueError("Production PostgreSQL için sslmode=verify-full gerektirir")
            if not self.redis_url.get_secret_value().startswith("rediss://"):
                raise ValueError("Production Redis TLS (rediss://) gerektirir")
            secret = self.app_secret.get_secret_value()
            # Rastgele hex sır her olası karakteri içermek zorunda değildir.
            if len(set(secret)) < 8 or any(
                marker in secret.lower() for marker in ["replace", "change_me", "test-only"]
            ):
                raise ValueError("APP_SECRET rastgele ve en az 32 karakter olmalı")
        return self

    @property
    def secure_cookie(self) -> bool:
        return self.public_origin.startswith("https://")

    @property
    def cookie_name(self) -> str:
        return "__Host-tenantfiles" if self.secure_cookie else "tenantfiles_dev"
