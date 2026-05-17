from sqlalchemy import (
    Column, Integer, String, Numeric, Date, DateTime, Text,
    CheckConstraint, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Invoice(Base):
    """
    Target invoice table – populated after successful validation and transformation
    of staging data. All fields are properly typed.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        # Invoice number is unique per client (not globally)
        UniqueConstraint("client_id", "invoice_number", name="uq_invoices_client_invoice_number"),
        CheckConstraint(
            "invoice_type IN ('VAT', 'CORRECTION', 'ADVANCE', 'PROFORMA')",
            name="ck_invoices_invoice_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'VALIDATED', 'EXPORTED', 'ERROR')",
            name="ck_invoices_status",
        ),
        CheckConstraint("net_amount >= 0", name="ck_invoices_net_amount_non_negative"),
        CheckConstraint("vat_amount >= 0", name="ck_invoices_vat_amount_non_negative"),
        CheckConstraint(
            "gross_amount >= 0", name="ck_invoices_gross_amount_non_negative"
        ),
        # NIP must be exactly 10 digits
        CheckConstraint(r"seller_nip ~ '^\d{10}$'", name="ck_invoices_seller_nip_format"),
        CheckConstraint(r"buyer_nip ~ '^\d{10}$'", name="ck_invoices_buyer_nip_format"),
        Index("ix_invoices_client_id", "client_id"),
        Index("ix_invoices_user_id", "user_id"),
        Index("ix_invoices_import_id", "import_id"),
        Index("ix_invoices_invoice_number", "invoice_number"),
        Index("ix_invoices_invoice_date", "invoice_date"),
        Index("ix_invoices_status", "status"),
        Index("ix_invoices_seller_nip", "seller_nip"),
        Index("ix_invoices_buyer_nip", "buyer_nip"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_id = Column(
        Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False
    )
    # User who processed / created this invoice record
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    # Source import batch
    import_id = Column(Integer, ForeignKey("imports.id", ondelete="SET NULL"))

    invoice_number = Column(String(100), nullable=False)
    invoice_date = Column(Date, nullable=False)
    sale_date = Column(Date)
    invoice_type = Column(String(20), nullable=False, server_default="VAT")

    # Seller details
    seller_nip = Column(String(10), nullable=False)
    seller_name = Column(String(255), nullable=False)
    seller_address = Column(Text)

    # Buyer details
    buyer_nip = Column(String(10), nullable=False)
    buyer_name = Column(String(255), nullable=False)
    buyer_address = Column(Text)

    # Financial totals
    net_amount = Column(Numeric(15, 2), nullable=False)
    vat_amount = Column(Numeric(15, 2), nullable=False)
    gross_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), nullable=False, server_default="PLN")

    # Payment details
    payment_method = Column(String(50))
    payment_due_date = Column(Date)
    bank_account = Column(String(34))  # IBAN format

    status = Column(String(20), nullable=False, server_default="DRAFT")

    # KSeF integration fields
    ksef_reference_number = Column(String(100), unique=True)
    xml_content = Column(Text)  # Generated KSeF-compliant XML
    xml_generated_at = Column(DateTime(timezone=True))

    notes = Column(Text)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    client = relationship("Client", back_populates="invoices")
    user = relationship("User", back_populates="invoices")
    import_record = relationship("Import", back_populates="invoices")
    items = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
    )
    validation_errors = relationship(
        "ValidationError", back_populates="invoice"
    )
    comments = relationship("Comment", back_populates="invoice")


class InvoiceItem(Base):
    """
    Individual line items belonging to an Invoice.
    """

    __tablename__ = "invoice_items"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id", "line_number", name="uq_invoice_items_invoice_line"
        ),
        CheckConstraint("quantity > 0", name="ck_invoice_items_quantity_positive"),
        CheckConstraint(
            "vat_rate >= 0 AND vat_rate <= 100",
            name="ck_invoice_items_vat_rate_range",
        ),
        CheckConstraint(
            "net_amount >= 0", name="ck_invoice_items_net_amount_non_negative"
        ),
        CheckConstraint(
            "vat_amount >= 0", name="ck_invoice_items_vat_amount_non_negative"
        ),
        CheckConstraint(
            "gross_amount >= 0", name="ck_invoice_items_gross_amount_non_negative"
        ),
        Index("ix_invoice_items_invoice_id", "invoice_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_number = Column(Integer, nullable=False)
    item_name = Column(String(500), nullable=False)
    unit_of_measure = Column(String(20))
    quantity = Column(Numeric(15, 4), nullable=False)
    unit_price_net = Column(Numeric(15, 4), nullable=False)
    vat_rate = Column(Numeric(5, 2), nullable=False)
    net_amount = Column(Numeric(15, 2), nullable=False)
    vat_amount = Column(Numeric(15, 2), nullable=False)
    gross_amount = Column(Numeric(15, 2), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    invoice = relationship("Invoice", back_populates="items")
