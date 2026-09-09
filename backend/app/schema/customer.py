from app.schema.base import PublicResponse


class CustomerResponse(PublicResponse):
    id: str
    name: str
