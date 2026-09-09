"""CSV önizleme kuralları; S3 ve HTTP olmadan doğrudan test edilebilir."""

import csv
import io

from app.core.config import Settings
from app.core.errors import ErrorKind, ServiceError


class CsvPreviewParser:
    def __init__(self, settings: Settings):
        self.settings = settings

    def parse(self, raw: bytes, name: str, size: int) -> dict:
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ServiceError(ErrorKind.INVALID_DATA, "CSV, UTF-8 kodlamasında olmalı") from exc
        if "\x00" in content:
            raise ServiceError(ErrorKind.INVALID_DATA, "CSV ikili veri içeriyor")
        try:
            dialect = csv.Sniffer().sniff(content[:8192], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(content, newline=""), dialect=dialect, strict=True)
        try:
            headers = next(reader, [])
            self._check_columns(headers)
            rows = []
            truncated = False
            for row in reader:
                self._check_columns(row)
                if len(rows) >= self.settings.preview_max_rows:
                    truncated = True
                    break
                if len(row) != len(headers):
                    raise ServiceError(
                        ErrorKind.INVALID_DATA, "CSV satırlarının sütun sayıları tutarsız"
                    )
                rows.append(row)
        except csv.Error as exc:
            raise ServiceError(
                ErrorKind.INVALID_DATA, "CSV yapısı geçersiz veya bir hücre çok büyük"
            ) from exc
        return {
            "name": name,
            "headers": headers,
            "rows": rows,
            "truncated": truncated,
            "row_limit": self.settings.preview_max_rows,
            "size": size,
        }

    def _check_columns(self, row: list[str]):
        if len(row) > self.settings.preview_max_columns:
            raise ServiceError(ErrorKind.INVALID_DATA, "CSV çok fazla sütun içeriyor")
