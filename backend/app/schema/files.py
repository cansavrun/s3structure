from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from app.schema.base import PublicResponse


class FolderResponse(PublicResponse):
    name: str
    path: str


class FileResponse(PublicResponse):
    name: str
    path: str
    size: int = Field(ge=0)
    # Python katmanında datetime tutarız; ISO 8601 JSON dönüşümünü Pydantic yapar.
    modified_at: datetime
    is_csv: bool


class FilePageResponse(PublicResponse):
    path: str
    folders: list[FolderResponse] = Field(max_length=200)
    files: list[FileResponse] = Field(max_length=200)
    # `| None` null'a izin verir; varsayılan atamadığımız için alan yine zorunludur.
    next_cursor: str | None


class CsvPreviewResponse(PublicResponse):
    name: str
    headers: list[str] = Field(max_length=500)
    rows: list[list[str]] = Field(max_length=1000)
    truncated: bool
    row_limit: int = Field(ge=1, le=1000)
    size: int = Field(ge=0)

    @model_validator(mode="after")
    def consistent_table(self) -> Self:
        # Tek alanın tipi yetmez: tablo boyutlarının da birbirini tutması gerekir.
        if len(self.rows) > self.row_limit:
            raise ValueError("Önizleme satır sınırını aşıyor")
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError("Önizleme satırlarının sütun sayıları tutarsız")
        return self
