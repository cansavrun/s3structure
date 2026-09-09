import re

from app.core.errors import ErrorKind, ServiceError


def relative_path(value: str, *, folder: bool = False) -> str:
    """Yolu normalize etmiyoruz: belirsiz/kaçış içeren girdiyi reddediyoruz."""
    if not value:
        if folder:
            return ""
        raise ServiceError(ErrorKind.INVALID_INPUT, "Dosya yolu gerekli")
    if len(value.encode("utf-8")) > 900:
        raise ServiceError(ErrorKind.INVALID_INPUT, "Dosya yolu çok uzun")
    if value.startswith("/") or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ServiceError(ErrorKind.INVALID_INPUT, "Geçersiz dosya yolu")
    if any(c in value for c in ("\\", "%", "*", "?", "$", "{", "}")):
        raise ServiceError(ErrorKind.INVALID_INPUT, "Geçersiz dosya yolu")
    parts = value.removesuffix("/").split("/")
    if any(p in {"", ".", ".."} for p in parts):
        raise ServiceError(ErrorKind.INVALID_INPUT, "Geçersiz dosya yolu")
    if not folder and value.endswith("/"):
        raise ServiceError(ErrorKind.INVALID_INPUT, "Dosya yolu klasör olamaz")
    return value.rstrip("/") + "/" if folder else value


def tenant_prefix(value: str) -> str:
    """Boş prefix yalnızca müşteriye tahsis edilmiş bucket için kullanılabilir."""
    if not value:
        return ""
    normalized = relative_path(value, folder=True)
    if not re.fullmatch(r"[a-zA-Z0-9_/-]+/", normalized) or len(normalized) > 256:
        raise ValueError("Prefix ASCII harf, rakam, _, - ve / içermeli; en fazla 256 karakter")
    return normalized


def scoped_key(prefix: str, path: str, *, folder: bool = False) -> str:
    safe = relative_path(path, folder=folder)
    if prefix and not prefix.endswith("/"):
        raise ServiceError(ErrorKind.UNAVAILABLE, "Müşteri depolama ayarı geçersiz")
    result = prefix + safe
    if len(result.encode("utf-8")) > 1024:
        raise ServiceError(ErrorKind.INVALID_INPUT, "Dosya yolu çok uzun")
    return result
