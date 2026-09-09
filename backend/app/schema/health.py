from typing import Literal

from app.schema.base import PublicResponse


class LiveResponse(PublicResponse):
    status: Literal["ok"]


class ReadyResponse(PublicResponse):
    status: Literal["ready"]
