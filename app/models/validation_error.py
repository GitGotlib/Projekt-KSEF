from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    CheckConstraint, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class ValidationError(Base):
    """
    Stores all validation errors found during SQL or Python validation steps.
    References can point to an import batch, a staging invoice, or a target invoice.
    """

    __tablename__ = "validation_errors"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('ERROR', 'WARNING')",
            name="ck_validation_errors_severity",
        ),
        Index("ix_validation_errors_import_id", "import_id"),
        Index("ix_validation_errors_invoice_id", "invoice_id"),
        Index("ix_validation_errors_staging_invoice_id", "staging_invoice_id"),
        Index("ix_validation_errors_severity", "severity"),
        Index("ix_validation_errors_is_resolved", "is_resolved"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # At least one of the three FKs below should be set
    import_id = Column(Integer, ForeignKey("imports.id", ondelete="CASCADE"))
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    staging_invoice_id = Column(
        Integer, ForeignKey("staging_invoices.id", ondelete="CASCADE")
    )

    # Row in the source file where the error occurred
    row_number = Column(Integer)
    # Name of the field that failed validation
    field_name = Column(String(100))
    # Short machine-readable error code, e.g. "MISSING_NIP", "INVALID_DATE"
    error_code = Column(String(50))
    error_message = Column(Text, nullable=False)
    severity = Column(String(10), nullable=False, server_default="ERROR")
    is_resolved = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    import_record = relationship("Import", back_populates="validation_errors")
    invoice = relationship("Invoice", back_populates="validation_errors")
    staging_invoice = relationship(
        "StagingInvoice", back_populates="validation_errors"
    )
