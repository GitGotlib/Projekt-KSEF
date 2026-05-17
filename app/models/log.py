from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Text,
    CheckConstraint, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Log(Base):
    """
    Audit log for all system operations: imports, validations, XML generation,
    user actions, etc.
    """

    __tablename__ = "logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('SUCCESS', 'ERROR', 'INFO')",
            name="ck_logs_status",
        ),
        Index("ix_logs_user_id", "user_id"),
        Index("ix_logs_client_id", "client_id"),
        Index("ix_logs_import_id", "import_id"),
        Index("ix_logs_operation", "operation"),
        Index("ix_logs_status", "status"),
        Index("ix_logs_created_at", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # All FK references are nullable – system-level events may not involve a user
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"))
    import_id = Column(Integer, ForeignKey("imports.id", ondelete="SET NULL"))

    # Operation name, e.g. "IMPORT", "VALIDATE", "GENERATE_XML", "LOGIN"
    operation = Column(String(50), nullable=False)
    # Type of entity affected, e.g. "Invoice", "Client"
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    # JSON-serialised extra details
    details = Column(Text)
    ip_address = Column(String(45))  # Supports both IPv4 and IPv6
    status = Column(String(10), nullable=False, server_default="INFO")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="logs")
    client = relationship("Client", back_populates="logs")
    import_record = relationship("Import", back_populates="logs")
