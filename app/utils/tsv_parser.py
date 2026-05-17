"""
Parsowanie i walidacja plików TSV importowanych do systemu KSeF.

Plik TSV musi spełniać:
- separator: TAB
- pierwszy wiersz: nagłówki (wielkość liter ignorowana)
- wszystkie wiersze muszą mieć ten sam ID_FIRMY
- plik nie może być pusty
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set

# ---------------------------------------------------------------------------
# Oczekiwane nagłówki
# ---------------------------------------------------------------------------

# Nagłówki wymagane – ich brak powoduje błąd krytyczny
INVOICE_REQUIRED_HEADERS: Set[str] = {
    "ID_FIRMY",
    "NUMER_FAKTURY",
    "DATA_WYSTAWIENIA",
    "NIP_SPRZEDAWCY",
    "NAZWA_SPRZEDAWCY",
    "NIP_NABYWCY",
    "NAZWA_NABYWCY",
    "WARTOSC_NETTO",
    "KWOTA_VAT",
    "WARTOSC_BRUTTO",
}

ITEM_REQUIRED_HEADERS: Set[str] = {
    "ID_FIRMY",
    "NUMER_FAKTURY",
    "LP",
    "NAZWA_TOWARU_USLUGI",
    "ILOSC",
    "WARTOSC_NETTO",
    "KWOTA_VAT",
    "WARTOSC_BRUTTO",
}

# Pełna lista nagłówków (wymagane + opcjonalne) – kolejność kolumn w staging
INVOICE_COLUMNS: List[str] = [
    "ID_FIRMY",
    "NUMER_FAKTURY",
    "DATA_WYSTAWIENIA",
    "DATA_SPRZEDAZY",
    "TYP_FAKTURY",
    "NIP_SPRZEDAWCY",
    "NAZWA_SPRZEDAWCY",
    "ADRES_SPRZEDAWCY",
    "NIP_NABYWCY",
    "NAZWA_NABYWCY",
    "ADRES_NABYWCY",
    "WARTOSC_NETTO",
    "KWOTA_VAT",
    "WARTOSC_BRUTTO",
    "WALUTA",
    "TERMIN_PLATNOSCI",
    "SPOSOB_PLATNOSCI",
    "NUMER_KONTA",
]

ITEM_COLUMNS: List[str] = [
    "ID_FIRMY",
    "NUMER_FAKTURY",
    "LP",
    "NAZWA_TOWARU_USLUGI",
    "JEDNOSTKA_MIARY",
    "ILOSC",
    "CENA_JEDNOSTKOWA_NETTO",
    "STAWKA_VAT",
    "WARTOSC_NETTO",
    "KWOTA_VAT",
    "WARTOSC_BRUTTO",
]


# ---------------------------------------------------------------------------
# Wynik parsowania
# ---------------------------------------------------------------------------


@dataclass
class TsvParseResult:
    headers: List[str]
    rows: List[Dict[str, str]]
    id_firmy: str
    errors: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def row_count(self) -> int:
        return len(self.rows)


# ---------------------------------------------------------------------------
# Parsowanie
# ---------------------------------------------------------------------------


def parse_and_validate_tsv(content: str, file_type: str) -> TsvParseResult:
    """
    Parsuje i waliduje zawartość pliku TSV.

    :param content: Zdekodowana (UTF-8) zawartość pliku.
    :param file_type: ``"invoices"`` albo ``"items"``.
    :raises ValueError: Gdy file_type jest nieznany.
    """
    if file_type not in ("invoices", "items"):
        raise ValueError(f"Nieznany typ pliku: '{file_type}'. Dozwolone: invoices, items")

    errors: List[str] = []

    # Usuń BOM (UTF-8 with BOM)
    content = content.lstrip("\ufeff")

    # Normalizuj końce linii, usuń puste wiersze
    lines = [
        line
        for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]

    if not lines:
        return TsvParseResult(
            headers=[], rows=[], id_firmy="", errors=["Plik jest pusty"]
        )

    # ---- Nagłówki ----
    raw_headers = lines[0].split("\t")
    headers = [h.strip().upper() for h in raw_headers]

    # Sprawdź unikalność nagłówków
    if len(headers) != len(set(headers)):
        errors.append("Nagłówki nie są unikalne")

    # Sprawdź wymagane nagłówki
    required = INVOICE_REQUIRED_HEADERS if file_type == "invoices" else ITEM_REQUIRED_HEADERS
    missing = required - set(headers)
    if missing:
        errors.append(f"Brak wymaganych kolumn: {', '.join(sorted(missing))}")

    # ---- Wiersze danych ----
    rows: List[Dict[str, str]] = []
    id_firmy_values: Set[str] = set()

    for line_no, line in enumerate(lines[1:], start=2):
        values = line.split("\t")
        # Uzupełnij do liczby nagłówków
        while len(values) < len(headers):
            values.append("")
        row: Dict[str, str] = {
            headers[j]: values[j].strip() for j in range(len(headers))
        }
        rows.append(row)

        company_id = row.get("ID_FIRMY", "").strip()
        if company_id:
            id_firmy_values.add(company_id)

    if not rows:
        errors.append("Plik nie zawiera wierszy danych (tylko nagłówek)")

    # ---- Spójność ID_FIRMY ----
    if len(id_firmy_values) > 1:
        errors.append(
            f"Niespójny ID_FIRMY: wiele wartości w jednym pliku: "
            f"{', '.join(sorted(id_firmy_values))}"
        )

    id_firmy = next(iter(id_firmy_values), "")
    if not id_firmy and not errors:
        errors.append("Kolumna ID_FIRMY jest pusta we wszystkich wierszach")

    return TsvParseResult(
        headers=headers,
        rows=rows,
        id_firmy=id_firmy,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Pomocnicze escape'owanie dla PostgreSQL COPY TEXT
# ---------------------------------------------------------------------------


def escape_copy_value(value: str) -> str:
    """
    Escape'uje wartość do formatu PostgreSQL COPY TEXT.
    Pusta wartość zwracana jest jako pusty string (NULL '' w poleceniu COPY).
    """
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
