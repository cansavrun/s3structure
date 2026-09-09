"""Uygulama hataları HTTP framework'ünden bağımsızdır; durum kodu API'de eşlenir."""

from enum import StrEnum


class ErrorKind(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    TOO_LARGE = "too_large"
    UNSUPPORTED = "unsupported"
    INVALID_DATA = "invalid_data"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"


class ServiceError(Exception):
    def __init__(self, kind: ErrorKind, message: str, *, retry_after: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retry_after = retry_after
