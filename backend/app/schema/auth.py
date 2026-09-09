from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schema.base import PublicResponse
from app.schema.customer import CustomerResponse


class LoginRequest(BaseModel):
    # Yazım hatalarını ve customer_id/bucket gibi yetki seçme girişimlerini reddederiz.
    # SecretStr gösterimi maskeler; doğrulama hataları ayrıca api/errors.py'de temizlenir.
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1, max_length=100)


class LoginResponse(PublicResponse):
    customer: CustomerResponse


class MeResponse(PublicResponse):
    customer: CustomerResponse
    key_name: str
    expires_at: datetime
    preview_max_bytes: int = Field(ge=1024, le=20 * 1024 * 1024)
