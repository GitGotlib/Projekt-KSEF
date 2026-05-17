"""
Serwis transformacji: staging → tabele docelowe (Invoice, InvoiceItem).

Transformacja działa tylko dla rekordów z is_valid=True.
Faktury już istniejące w tabeli invoices (ten sam client_id + invoice_number)
są pomijane (idempotentność).

Wynik transformacji:
- Nowe rekordy Invoice ze statusem DRAFT.
- Powiązane rekordy InvoiceItem.
- Import.status pozostaje VALIDATED – zmienia się dopiero po generacji XML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.import_ import Import
from app.models.invoice import Invoice, InvoiceItem
from app.models.staging import StagingInvoice, StagingInvoiceItem

# ---------------------------------------------------------------------------
# Mapowanie typów faktur staging → Invoice.invoice_type
# ---------------------------------------------------------------------------

_INVOICE_TYPE_MAP = {
    "VAT": "VAT",
    "KOREKTA": "CORRECTION",
    "ZALICZKOWA": "ADVANCE",
    "UPROSZCZONA": "PROFORMA",
    "RR": "VAT",  # faktura rolnicza → traktowana jak VAT
}


# ---------------------------------------------------------------------------
# Pomocnicze konwersje
# ---------------------------------------------------------------------------


def _to_decimal(value: Optional[str], default: Decimal = Decimal("0")) -> Decimal:
    if not value or not value.strip():
        return default
    try:
        return Decimal(value.strip().replace(",", "."))
    except (DecimalException, InvalidOperation):
        return default


def _to_date(value: Optional[str]) -> Optional[date]:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _clean_nip(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[\s\-]", "", value.strip())


def _map_invoice_type(value: Optional[str]) -> str:
    if not value:
        return "VAT"
    return _INVOICE_TYPE_MAP.get(value.strip().upper(), "VAT")


# ---------------------------------------------------------------------------
# Wynik transformacji
# ---------------------------------------------------------------------------


@dataclass
class TransformResult:
    import_id: int
    created: int       # liczba nowych faktur
    skipped: int       # pominięte (duplikaty)
    failed: int        # błędy konwersji


# ---------------------------------------------------------------------------
# Główna funkcja transformacji
# ---------------------------------------------------------------------------


def transform_import(db: Session, import_id: int) -> TransformResult:
    """
    Przekształca zwalidowane faktury staging → Invoice + InvoiceItem.

    Warunki wstępne:
    - Import musi mieć status VALIDATED.
    - Pobierane są tylko StagingInvoice z is_valid=True.

    Idempotentność:
    - Jeśli Invoice (client_id, invoice_number) już istnieje – wiersz pominięty.
    """
    # Pobierz import
    import_record: Optional[Import] = db.get(Import, import_id)
    if not import_record:
        raise ValueError(f"Import {import_id} nie istnieje")

    # Pobierz zwalidowane faktury staging
    staging_invoices: List[StagingInvoice] = (
        db.query(StagingInvoice)
        .filter(
            StagingInvoice.import_id == import_id,
            StagingInvoice.is_valid == True,  # noqa: E712
        )
        .all()
    )

    # Pobierz pozycje staging (pogrupowane wg numer_faktury)
    staging_items: List[StagingInvoiceItem] = (
        db.query(StagingInvoiceItem)
        .filter(StagingInvoiceItem.import_id == import_id)
        .all()
    )
    items_map: dict[str, List[StagingInvoiceItem]] = {}
    for item in staging_items:
        key = (item.numer_faktury or "").strip()
        items_map.setdefault(key, []).append(item)

    created = 0
    skipped = 0
    failed = 0

    for stg in staging_invoices:
        # Sprawdź duplikat
        existing = (
            db.query(Invoice)
            .filter(
                Invoice.client_id == import_record.client_id,
                Invoice.invoice_number == (stg.numer_faktury or "").strip(),
            )
            .first()
        )
        if existing:
            skipped += 1
            continue

        try:
            invoice = _build_invoice(stg, import_record)
            db.add(invoice)
            db.flush()  # generuje invoice.id

            # Pozycje
            inv_key = (stg.numer_faktury or "").strip()
            for stg_item in sorted(
                items_map.get(inv_key, []),
                key=lambda x: int(x.lp or "0") if (x.lp or "0").isdigit() else 0,
            ):
                line = _build_invoice_item(stg_item, invoice.id)
                if line:
                    db.add(line)

            created += 1

        except Exception:
            failed += 1
            db.rollback()
            continue

    db.commit()
    return TransformResult(
        import_id=import_id,
        created=created,
        skipped=skipped,
        failed=failed,
    )


def _build_invoice(stg: StagingInvoice, import_record: Import) -> Invoice:
    return Invoice(
        client_id=import_record.client_id,
        user_id=import_record.user_id,
        import_id=import_record.id,
        invoice_number=(stg.numer_faktury or "").strip(),
        invoice_date=_to_date(stg.data_wystawienia) or date.today(),
        sale_date=_to_date(stg.data_sprzedazy),
        invoice_type=_map_invoice_type(stg.typ_faktury),
        seller_nip=_clean_nip(stg.nip_sprzedawcy),
        seller_name=(stg.nazwa_sprzedawcy or "").strip(),
        seller_address=(stg.adres_sprzedawcy or "").strip() or None,
        buyer_nip=_clean_nip(stg.nip_nabywcy),
        buyer_name=(stg.nazwa_nabywcy or "").strip(),
        buyer_address=(stg.adres_nabywcy or "").strip() or None,
        net_amount=_to_decimal(stg.wartosc_netto),
        vat_amount=_to_decimal(stg.kwota_vat),
        gross_amount=_to_decimal(stg.wartosc_brutto),
        currency=(stg.waluta or "PLN").strip().upper(),
        payment_method=(stg.sposob_platnosci or "").strip() or None,
        payment_due_date=_to_date(stg.termin_platnosci),
        bank_account=(stg.numer_konta or "").strip() or None,
        status="DRAFT",
    )


def _build_invoice_item(
    stg: StagingInvoiceItem, invoice_id: int
) -> Optional[InvoiceItem]:
    line_num = int(stg.lp) if stg.lp and stg.lp.strip().isdigit() else 1
    quantity = _to_decimal(stg.ilosc, Decimal("1"))
    unit_price = _to_decimal(stg.cena_jednostkowa_netto)
    net_amount = _to_decimal(stg.wartosc_netto)
    vat_amount = _to_decimal(stg.kwota_vat)
    gross_amount = _to_decimal(stg.wartosc_brutto)
    vat_rate = _to_decimal(stg.stawka_vat)

    # Oblicz brakujące pola z dostępnych danych
    if unit_price == 0 and quantity != 0 and net_amount != 0:
        unit_price = (net_amount / quantity).quantize(Decimal("0.0001"))

    return InvoiceItem(
        invoice_id=invoice_id,
        line_number=line_num,
        item_name=(stg.nazwa_towaru_uslugi or "").strip() or "—",
        unit_of_measure=(stg.jednostka_miary or "").strip() or None,
        quantity=quantity,
        unit_price_net=unit_price,
        vat_rate=vat_rate,
        net_amount=net_amount,
        vat_amount=vat_amount,
        gross_amount=gross_amount,
    )


# ---------------------------------------------------------------------------
# Odczyt faktur dla importu
# ---------------------------------------------------------------------------


def get_invoices_for_import(db: Session, import_id: int) -> List[Invoice]:
    from sqlalchemy.orm import joinedload

    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items))
        .filter(Invoice.import_id == import_id)
        .all()
    )
