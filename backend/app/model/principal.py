from dataclasses import dataclass

from app.model.api_key import ApiKey
from app.model.customer import Customer


@dataclass(frozen=True)
class Principal:
    customer: Customer
    key: ApiKey
