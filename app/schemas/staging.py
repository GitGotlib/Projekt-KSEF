from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StagingInvoiceResponse(BaseModel):
    """
    Odczyt surowych danych faktury ze strefy staging.
    Wszystkie pola biznesowe są typu str – brak konwersji typów.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    import_id: int
    row_number: Optional[int]

    id_firmy: Optional[str]
    numer_faktury: Optional[str]
    data_wystawienia: Optional[str]
    data_sprzedazy: Optional[str]
    typ_faktury: Optional[str]
    nip_sprzedawcy: Optional[str]
    nazwa_sprzedawcy: Optional[str]
    adres_sprzedawcy: Optional[str]
    nip_nabywcy: Optional[str]
    nazwa_nabywcy: Optional[str]
    adres_nabywcy: Optional[str]
    wartosc_netto: Optional[str]
    kwota_vat: Optional[str]
    wartosc_brutto: Optional[str]
    waluta: Optional[str]
    termin_platnosci: Optional[str]
    sposob_platnosci: Optional[str]
    numer_konta: Optional[str]

    is_valid: Optional[bool]
    created_at: datetime


class StagingInvoiceItemResponse(BaseModel):
    """
    Odczyt surowej pozycji faktury ze strefy staging.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    import_id: int
    staging_invoice_id: Optional[int]
    row_number: Optional[int]

    id_firmy: Optional[str]
    numer_faktury: Optional[str]
    lp: Optional[str]
    nazwa_towaru_uslugi: Optional[str]
    jednostka_miary: Optional[str]
    ilosc: Optional[str]
    cena_jednostkowa_netto: Optional[str]
    stawka_vat: Optional[str]
    wartosc_netto: Optional[str]
    kwota_vat: Optional[str]
    wartosc_brutto: Optional[str]

    is_valid: Optional[bool]
    created_at: datetime
