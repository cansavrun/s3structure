from app.schema.base import PublicResponse


class ErrorResponse(PublicResponse):
    detail: str
    request_id: str | None = None
