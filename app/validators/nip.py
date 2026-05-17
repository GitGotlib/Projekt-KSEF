def validate_nip(value: str) -> str:
    """
    Walidacja polskiego NIP (Numer Identyfikacji Podatkowej).
    Usuwa myślniki i spacje, sprawdza 10 cyfr oraz cyfrę kontrolną.
    """
    nip = value.replace("-", "").replace(" ", "")
    if not nip.isdigit() or len(nip) != 10:
        raise ValueError("NIP musi składać się z dokładnie 10 cyfr")

    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(int(nip[i]) * weights[i] for i in range(9)) % 11

    if checksum == 10:
        raise ValueError("Nieprawidłowy NIP (błąd sumy kontrolnej)")
    if checksum != int(nip[9]):
        raise ValueError("Nieprawidłowy NIP (błąd sumy kontrolnej)")

    return nip
