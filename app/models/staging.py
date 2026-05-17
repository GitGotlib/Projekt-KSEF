from sqlalchemy import (
    Column, Integer, Boolean, DateTime,
    ForeignKey, Index, Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class StagingInvoice(Base):
    """
    Raw staging table – all fields stored as TEXT exactly as imported from TSV.
    No type conversion or business validation is applied at this stage.
    """

    __tablename__ = "staging_invoices"
    __table_args__ = (
        Index("ix_staging_invoices_import_id", "import_id"),
        Index("ix_staging_invoices_numer_faktury", "numer_faktury"),
        Index("ix_staging_invoices_id_firmy", "id_firmy"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_id = Column(
        Integer,
        ForeignKey("imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Original row number in the TSV file (1-based, excluding header)
    row_number = Column(Integer)

    # --- Raw TSV fields (all TEXT) ---
    id_firmy = Column(Text)
    numer_faktury = Column(Text)
    data_wystawienia = Column(Text)
    data_sprzedazy = Column(Text)
    typ_faktury = Column(Text)
    nip_sprzedawcy = Column(Text)
    nazwa_sprzedawcy = Column(Text)
    adres_sprzedawcy = Column(Text)
    nip_nabywcy = Column(Text)
    nazwa_nabywcy = Column(Text)
    adres_nabywcy = Column(Text)
    wartosc_netto = Column(Text)
    kwota_vat = Column(Text)
    wartosc_brutto = Column(Text)
    waluta = Column(Text)
    termin_platnosci = Column(Text)
    sposob_platnosci = Column(Text)
    numer_konta = Column(Text)

    # Validation flag: NULL = not yet validated, True = valid, False = invalid
    is_valid = Column(Boolean)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    import_record = relationship("Import", back_populates="staging_invoices")
    items = relationship(
        "StagingInvoiceItem",
        back_populates="staging_invoice",
        cascade="all, delete-orphan",
    )
    validation_errors = relationship(
        "ValidationError", back_populates="staging_invoice"
    )


class StagingInvoiceItem(Base):
    """
    Raw staging table for invoice line items – all fields stored as TEXT.
    """

    __tablename__ = "staging_invoice_items"
    __table_args__ = (
        Index("ix_staging_invoice_items_import_id", "import_id"),
        Index("ix_staging_invoice_items_staging_invoice_id", "staging_invoice_id"),
        Index("ix_staging_invoice_items_numer_faktury", "numer_faktury"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_id = Column(
        Integer,
        ForeignKey("imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    staging_invoice_id = Column(
        Integer,
        ForeignKey("staging_invoices.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Original row number in the TSV file (1-based, excluding header)
    row_number = Column(Integer)

    # --- Raw TSV fields (all TEXT) ---
    id_firmy = Column(Text)
    numer_faktury = Column(Text)
    lp = Column(Text)  # Line position / item number
    nazwa_towaru_uslugi = Column(Text)
    jednostka_miary = Column(Text)
    ilosc = Column(Text)
    cena_jednostkowa_netto = Column(Text)
    stawka_vat = Column(Text)
    wartosc_netto = Column(Text)
    kwota_vat = Column(Text)
    wartosc_brutto = Column(Text)

    # Validation flag: NULL = not yet validated, True = valid, False = invalid
    is_valid = Column(Boolean)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    import_record = relationship("Import", back_populates="staging_invoice_items")
    staging_invoice = relationship("StagingInvoice", back_populates="items")
