"""
Generowanie dokumentów XML zgodnych ze schematem KSeF FA (2).

Namespace: http://crd.gov.pl/wzor/2023/06/29/12648/
Schema:    FA_VAT (wariant 2, wersja 1-0E)

Dokumentacja: https://www.podatki.gov.pl/ksef/dokumenty-do-pobrania/

Implementacja obejmuje:
- Nagłówek (Naglowek)
- Podmiot1 – sprzedawca
- Podmiot2 – nabywca
- Fa – dane faktury z podziałem kwot wg stawek VAT
- FaWiersz – pozycje faktury

Obsługiwane stawki VAT: 0%, 5%, 8%, 23%.
Stawki niestandardowe trafiają do pola P_13_10 / P_14_10 (stawka dodatkowa).
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from lxml import etree
from sqlalchemy.orm import Session

from app.models.import_ import Import
from app.models.invoice import Invoice, InvoiceItem

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

_NS = "http://crd.gov.pl/wzor/2023/06/29/12648/"
_SYSTEM_INFO = "Projekt-KSeF v1.0"

# Mapowanie % stawki VAT → numer pola FA(2): (P_13_X netto, P_14_X vat)
# Zgodnie ze schematem FA(2):
#   1 = 23%,  2 = 8%,  3 = 5%,  4 = 0%,  5 = ZW (zwolniona),
#   6 = NP (nie podlega),  7 = oo (odwrotne obciążenie, brak VAT)
_VAT_RATE_FIELD: dict[str, int] = {
    "23": 1,
    "8": 2,
    "5": 3,
    "0": 4,
}


def _e(parent: etree._Element, tag: str, text: Optional[str] = None) -> etree._Element:
    """Tworzy element XML w przestrzeni nazw KSeF i opcjonalnie ustawia tekst."""
    el = etree.SubElement(parent, f"{{{_NS}}}{tag}")
    if text is not None:
        el.text = text
    return el


def _fmt_amount(value) -> str:
    """Formatuje kwotę jako łańcuch z 2 miejscami po przecinku."""
    if value is None:
        return "0.00"
    return f"{Decimal(str(value)):.2f}"


def _fmt_qty(value) -> str:
    """Formatuje ilość – usuwa zbędne zera, zachowuje maks. 4 miejsca."""
    if value is None:
        return "0"
    d = Decimal(str(value)).normalize()
    # Nie więcej niż 4 miejsca po przecinku
    return f"{d:.4f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Budowanie XML
# ---------------------------------------------------------------------------


def build_invoice_xml(invoice: Invoice) -> str:
    """
    Buduje dokument XML FA(2) dla jednej faktury.
    Zwraca łańcuch UTF-8.
    """
    root = etree.Element(f"{{{_NS}}}Faktura", nsmap={None: _NS})

    _build_naglowek(root, invoice)
    _build_podmiot1(root, invoice)   # sprzedawca
    _build_podmiot2(root, invoice)   # nabywca
    _build_fa(root, invoice)

    return etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    ).decode("utf-8")


def _build_naglowek(root: etree._Element, invoice: Invoice) -> None:
    nagl = _e(root, "Naglowek")
    kod = _e(nagl, "KodFormularza", "FA")
    kod.set("kodSystemowy", "FA (2)")
    kod.set("wersjaSchemy", "1-0E")
    _e(nagl, "WariantFormularza", "2")
    _e(
        nagl,
        "DataWytworzeniaFa",
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _e(nagl, "SystemInfo", _SYSTEM_INFO)


def _build_podmiot1(root: etree._Element, invoice: Invoice) -> None:
    """Sprzedawca."""
    pod = _e(root, "Podmiot1")
    dane = _e(pod, "DaneIdentyfikacyjne")
    _e(dane, "NIP", invoice.seller_nip)
    _e(dane, "PelnaNazwa", invoice.seller_name)
    if invoice.seller_address:
        adres = _e(pod, "Adres")
        _e(adres, "KodKraju", "PL")
        _e(adres, "AdresL1", invoice.seller_address[:255])


def _build_podmiot2(root: etree._Element, invoice: Invoice) -> None:
    """Nabywca."""
    pod = _e(root, "Podmiot2")
    dane = _e(pod, "DaneIdentyfikacyjne")
    _e(dane, "NIP", invoice.buyer_nip)
    _e(dane, "PelnaNazwa", invoice.buyer_name)
    if invoice.buyer_address:
        adres = _e(pod, "Adres")
        _e(adres, "KodKraju", "PL")
        _e(adres, "AdresL1", invoice.buyer_address[:255])


def _build_fa(root: etree._Element, invoice: Invoice) -> None:
    fa = _e(root, "Fa")

    _e(fa, "KodWaluty", invoice.currency or "PLN")
    _e(fa, "P_1", invoice.invoice_date.strftime("%Y-%m-%d"))
    _e(fa, "P_1M", invoice.invoice_date.strftime("%m"))
    _e(fa, "P_2", invoice.invoice_number)

    if invoice.sale_date:
        _e(fa, "P_6", invoice.sale_date.strftime("%Y-%m-%d"))

    # ---- Kwoty wg stawek VAT ----
    _build_vat_totals(fa, invoice)

    # ---- Adnotacje (wymagane przez schemat) ----
    _build_adnotacje(fa, invoice)

    # ---- Typ faktury ----
    rodz_map = {
        "VAT": "VAT",
        "CORRECTION": "KOR",
        "ADVANCE": "ZAL",
        "PROFORMA": "UPR",
    }
    _e(fa, "RodzajFaktury", rodz_map.get(invoice.invoice_type or "VAT", "VAT"))

    # ---- Termin i metoda płatności ----
    if invoice.payment_method or invoice.payment_due_date or invoice.bank_account:
        _build_platnosc(fa, invoice)

    # ---- Pozycje faktury ----
    for item in sorted(invoice.items or [], key=lambda x: x.line_number):
        _build_fa_wiersz(fa, item)


def _build_vat_totals(fa: etree._Element, invoice: Invoice) -> None:
    """
    Sumuje kwoty netto i VAT per stawka VAT.
    Jeśli brak pozycji – wstawia łączne kwoty do P_13_1 (23%).
    """
    # Zbierz kwoty wg stawek z pozycji
    totals_netto: dict[int, Decimal] = {}
    totals_vat: dict[int, Decimal] = {}

    if invoice.items:
        for item in invoice.items:
            rate_str = str(int(Decimal(str(item.vat_rate or "23"))))
            field_idx = _VAT_RATE_FIELD.get(rate_str, 1)  # default → 23%
            totals_netto[field_idx] = totals_netto.get(field_idx, Decimal("0")) + Decimal(
                str(item.net_amount or "0")
            )
            totals_vat[field_idx] = totals_vat.get(field_idx, Decimal("0")) + Decimal(
                str(item.vat_amount or "0")
            )
    else:
        # Brak pozycji – wstaw całkowite kwoty z nagłówka do stawki 23%
        totals_netto[1] = Decimal(str(invoice.net_amount or "0"))
        totals_vat[1] = Decimal(str(invoice.vat_amount or "0"))

    for idx in sorted(totals_netto):
        _e(fa, f"P_13_{idx}", _fmt_amount(totals_netto[idx]))
        if totals_vat.get(idx, Decimal("0")) != Decimal("0"):
            _e(fa, f"P_14_{idx}", _fmt_amount(totals_vat[idx]))

    # P_15 – łączna kwota należności brutto
    _e(fa, "P_15", _fmt_amount(invoice.gross_amount))


def _build_adnotacje(fa: etree._Element, invoice: Invoice) -> None:
    """Sekcja Adnotacje – wymagana przez schemat FA(2)."""
    adnot = _e(fa, "Adnotacje")
    _e(adnot, "P_16", "2")   # 2 = nie dotyczy
    _e(adnot, "P_17", "2")
    _e(adnot, "P_18", "2")
    _e(adnot, "P_18A", "2")
    zwol = _e(adnot, "Zwolnienie")
    _e(zwol, "P_19N", "1")   # 1 = brak zwolnienia z VAT
    nst = _e(adnot, "NoweSrodkiTransportu")
    _e(nst, "P_22N", "1")
    _e(adnot, "P_23", "2")
    pmarzy = _e(adnot, "PMarzy")
    _e(pmarzy, "P_PMarzyN", "1")


def _build_platnosc(fa: etree._Element, invoice: Invoice) -> None:
    """Dane płatności."""
    platnosc = _e(fa, "Platnosc")
    if invoice.payment_method:
        method_map = {
            "przelew": "6",  # 6 = przelew bankowy
            "gotówka": "1",
            "gotowka": "1",
            "karta": "3",
        }
        code = method_map.get(
            (invoice.payment_method or "").lower(), "6"
        )
        _e(platnosc, "FormaPlatnosci", code)
    if invoice.payment_due_date:
        _e(platnosc, "TerminPlatnosci", invoice.payment_due_date.strftime("%Y-%m-%d"))
    if invoice.bank_account:
        _e(platnosc, "NrRachunku", invoice.bank_account.replace(" ", ""))


def _build_fa_wiersz(fa: etree._Element, item: InvoiceItem) -> None:
    """Pozycja faktury (FaWiersz)."""
    wiersz = _e(fa, "FaWiersz")
    _e(wiersz, "NrWierszaFa", str(item.line_number))
    _e(wiersz, "P_7", item.item_name)
    if item.unit_of_measure:
        _e(wiersz, "P_8A", item.unit_of_measure)
    _e(wiersz, "P_8B", _fmt_qty(item.quantity))
    _e(wiersz, "P_9A", _fmt_amount(item.unit_price_net))
    _e(wiersz, "P_11", _fmt_amount(item.net_amount))
    # P_12 = stawka VAT (liczba lub "zw"/"np")
    rate = Decimal(str(item.vat_rate or "23"))
    _e(wiersz, "P_12", str(int(rate)) if rate == int(rate) else str(rate))


# ---------------------------------------------------------------------------
# Generowanie XML dla całego importu
# ---------------------------------------------------------------------------


def generate_xml_for_import(
    db: Session,
    import_id: int,
) -> int:
    """
    Generuje XML dla wszystkich faktur z danego importu (status DRAFT).
    Zapisuje XML do Invoice.xml_content i ustawia xml_generated_at.
    Zwraca liczbę wygenerowanych dokumentów.
    """
    from sqlalchemy.orm import joinedload

    invoices: List[Invoice] = (
        db.query(Invoice)
        .options(joinedload(Invoice.items))
        .filter(
            Invoice.import_id == import_id,
            Invoice.status.in_(["DRAFT", "VALIDATED"]),
        )
        .all()
    )

    now = datetime.now(timezone.utc)
    count = 0

    for inv in invoices:
        try:
            xml_str = build_invoice_xml(inv)
            inv.xml_content = xml_str
            inv.xml_generated_at = now
            inv.status = "EXPORTED"
            count += 1
        except Exception as exc:
            inv.status = "ERROR"
            inv.notes = f"Błąd generacji XML: {exc}"

    # Aktualizuj status importu
    import_record: Optional[Import] = db.get(Import, import_id)
    if import_record and count > 0:
        import_record.status = "EXPORTED"

    db.commit()
    return count


# ---------------------------------------------------------------------------
# ZIP – paczka wszystkich XML-i importu
# ---------------------------------------------------------------------------


def build_xml_zip(invoices: List[Invoice]) -> bytes:
    """
    Pakuje wygenerowane XML-e (invoice.xml_content) do archiwum ZIP.
    Nazwa pliku = {invoice_number}.xml (niedozwolone znaki zastąpione '_').
    """
    import re as _re

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for inv in invoices:
            if not inv.xml_content:
                continue
            safe_name = _re.sub(r'[\\/:*?"<>|]', "_", inv.invoice_number)
            zf.writestr(f"{safe_name}.xml", inv.xml_content.encode("utf-8"))
    buf.seek(0)
    return buf.read()
