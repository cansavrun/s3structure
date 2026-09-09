from sqlalchemy.orm import Session

from app.model.audit_event import AuditEvent


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, event: AuditEvent) -> None:
        self.db.add(event)
