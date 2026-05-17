from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime,
    CheckConstraint, ForeignKey, Index, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Import(Base):
    __tablename__ = "imports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NEW', 'LOADED', 'VALIDATED', 'ERROR', 'EXPORTED')",
            name="ck_imports_status",
        ),
        # import_month must be in YYYY-MM format
        CheckConstraint(
            r"import_month ~ '^\d{4}-\d{2}$'",
            name="ck_imports_import_month_format",
        ),
        CheckConstraint("row_count >= 0", name="ck_imports_row_count_non_negative"),
        CheckConstraint("error_count >= 0", name="ck_imports_error_count_non_negative"),
        Index("ix_imports_client_id", "client_id"),
        Index("ix_imports_user_id", "user_id"),
        Index("ix_imports_status", "status"),
        Index("ix_imports_import_month", "import_month"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(
        Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Billing month in YYYY-MM format, e.g. "2024-01"
    import_month = Column(String(7), nullable=False)
    filename = Column(String(500), nullable=False)
    file_size_bytes = Column(BigInteger)
    row_count = Column(Integer, server_default="0")
    error_count = Column(Integer, server_default="0")
    status = Column(String(20), nullable=False, server_default="NEW")
    notes = Column(Text)
    imported_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    client = relationship("Client", back_populates="imports")
    user = relationship("User", back_populates="imports")
    staging_invoices = relationship(
        "StagingInvoice", back_populates="import_record", cascade="all, delete-orphan"
    )
    staging_invoice_items = relationship(
        "StagingInvoiceItem",
        back_populates="import_record",
        cascade="all, delete-orphan",
    )
    invoices = relationship("Invoice", back_populates="import_record")
    validation_errors = relationship(
        "ValidationError", back_populates="import_record", cascade="all, delete-orphan"
    )
    logs = relationship("Log", back_populates="import_record")
    comments = relationship("Comment", back_populates="import_record")
