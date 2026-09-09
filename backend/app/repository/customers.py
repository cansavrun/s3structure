from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.model.customer import Customer


class CustomerRepository:
    """SQL burada kalır. Repository commit etmez; transaction kararı çağırandadır."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, customer_id: str) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def all(self) -> list[Customer]:
        return list(self.db.scalars(select(Customer)))

    def in_bucket(self, bucket: str) -> list[Customer]:
        return list(self.db.scalars(select(Customer).where(Customer.bucket == bucket)))

    def lock_registration(self) -> None:
        # Kilit transaction bitince bırakılır; iki operatör aynı prefix'i kaydedemez.
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(9042026)"))

    def add(self, customer: Customer) -> Customer:
        self.db.add(customer)
        self.db.flush()
        return customer
