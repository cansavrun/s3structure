from sqlalchemy import select
from sqlalchemy.orm import Session

from app.model.api_key import ApiKey


class ApiKeyRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, key_id: str) -> ApiKey | None:
        return self.db.get(ApiKey, key_id)

    def for_customer(self, customer_id: str) -> list[ApiKey]:
        return list(self.db.scalars(select(ApiKey).where(ApiKey.customer_id == customer_id)))

    def add(self, key: ApiKey) -> ApiKey:
        self.db.add(key)
        self.db.flush()
        return key
