from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.validators.nip import validate_nip

# ---------------------------------------------------------------------------
# Invoice Items
# ---------------------------------------------------------------------------


class InvoiceItemCreate(BaseModel):
    line_number: int
    item_name: str
    unit_of_measure: Optional[str] = None
    quantity: Decimal
    unit_price_net: Decimal
    vat_rate: Decimal
    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Ilość musi być większa od zera")
        return v

    @field_validator("vat_rate")
    @classmethod
    def vat_rate_range(cls, v: Decimal) -> Decimal:
        if v < 0 or v > 100:
            raise ValueError("Stawka VAT musi być w zakresie 0–100")
        return v

    @field_validator("net_amount", "vat_amount", "gross_amount")
    @classmethod
    def amounts_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Kwota nie może być ujemna")
        return v


class InvoiceItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    line_number: int
    item_name: str
    unit_of_measure: Optional[str]
    quantity: Decimal
    unit_price_net: Decimal
    vat_rate: Decimal
    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    created_at: datetime


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


class InvoiceCreate(BaseModel):
    invoice_number: str
    invoice_date: date
    sale_date: Optional[date] = None
    invoice_type: str = "VAT"

    seller_nip: str
    seller_name: str
    seller_address: Optional[str] = None

    buyer_nip: str
    buyer_name: str
    buyer_address: Optional[str] = None

    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    currency: str = "PLN"

    payment_method: Optional[str] = None
    payment_due_date: Optional[date] = None
    bank_account: Optional[str] = None

    notes: Optional[str] = None
    items: List[InvoiceItemCreate] = []

    @field_validator("seller_nip", "buyer_nip")
    @classmethod
    def validate_nip_fields(cls, v: str) -> str:
        return validate_nip(v)

    @field_validator("invoice_type")
    @classmethod
    def validate_invoice_type(cls, v: str) -> str:
        allowed = {"VAT", "CORRECTION", "ADVANCE", "PROFORMA"}
        if v not in allowed:
            raise ValueError(f"Typ faktury musi być jednym z: {', '.join(allowed)}")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3:
            raise ValueError("Kod waluty musi mieć dokładnie 3 znaki (np. PLN)")
        return v

    @field_validator("net_amount", "vat_amount", "gross_amount")
    @classmethod
    def amounts_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Kwota nie może być ujemna")
        return v

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Numer faktury nie może być pusty")
        return v


class InvoiceUpdate(BaseModel):
    """Wszystkie pola opcjonalne – aktualizacja częściowa."""

    sale_date: Optional[date] = None
    invoice_type: Optional[str] = None
    buyer_nip: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_address: Optional[str] = None
    net_amount: Optional[Decimal] = None
    vat_amount: Optional[Decimal] = None
    gross_amount: Optional[Decimal] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    payment_due_date: Optional[date] = None
    bank_account: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("buyer_nip")
    @classmethod
    def validate_nip_field(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_nip(v)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"DRAFT", "VALIDATED", "EXPORTED", "ERROR"}
            if v not in allowed:
                raise ValueError(f"Status musi być jednym z: {', '.join(allowed)}")
        return v

    @field_validator("net_amount", "vat_amount", "gross_amount")
    @classmethod
    def amounts_non_negative(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Kwota nie może być ujemna")
        return v


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    user_id: Optional[int]
    import_id: Optional[int]
    invoice_number: str
    invoice_date: date
    sale_date: Optional[date]
    invoice_type: str
    seller_nip: str
    seller_name: str
    seller_address: Optional[str]
    buyer_nip: str
    buyer_name: str
    buyer_address: Optional[str]
    net_amount: Decimal
    vat_amount: Decimal
    gross_amount: Decimal
    currency: str
    payment_method: Optional[str]
    payment_due_date: Optional[date]
    bank_account: Optional[str]
    status: str
    ksef_reference_number: Optional[str]
    xml_generated_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    items: List[InvoiceItemResponse] = []


class InvoiceListItem(BaseModel):
    """Lżejsza wersja faktury do użycia w listach (bez pozycji i XML)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    invoice_number: str
    invoice_date: date
    invoice_type: str
    buyer_nip: str
    buyer_name: str
    gross_amount: Decimal
    currency: str
    status: str
    ksef_reference_number: Optional[str]
    created_at: datetime
