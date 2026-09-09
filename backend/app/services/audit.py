from sqlalchemy.orm import Session

from app.model.audit_event import AuditEvent
from app.model.principal import Principal
from app.repository.audit import AuditRepository


class AuditService:
    def __init__(self, db: Session, request_id: str):
        self.db = db
        self.repository = AuditRepository(db)
        self.request_id = request_id

    def record(
        self,
        action: str,
        principal: Principal | None = None,
        path: str | None = None,
        outcome: str = "success",
    ) -> None:
        # Korunan HTTP işlemleri salt okunurdur. Audit kalıcılaşmadan veri teslim edilmez.
        # Admin yazıları ayrı, tek bir transaction ile CLI tarafından yönetilir.
        self.repository.add(
            AuditEvent(
                customer_id=principal.customer.id if principal else None,
                key_id=principal.key.id if principal else None,
                action=action,
                object_path=path,
                outcome=outcome,
                request_id=self.request_id,
            )
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
