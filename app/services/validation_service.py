"""
Serwis walidacji danych w strefie staging.

Walidacja przebiega w dwóch fazach:
1. Walidacja każdej faktury staging (Python) – pola wymagane, formaty, sumy kontrolne.
2. Walidacja spójności między fakturami a pozycjami (opcjonalna / ostrzeżenia).

Po walidacji:
- Rekordy StagingInvoice otrzymują flagę is_valid.
- Błędy zapisywane są do tabeli validation_errors.
- Status importu zmienia się na VALIDATED (wszystkie OK lub tylko WARNING)
  albo ERROR (co najmniej jeden ERROR).

Kody błędów
-----------
MISSING_FIELD      – wymagane pole jest NULL lub puste
INVALID_NIP        – NIP nie przechodzi walidacji sumy kontrolnej
INVALID_DATE       – data nie jest w formacie YYYY-MM-DD
INVALID_AMOUNT     – wartość nie jest liczbą dziesiętną
AMOUNT_MISMATCH    – wartosc_netto + kwota_vat ≠ wartosc_brutto (tolerancja 0.01)
INVALID_CURRENCY   – waluta inna niż ISO 4217 (lista 3-znakowych kodów)
INVALID_INVOICE_TYPE – typ faktury spoza dozwolonych wartości
MISSING_ITEMS      – faktura nie ma żadnej pozycji (ostrzeżenie)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, DecimalException
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.import_ import Import
from app.models.staging import StagingInvoice, StagingInvoiceItem
from app.models.validation_error import ValidationError
from app.validators.nip import validate_nip

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

_ALLOWED_CURRENCIES = frozenset(
    [
        "PLN", "EUR", "USD", "GBP", "CHF", "CZK", "DKK",
        "HUF", "NOK", "SEK", "RON", "BGN", "HRK",
    ]
)

_ALLOWED_INVOICE_TYPES = frozenset(
    ["VAT", "KOREKTA", "ZALICZKOWA", "UPROSZCZONA", "RR"]
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECIMAL_RE = re.compile(r"^-?\d+(\.\d+)?$")

# Tolerancja dla porównania kwot (zaokrąglenia)
_AMOUNT_TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# Reprezentacja pojedynczego znalezionego błędu
# ---------------------------------------------------------------------------


@dataclass
class _Issue:
    field_name: Optional[str]
    error_code: str
    error_message: str
    severity: str = "ERROR"  # "ERROR" | "WARNING"


# ---------------------------------------------------------------------------
# Narzędzia pomocnicze
# ---------------------------------------------------------------------------


def _is_empty(value: Optional[str]) -> bool:
    return not value or not value.strip()


def _parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    if _is_empty(value):
        return None
    try:
        return Decimal(value.strip().replace(",", "."))
    except DecimalException:
        return None


def _validate_date(value: Optional[str], field_name: str) -> Optional[_Issue]:
    if _is_empty(value):
        return None  # wymagane pole obsługuje inna reguła
    v = value.strip()
    if not _DATE_RE.match(v):
        return _Issue(
            field_name=field_name,
            error_code="INVALID_DATE",
            error_message=f"{field_name}: '{v}' nie jest datą w formacie YYYY-MM-DD",
        )
    try:
        date.fromisoformat(v)
    except ValueError:
        return _Issue(
            field_name=field_name,
            error_code="INVALID_DATE",
            error_message=f"{field_name}: '{v}' jest nieprawidłową datą",
        )
    return None


def _validate_amount(value: Optional[str], field_name: str) -> Optional[_Issue]:
    if _is_empty(value):
        return None
    v = value.strip().replace(",", ".")
    if not _DECIMAL_RE.match(v):
        return _Issue(
            field_name=field_name,
            error_code="INVALID_AMOUNT",
            error_message=f"{field_name}: '{value}' nie jest prawidłową liczbą",
        )
    return None


# ---------------------------------------------------------------------------
# Reguły walidacji dla StagingInvoice
# ---------------------------------------------------------------------------


def _validate_invoice(inv: StagingInvoice) -> List[_Issue]:
    issues: List[_Issue] = []

    # ---- Pola wymagane ----
    required_fields = [
        ("id_firmy", "ID_FIRMY"),
        ("numer_faktury", "NUMER_FAKTURY"),
        ("data_wystawienia", "DATA_WYSTAWIENIA"),
        ("nip_sprzedawcy", "NIP_SPRZEDAWCY"),
        ("nazwa_sprzedawcy", "NAZWA_SPRZEDAWCY"),
        ("nip_nabywcy", "NIP_NABYWCY"),
        ("nazwa_nabywcy", "NAZWA_NABYWCY"),
        ("wartosc_netto", "WARTOSC_NETTO"),
        ("kwota_vat", "KWOTA_VAT"),
        ("wartosc_brutto", "WARTOSC_BRUTTO"),
    ]
    for attr, label in required_fields:
        if _is_empty(getattr(inv, attr, None)):
            issues.append(
                _Issue(
                    field_name=label,
                    error_code="MISSING_FIELD",
                    error_message=f"Wymagane pole '{label}' jest puste",
                )
            )

    # ---- Walidacja NIP sprzedawcy ----
    if not _is_empty(inv.nip_sprzedawcy):
        try:
            validate_nip(inv.nip_sprzedawcy)
        except ValueError as exc:
            issues.append(
                _Issue(
                    field_name="NIP_SPRZEDAWCY",
                    error_code="INVALID_NIP",
                    error_message=f"NIP_SPRZEDAWCY: {exc}",
                )
            )

    # ---- Walidacja NIP nabywcy ----
    if not _is_empty(inv.nip_nabywcy):
        try:
            validate_nip(inv.nip_nabywcy)
        except ValueError as exc:
            issues.append(
                _Issue(
                    field_name="NIP_NABYWCY",
                    error_code="INVALID_NIP",
                    error_message=f"NIP_NABYWCY: {exc}",
                )
            )

    # ---- Daty ----
    for attr, label in [
        ("data_wystawienia", "DATA_WYSTAWIENIA"),
        ("data_sprzedazy", "DATA_SPRZEDAZY"),
        ("termin_platnosci", "TERMIN_PLATNOSCI"),
    ]:
        issue = _validate_date(getattr(inv, attr, None), label)
        if issue:
            issues.append(issue)

    # ---- Kwoty ----
    for attr, label in [
        ("wartosc_netto", "WARTOSC_NETTO"),
        ("kwota_vat", "KWOTA_VAT"),
        ("wartosc_brutto", "WARTOSC_BRUTTO"),
    ]:
        issue = _validate_amount(getattr(inv, attr, None), label)
        if issue:
            issues.append(issue)

    # ---- Suma netto + VAT = brutto ----
    netto = _parse_decimal(inv.wartosc_netto)
    vat = _parse_decimal(inv.kwota_vat)
    brutto = _parse_decimal(inv.wartosc_brutto)
    if netto is not None and vat is not None and brutto is not None:
        if abs((netto + vat) - brutto) > _AMOUNT_TOLERANCE:
            issues.append(
                _Issue(
                    field_name="WARTOSC_BRUTTO",
                    error_code="AMOUNT_MISMATCH",
                    error_message=(
                        f"Niezgodność kwot: {netto} + {vat} = {netto + vat}, "
                        f"a WARTOSC_BRUTTO = {brutto}"
                    ),
                )
            )

    # ---- Waluta ----
    if not _is_empty(inv.waluta):
        currency = inv.waluta.strip().upper()
        if currency not in _ALLOWED_CURRENCIES:
            issues.append(
                _Issue(
                    field_name="WALUTA",
                    error_code="INVALID_CURRENCY",
                    error_message=f"Nieznana waluta: '{inv.waluta}'",
                    severity="WARNING",
                )
            )

    # ---- Typ faktury ----
    if not _is_empty(inv.typ_faktury):
        typ = inv.typ_faktury.strip().upper()
        if typ not in _ALLOWED_INVOICE_TYPES:
            issues.append(
                _Issue(
                    field_name="TYP_FAKTURY",
                    error_code="INVALID_INVOICE_TYPE",
                    error_message=(
                        f"Nieznany typ faktury: '{inv.typ_faktury}'. "
                        f"Dozwolone: {', '.join(sorted(_ALLOWED_INVOICE_TYPES))}"
                    ),
                    severity="WARNING",
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Reguły walidacji dla StagingInvoiceItem
# ---------------------------------------------------------------------------


def _validate_item(item: StagingInvoiceItem) -> List[_Issue]:
    issues: List[_Issue] = []

    required_fields = [
        ("numer_faktury", "NUMER_FAKTURY"),
        ("lp", "LP"),
        ("nazwa_towaru_uslugi", "NAZWA_TOWARU_USLUGI"),
        ("ilosc", "ILOSC"),
        ("wartosc_netto", "WARTOSC_NETTO"),
        ("kwota_vat", "KWOTA_VAT"),
        ("wartosc_brutto", "WARTOSC_BRUTTO"),
    ]
    for attr, label in required_fields:
        if _is_empty(getattr(item, attr, None)):
            issues.append(
                _Issue(
                    field_name=label,
                    error_code="MISSING_FIELD",
                    error_message=f"Wymagane pole '{label}' w pozycji jest puste",
                )
            )

    # Kwoty pozycji
    for attr, label in [
        ("ilosc", "ILOSC"),
        ("cena_jednostkowa_netto", "CENA_JEDNOSTKOWA_NETTO"),
        ("wartosc_netto", "WARTOSC_NETTO"),
        ("kwota_vat", "KWOTA_VAT"),
        ("wartosc_brutto", "WARTOSC_BRUTTO"),
    ]:
        issue = _validate_amount(getattr(item, attr, None), label)
        if issue:
            issues.append(issue)

    # Stawka VAT 0-100
    if not _is_empty(item.stawka_vat):
        vat_rate = _parse_decimal(item.stawka_vat)
        if vat_rate is None:
            issues.append(
                _Issue(
                    field_name="STAWKA_VAT",
                    error_code="INVALID_AMOUNT",
                    error_message=f"STAWKA_VAT: '{item.stawka_vat}' nie jest liczbą",
                )
            )
        elif not (Decimal("0") <= vat_rate <= Decimal("100")):
            issues.append(
                _Issue(
                    field_name="STAWKA_VAT",
                    error_code="INVALID_AMOUNT",
                    error_message=f"STAWKA_VAT musi być w zakresie 0–100, podano: {item.stawka_vat}",
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Wynik walidacji importu
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    import_id: int
    total_invoices: int
    invalid_invoices: int
    total_errors: int
    total_warnings: int
    new_status: str  # "VALIDATED" albo "ERROR"

    errors: List[dict] = field(default_factory=list)  # lista dla odpowiedzi API


# ---------------------------------------------------------------------------
# Główna funkcja walidacji
# ---------------------------------------------------------------------------


def validate_import(db: Session, import_id: int) -> ValidationResult:
    """
    Uruchamia pełną walidację wszystkich faktur staging dla danego importu.

    Zapis:
    - Usuwa poprzednie błędy walidacji dla tego importu.
    - Zapisuje nowe rekordy ValidationError.
    - Aktualizuje flagę StagingInvoice.is_valid.
    - Aktualizuje Import.status → VALIDATED lub ERROR.
    - Aktualizuje Import.error_count.

    Zwraca ValidationResult z podsumowaniem.
    """
    # -- Wczytaj faktury staging --
    invoices: List[StagingInvoice] = (
        db.query(StagingInvoice)
        .filter(StagingInvoice.import_id == import_id)
        .all()
    )

    # -- Wczytaj pozycje staging (pogrupowane wg numer_faktury) --
    items: List[StagingInvoiceItem] = (
        db.query(StagingInvoiceItem)
        .filter(StagingInvoiceItem.import_id == import_id)
        .all()
    )
    items_by_invoice: dict[str, List[StagingInvoiceItem]] = {}
    for item in items:
        key = (item.numer_faktury or "").strip()
        items_by_invoice.setdefault(key, []).append(item)

    # -- Usuń poprzednie błędy dla tego importu --
    db.query(ValidationError).filter(
        ValidationError.import_id == import_id
    ).delete(synchronize_session=False)

    # -- Waliduj każdą fakturę --
    total_errors = 0
    total_warnings = 0
    invalid_invoices = 0
    new_error_records: List[ValidationError] = []

    for inv in invoices:
        inv_issues = _validate_invoice(inv)

        # Sprawdź ostrzeżenie o braku pozycji (jeśli plik pozycji był importowany)
        invoice_key = (inv.numer_faktury or "").strip()
        if items and invoice_key not in items_by_invoice:
            inv_issues.append(
                _Issue(
                    field_name="NUMER_FAKTURY",
                    error_code="MISSING_ITEMS",
                    error_message=(
                        f"Faktura '{inv.numer_faktury}' nie ma pozycji "
                        "w pliku pozycji (staging_invoice_items)"
                    ),
                    severity="WARNING",
                )
            )

        # Waliduj pozycje powiązane z tą fakturą
        for item in items_by_invoice.get(invoice_key, []):
            item_issues = _validate_item(item)
            for issue in item_issues:
                new_error_records.append(
                    ValidationError(
                        import_id=import_id,
                        staging_invoice_id=inv.id,
                        row_number=item.row_number,
                        field_name=issue.field_name,
                        error_code=issue.error_code,
                        error_message=issue.error_message,
                        severity=issue.severity,
                    )
                )
                if issue.severity == "ERROR":
                    total_errors += 1
                else:
                    total_warnings += 1

        has_error = any(i.severity == "ERROR" for i in inv_issues)
        inv.is_valid = not has_error

        if has_error:
            invalid_invoices += 1

        for issue in inv_issues:
            new_error_records.append(
                ValidationError(
                    import_id=import_id,
                    staging_invoice_id=inv.id,
                    row_number=inv.row_number,
                    field_name=issue.field_name,
                    error_code=issue.error_code,
                    error_message=issue.error_message,
                    severity=issue.severity,
                )
            )
            if issue.severity == "ERROR":
                total_errors += 1
            else:
                total_warnings += 1

    # -- Zapisz błędy --
    db.bulk_save_objects(new_error_records)

    # -- Aktualizuj import --
    import_record: Optional[Import] = db.get(Import, import_id)
    new_status = "ERROR" if total_errors > 0 else "VALIDATED"
    if import_record:
        import_record.status = new_status
        import_record.error_count = total_errors

    db.commit()

    return ValidationResult(
        import_id=import_id,
        total_invoices=len(invoices),
        invalid_invoices=invalid_invoices,
        total_errors=total_errors,
        total_warnings=total_warnings,
        new_status=new_status,
    )


# ---------------------------------------------------------------------------
# Odczyt błędów walidacji
# ---------------------------------------------------------------------------


def get_validation_errors(
    db: Session,
    import_id: int,
    severity: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[int, List[ValidationError]]:
    query = db.query(ValidationError).filter(
        ValidationError.import_id == import_id
    )
    if severity:
        query = query.filter(ValidationError.severity == severity.upper())
    if is_resolved is not None:
        query = query.filter(ValidationError.is_resolved == is_resolved)
    total = query.count()
    items = (
        query.order_by(ValidationError.row_number, ValidationError.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, items


def resolve_validation_error(
    db: Session, error_id: int, is_resolved: bool = True
) -> Optional[ValidationError]:
    err = db.get(ValidationError, error_id)
    if not err:
        return None
    err.is_resolved = is_resolved
    db.commit()
    db.refresh(err)
    return err
