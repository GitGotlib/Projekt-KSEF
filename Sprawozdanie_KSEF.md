# Sprawozdanie z projektu

## System Przetwarzania Faktur KSeF

**Autor projektu:** Hlib Filobok 335809

---

## 1. Opis zadania

Celem projektu było zaprojektowanie i wykonanie backendowej aplikacji webowej realizującej pełny potok przetwarzania faktur elektronicznych zgodnych ze standardem **KSeF** (Krajowy System e-Faktur – Ministerstwo Finansów RP).

System obsługuje następujący przepływ danych:

1. Przyjęcie pliku TSV z fakturami od klienta (firmy)
2. Załadowanie surowych danych do strefy staging w bazie danych
3. Walidację biznesową (NIP, daty, kwoty, waluty, typy faktur)
4. Transformację zwalidowanych danych do struktury docelowej
5. Generowanie plików XML zgodnych ze schematem KSeF FA(2) Ministerstwa Finansów
6. Eksport archiwum ZIP z wygenerowanymi plikami XML

Projekt realizowany jest jako **backendowe API REST** bez warstwy frontendowej, z pełną dokumentacją Swagger dostępną pod adresem `http://localhost:8000/docs`.

Dowód uruchomienia aplikacji w kontenerze Docker:

![Dowód uruchomienia aplikacji](uruchomienie_dockera.png)

---

## 2. Zakres funkcjonalny

### 2.1 Zarządzanie użytkownikami i autoryzacja

- Rejestracja użytkowników przez administratora
- Logowanie z użyciem OAuth2 Password Flow i generowaniem tokenu JWT (HS256)
- Dwa poziomy uprawnień: `admin` (pełen dostęp) i `user` (odczyt i własne operacje)
- Dezaktywacja kont użytkowników (soft delete)

### 2.2 Zarządzanie klientami

- Rejestracja firm (klientów) z walidacją numeru NIP i identyfikatora `ID_FIRMY`
- Wyszukiwanie klientów po nazwie, NIP lub ID_FIRMY z paginacją

### 2.3 Import danych z pliku TSV

- Przyjmowanie pliku TSV przez endpoint REST (`multipart/form-data`, limit 50 MB)
- Obsługa dwóch typów plików: faktur nagłówkowych i pozycji faktur
- Weryfikacja nagłówków kolumn i spójności `ID_FIRMY`
- Masowe ładowanie danych do strefy staging przez PostgreSQL `COPY FROM STDIN`
- Rejestr importów z metadanymi (data, rozmiar, liczba wierszy, status)

### 2.4 Walidacja biznesowa

- Sprawdzanie wymaganych pól (NULL/empty)
- Walidacja NIP z sumą kontrolną (wagi `[6,5,7,2,3,4,5,6,7]`, mod 11)
- Walidacja formatu dat (`YYYY-MM-DD`) z weryfikacją zakresów
- Walidacja kwot: `WARTOSC_NETTO + KWOTA_VAT = WARTOSC_BRUTTO` (tolerancja 0,01 zł)
- Walidacja kodu waluty (lista ISO 4217)
- Walidacja typu faktury (VAT, KOREKTA, ZALICZKOWA, UPROSZCZONA, RR)
- Zapis błędów walidacji z rozróżnieniem `ERROR`/`WARNING`; ręczne oznaczanie jako rozwiązanych

### 2.5 Transformacja danych (staging → docelowe)

- Przeniesienie tylko poprawnych rekordów (`is_valid = TRUE`) do tabel `invoices` i `invoice_items`
- Mapowanie typów: TEXT z staging → liczby, daty, typy wyliczeniowe
- Idempotentność: ponowne uruchomienie nie duplikuje faktur

### 2.6 Generowanie XML KSeF FA(2)

- Budowanie dokumentu XML wg schematu `FA_VAT` wariant 2 Ministerstwa Finansów
- Namespace: `http://crd.gov.pl/wzor/2023/06/29/12648/`
- Prawidłowe mapowanie stawek VAT na pola `P_13_x` / `P_14_x`
- Generowanie archiwum ZIP (jeden plik XML na fakturę); pobieranie pojedynczego XML

### 2.7 Raportowanie

- Raport miesięczny per klient i miesiąc: sumy kwot, statusy importów, podział wg typów faktur, liczba błędów

### 2.8 Infrastruktura

- Konteneryzacja przez Docker Compose (baza danych + API)
- Konfiguracja przez plik `.env` (DATABASE_URL, SECRET_KEY, ALGORITHM)
- Automatyczna dokumentacja OpenAPI/Swagger (FastAPI)
- Dziennik audytowy operacji (tabela `logs`)

---

## 3. Opis plików źródłowych

### 3.1 Struktura katalogów z opisem plików

```
app/
├── main.py                      # Punkt wejścia – instancja FastAPI, włączenie routerów
├── api/
│   ├── deps.py                  # Zależności DI: get_current_user(), require_admin()
│   ├── __init__.py              # api_router – agregacja wszystkich routerów
│   └── routers/
│       ├── auth.py              # POST /auth/login, /register, GET /auth/me, /users
│       ├── clients.py           # CRUD /clients z paginacją i wyszukiwaniem
│       ├── imports.py           # POST /imports/upload, GET staging-invoices/items
│       ├── invoices.py          # CRUD /invoices z filtrami
│       ├── validation.py        # POST /validation/run, GET/PATCH/DELETE errors
│       ├── ksef.py              # POST transform/generate, GET download (ZIP/XML)
│       └── reports.py           # GET /reports/monthly
├── core/
│   ├── config.py                # Settings (BaseSettings) – czyta z .env
│   └── security.py              # verify_password, get_password_hash, JWT create/decode
├── database/
│   ├── base.py                  # class Base(DeclarativeBase) – baza ORM
│   └── session.py               # engine, SessionLocal, get_db() generator
├── models/
│   ├── enums.py                 # UserRole, ImportStatus, InvoiceType, ValidationSeverity
│   ├── user.py                  # Model User (id, username, email, hashed_password, role…)
│   ├── client.py                # Model Client (NIP, company_id, adres)
│   ├── import_.py               # Model Import (status, miesiąc, pliki)
│   ├── staging.py               # StagingInvoice + StagingInvoiceItem (pola TEXT)
│   ├── invoice.py               # Invoice + InvoiceItem (typowane pola numeryczne)
│   ├── validation_error.py      # ValidationError (kody, severity, is_resolved)
│   ├── log.py                   # Log (BigInteger PK, operacje audytowe)
│   └── comment.py               # Comment (do faktur i importów)
├── schemas/
│   ├── auth.py                  # Token, TokenData (schematy JWT)
│   ├── user.py                  # UserCreate (walidacja hasła, username), UserResponse
│   ├── client.py                # ClientCreate, ClientUpdate, ClientResponse
│   ├── import_.py               # ImportResponse, ImportStatusUpdate
│   ├── invoice.py               # InvoiceCreate, InvoiceResponse (z listą pozycji)
│   ├── staging.py               # StagingInvoiceResponse, StagingInvoiceItemResponse
│   ├── validation_error.py      # ValidationErrorResponse, ValidationErrorResolve
│   ├── common.py                # PaginatedResponse[T] (generyczny schemat stronicowania)
│   ├── log.py                   # LogResponse
│   └── comment.py               # CommentCreate, CommentResponse
├── services/
│   ├── auth_service.py          # get_user_by_*, authenticate_user, create_user
│   ├── client_service.py        # CRUD klientów, wyszukiwanie po NIP/company_id
│   ├── import_service.py        # create_import, COPY do staging, get_staging_*
│   ├── invoice_service.py       # CRUD faktur z filtrami (status, klient, data)
│   ├── validation_service.py    # validate_import() – 8 reguł, zapis errors do bazy
│   ├── transform_service.py     # transform_import() – staging → Invoice (idempotentny)
│   └── ksef_xml_service.py      # build_invoice_xml(), generate_xml_for_import(), ZIP
├── validators/
│   └── nip.py                   # validate_nip() – suma kontrolna polskiego NIP
└── utils/
    └── tsv_parser.py            # parse_and_validate_tsv(), escape_copy_value()

sql/
└── migrations/
    └── 001_initial_schema.sql   # Pełny DDL: 10 tabel, indeksy, CHECK constraints

scripts/
├── create_admin.py              # Interaktywny CLI tworzenia konta admina
├── create_admin_direct.py       # Niinteraktywny skrypt tworzenia admina (dev)
└── seed_db.py                   # Seed bazy – klienci, importy, faktury, błędy walidacji

docker/
└── Dockerfile                   # python:3.11-slim, libpq-dev, pip install requirements

docker-compose.yml               # Serwis db (postgres:16) + api; healthcheck
.env / .env.example              # Konfiguracja: DATABASE_URL, SECRET_KEY, ALGORITHM
requirements.txt                 # Zależności Pythona (fastapi, sqlalchemy, lxml…)
```

### 3.2 Kluczowe fragmenty kodu źródłowego

**Walidator NIP (`validators/nip.py`):**
```python
def validate_nip(value: str) -> str:
    nip = value.replace("-", "").replace(" ", "")
    if not nip.isdigit() or len(nip) != 10:
        raise ValueError("NIP musi składać się z dokładnie 10 cyfr")
    if nip == "0" * 10:
        raise ValueError("NIP nie może składać się z samych zer")
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(int(nip[i]) * weights[i] for i in range(9)) % 11
    if checksum == 10 or checksum != int(nip[9]):
        raise ValueError("Nieprawidłowy NIP (błąd sumy kontrolnej)")
    return nip
```

**Masowy import przez PostgreSQL COPY (`services/import_service.py`):**
```python
raw_conn = engine.raw_connection()
cur = raw_conn.cursor()
cur.copy_expert(
    f"COPY staging_invoices ({columns}) FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t')",
    buffer
)
raw_conn.commit()
```

**Generator XML FA(2) (`services/ksef_xml_service.py`):**
```python
_NS = "http://crd.gov.pl/wzor/2023/06/29/12648/"
_VAT_RATE_FIELD = {"23": 1, "8": 2, "5": 3, "0": 4}

def _e(parent, tag, text=None):
    el = etree.SubElement(parent, f"{{{_NS}}}{tag}")
    if text is not None:
        el.text = text
    return el
```

---

## 4. Pliki użyte do testów

### 4.1 `sample_data/sample_invoices.tsv` – nagłówki faktur

Plik TSV zawierający **3 faktury VAT** wystawione przez firmę FIRMA001 w miesiącu 2024-01.

Kolumny: `ID_FIRMY`, `NUMER_FAKTURY`, `DATA_WYSTAWIENIA`, `DATA_SPRZEDAZY`, `TYP_FAKTURY`, `NIP_SPRZEDAWCY`, `NAZWA_SPRZEDAWCY`, `ADRES_SPRZEDAWCY`, `NIP_NABYWCY`, `NAZWA_NABYWCY`, `ADRES_NABYWCY`, `WARTOSC_NETTO`, `KWOTA_VAT`, `WARTOSC_BRUTTO`, `WALUTA`, `TERMIN_PLATNOSCI`, `SPOSOB_PLATNOSCI`, `NUMER_KONTA`

| Numer faktury | Data | Netto (PLN) | VAT (PLN) | Brutto (PLN) |
|---------------|------|------------|----------|------------|
| FV/2024/01/001 | 2024-01-05 | 1 000,00 | 230,00 | 1 230,00 |
| FV/2024/01/002 | 2024-01-10 | 2 500,00 | 575,00 | 3 075,00 |
| FV/2024/01/003 | 2024-01-15 | 800,00 | 184,00 | 984,00 |
| **Łącznie** | | **4 300,00** | **989,00** | **5 289,00** |

NIP sprzedawcy: `5261040828` (Przykładowa Spółka z o.o.)

### 4.2 `sample_data/sample_items.tsv` – pozycje faktur

Plik TSV zawierający **4 pozycje** powiązane z powyższymi fakturami.

Kolumny: `ID_FIRMY`, `NUMER_FAKTURY`, `LP`, `NAZWA_TOWARU_USLUGI`, `JEDNOSTKA_MIARY`, `ILOSC`, `CENA_JEDNOSTKOWA_NETTO`, `STAWKA_VAT`, `WARTOSC_NETTO`, `KWOTA_VAT`, `WARTOSC_BRUTTO`

| Faktura | LP | Towar/Usługa | J.m. | Ilość | Cena netto | Stawka | Netto |
|---------|-----|--------------|------|-------|-----------|--------|-------|
| FV/2024/01/001 | 1 | Usługa informatyczna | godz. | 10 | 100,00 | 23% | 1 000,00 |
| FV/2024/01/002 | 1 | Licencja na oprogramowanie | szt. | 5 | 300,00 | 23% | 1 500,00 |
| FV/2024/01/002 | 2 | Wdrożenie systemu | godz. | 8 | 125,00 | 23% | 1 000,00 |
| FV/2024/01/003 | 1 | Dostawa sprzętu komputerowego | szt. | 2 | 400,00 | 23% | 800,00 |

### 4.3 Dane seedowe (`scripts/seed_db.py`)

Skrypt automatycznie wypełnia bazę przykładowymi danymi testowymi:

| Tabela | Liczba rekordów | Opis |
|--------|----------------|------|
| `users` | 4 | admin + jan.kowalski, anna.nowak, piotr.wisniew (hasło: Test1234!) |
| `clients` | 3 | FIRMA001 (NIP 5261040828), FIRMA002, FIRMA003 |
| `imports` | 4 | Statusy: VALIDATED, EXPORTED, ERROR, LOADED |
| `staging_invoices` | 8 | W tym 1 z błędnym NIP (test walidacji) |
| `invoices` | 5 | 3×VALIDATED, 2×EXPORTED |
| `validation_errors` | 3 | INVALID_NIP, 2×MISSING_BANK_ACCOUNT |
| `comments` | 3 | Do importu i faktury |
| `logs` | 7 | Operacje audytowe |

---

## 5. Opis realizacji

### 5.1 Schemat pakietów (warstwy aplikacji)

```
┌─────────────────────────────────────────────────────┐
│                   HTTP Request                      │
└───────────────────────┬─────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│   WARSTWA API  (app/api/routers/)                   │
│   FastAPI Router → walidacja Pydantic → Depends     │
└───────────────────────┬─────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│   WARSTWA SERWISÓW  (app/services/)                 │
│   Logika biznesowa, walidacja, XML, transformacja   │
└───────────────────────┬─────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│   WARSTWA ORM  (app/models/ + SQLAlchemy Session)   │
│   Modele tabel, zapytania, transakcje               │
└───────────────────────┬─────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│   BAZA DANYCH  (PostgreSQL 16)                      │
│   10 tabel, CHECK constraints, indeksy, FK          │
└─────────────────────────────────────────────────────┘
```

### 5.2 Schemat bazy danych – kod SQL (fragment `001_initial_schema.sql`)

```sql
-- Tabela użytkowników
CREATE TABLE IF NOT EXISTS users (
    id               SERIAL         PRIMARY KEY,
    username         VARCHAR(100)   NOT NULL UNIQUE,
    email            VARCHAR(255)   NOT NULL UNIQUE,
    hashed_password  VARCHAR(255)   NOT NULL,
    role             VARCHAR(20)    NOT NULL DEFAULT 'user'
                         CHECK (role IN ('admin', 'user')),
    is_active        BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- Klienci z walidacją NIP po stronie bazy
CREATE TABLE IF NOT EXISTS clients (
    id           SERIAL        PRIMARY KEY,
    company_id   VARCHAR(50)   NOT NULL UNIQUE,
    nip          VARCHAR(10)   NOT NULL UNIQUE
                     CHECK (nip ~ '^\d{10}$'),
    company_name VARCHAR(255)  NOT NULL,
    is_active    BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Importy z kontrolą formatu miesiąca
CREATE TABLE IF NOT EXISTS imports (
    id           SERIAL        PRIMARY KEY,
    client_id    INTEGER       NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    user_id      INTEGER       NOT NULL REFERENCES users(id)   ON DELETE RESTRICT,
    import_month VARCHAR(7)    NOT NULL CHECK (import_month ~ '^\d{4}-\d{2}$'),
    status       VARCHAR(20)   NOT NULL DEFAULT 'NEW'
                     CHECK (status IN ('NEW','LOADED','VALIDATED','ERROR','EXPORTED')),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Faktury docelowe z unikalnym numerem per klient
CREATE TABLE IF NOT EXISTS invoices (
    id             SERIAL        PRIMARY KEY,
    client_id      INTEGER       NOT NULL REFERENCES clients(id) ON DELETE RESTRICT,
    import_id      INTEGER       REFERENCES imports(id) ON DELETE SET NULL,
    invoice_number VARCHAR(100)  NOT NULL,
    seller_nip     VARCHAR(10)   NOT NULL CHECK (seller_nip ~ '^\d{10}$'),
    buyer_nip      VARCHAR(10)   NOT NULL CHECK (buyer_nip  ~ '^\d{10}$'),
    net_amount     NUMERIC(15,2) NOT NULL CHECK (net_amount  >= 0),
    vat_amount     NUMERIC(15,2) NOT NULL CHECK (vat_amount  >= 0),
    gross_amount   NUMERIC(15,2) NOT NULL CHECK (gross_amount >= 0),
    status         VARCHAR(20)   NOT NULL DEFAULT 'DRAFT'
                       CHECK (status IN ('DRAFT','VALIDATED','EXPORTED','ERROR')),
    xml_content    TEXT,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_invoices_client_invoice_number UNIQUE (client_id, invoice_number)
);

-- Błędy walidacji z rozróżnieniem ERROR/WARNING
CREATE TABLE IF NOT EXISTS validation_errors (
    id            SERIAL       PRIMARY KEY,
    import_id     INTEGER      NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    invoice_id    INTEGER      REFERENCES invoices(id) ON DELETE CASCADE,
    row_number    INTEGER,
    field_name    VARCHAR(100),
    error_code    VARCHAR(50)  NOT NULL,
    error_message TEXT         NOT NULL,
    severity      VARCHAR(10)  NOT NULL DEFAULT 'ERROR'
                      CHECK (severity IN ('ERROR','WARNING')),
    is_resolved   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## 6. Uzyskane wyniki dla przykładowych plików

### 6.1 Upload pliku `sample_invoices.tsv`

![](import_TSV_2.png)

![](import_TSV.png)

### 6.2 Wynik walidacji dla poprawnego pliku

**Żądanie:** `POST /validation/run/1`

**Odpowiedź (HTTP 200):**
```json
{
  "import_id": 1,
  "total_invoices": 3,
  "invalid_invoices": 0,
  "total_errors": 0,
  "total_warnings": 0,
  "new_status": "VALIDATED",
  "message": "Walidacja zakończona: 3/3 faktur poprawnych."
}
```

### 6.3 Wynik walidacji dla pliku z błędami

**Odpowiedź dla importu zawierającego NIP `0000000000`:**
```json
{
  "import_id": 3,
  "total_invoices": 1,
  "invalid_invoices": 1,
  "total_errors": 1,
  "total_warnings": 1,
  "new_status": "ERROR",
  "message": "Walidacja zakończona: 0/1 faktur poprawnych."
}
```

### 6.4 Wynik transformacji

![](transformacja.png)

### 6.5 Raport miesięczny

![Raport miesięczny](raport.png)

---

## 7. Dowód poprawności walidacji

### 7.1 Algorytm sumy kontrolnej NIP

NIP polega na weryfikacji ostatniej cyfry (kontrolnej) względem sumy ważonej pierwszych 9 cyfr:


$$\text{suma} = \sum_{i=0}^{8} d_i \cdot w_i \quad \text{gdzie} \quad w = [6,5,7,2,3,4,5,6,7]$$

$$d_9 = \text{suma} \bmod 11$$

Jeśli wynik $= 10$ lub $\neq d_9$ → NIP nieprawidłowy.


![przykładowy NIP](good_nip.png)



![przykład błędnego NIP](Nip0.png)

```
**Przykład błędny – NIP `1234567891`:**

1×6 + 2×5 + 3×7 + 4×2 + 5×3 + 6×4 + 7×5 + 8×6 + 9×7
= 6+10+21+8+15+24+35+48+63 = 230
230 mod 11 = 10  → wynik 10 jest niemożliwy → INVALID_NIP
```

### 7.2 Walidacja kwot – tolerancja zaokrągleń

Reguła `AMOUNT_MISMATCH`: sprawdza czy $|\text{netto} + \text{vat} - \text{brutto}| \leq 0{,}01$

| netto | vat | brutto | różnica | wynik |
|-------|-----|--------|---------|-------|
| 1000.00 | 230.00 | 1230.00 | 0.00 | ✓ OK |
| 800.00 | 184.00 | 984.00 | 0.00 | ✓ OK |
| 100.00 | 23.00 | 122.99 | 0.01 | ✓ OK (w tolerancji) |
| 100.00 | 23.00 | 124.00 | 1.00 | ✗ AMOUNT_MISMATCH |

### 7.3 Przykładowy błąd walidacji zwracany przez API

**`GET /validation/errors/3`**

![Przykład wykrycia złego NIP](Error_walidacji.png)

### 7.4 Reguły walidacyjne – podsumowanie

| Kod błędu | Typ | Pole | Opis |
|-----------|-----|------|------|
| `MISSING_FIELD` | ERROR | wszystkie wymagane | Pole puste lub NULL |
| `INVALID_NIP` | ERROR | nip_sprzedawcy, nip_nabywcy | Błąd sumy kontrolnej lub format |
| `INVALID_DATE` | ERROR | data_wystawienia, data_sprzedazy | Niepoprawny format lub zakres |
| `INVALID_AMOUNT` | ERROR | wartosc_netto, kwota_vat, wartosc_brutto | Nie jest liczbą dziesiętną |
| `AMOUNT_MISMATCH` | ERROR | wartosc_brutto | netto + VAT ≠ brutto (tol. 0,01) |
| `INVALID_CURRENCY` | ERROR | waluta | Kod spoza listy ISO 4217 |
| `INVALID_INVOICE_TYPE` | ERROR | typ_faktury | Spoza: VAT/KOREKTA/ZALICZKOWA/… |
| `MISSING_ITEMS` | WARNING | – | Brak pozycji w pliku items |

---

## 8. Dowód poprawności plików XML (walidacja schematu KSeF)

### 8.1 Schemat XSD KSeF FA(2)

Wygenerowane pliki XML muszą być zgodne ze schematem XSD opublikowanym przez Ministerstwo Finansów:

- **Nazwa:** `FA_VAT` wariant 2, wersja `1-0E`
- **Namespace:** `http://crd.gov.pl/wzor/2023/06/29/12648/`
- **Element główny:** `<Faktura>`
- **Źródło:** https://www.podatki.gov.pl/ksef/dokumenty-do-pobrania/

### 8.2 Struktura wygenerowanego XML

![Generacja KSeF](generacja_ksef.png)

![Struktura XML](show_ksef1.png)

![Struktura XML](show_ksef2.png)




### 8.3 Mapowanie stawek VAT na pola FA(2)
```
| Stawka VAT | Pole netto | Pole VAT | Pole pozycji |
|-----------|-----------|---------|-------------|
| 23% | `P_13_1` | `P_14_1` | `P_12 = "23"` |
| 8% | `P_13_2` | `P_14_2` | `P_12 = "8"` |
| 5% | `P_13_3` | `P_14_3` | `P_12 = "5"` |
| 0% | `P_13_4` | — | `P_12 = "0"` |
| inne | `P_13_10` | `P_14_10` | wartość stawki |
```
### 8.4 Weryfikacja poprawności XML przez lxml

```
python
from lxml import etree

# Walidacja względem oficjalnego XSD Ministerstwa Finansów
schema = etree.XMLSchema(etree.parse("FA_VAT(2)_v1-0E.xsd"))
doc = etree.parse("FV_2024_01_001.xml")

is_valid = schema.validate(doc)
print("XML poprawny:", is_valid)

if not is_valid:
    for error in schema.error_log:
        print(f"  Linia {error.line}: {error.message}")
```

---

## 9. Wykorzystane technologie

### 9.1 Backend

- **FastAPI** – framework REST API dla Pythona; obsługa routingu, dependency injection, walidacji wejściowych i generowania dokumentacji OpenAPI/Swagger
- **Python 3.11** – środowisko uruchomieniowe
- **Uvicorn** – serwer ASGI uruchamiający aplikację FastAPI
- **python-multipart** – obsługa przesyłania plików (formularz multipart, `UploadFile`)

### 9.2 Baza danych

- **PostgreSQL 16** – baza `ksef_db` z 10 powiązanymi tabelami
- **SQLAlchemy 2.0** – ORM, mapowanie modeli Python → tabele, zapytania przez sesję
- **Alembic** – narzędzie do migracji schematu bazy danych
- **psycopg2-binary** – sterownik DBAPI do PostgreSQL

### 9.3 Walidacja i schematy danych

- **Pydantic v2** – deklaratywne schematy danych (`BaseModel`), walidatory pól (`@field_validator`), serializacja odpowiedzi API
- **pydantic-settings** – czytanie konfiguracji aplikacji z pliku .env przez klasę `BaseSettings`

### 9.4 Bezpieczeństwo i uwierzytelnianie

- **python-jose[cryptography]** – generowanie i weryfikacja tokenów JWT (HS256)
- **passlib[bcrypt]** + **bcrypt 4.0.1** – haszowanie haseł algorytmem bcrypt
- **OAuth2PasswordBearer** – schemat uwierzytelniania HTTP Bearer (FastAPI)

### 9.5 Generowanie XML

- **lxml** – budowanie dokumentów XML dla schematu KSeF FA(2) (namespace `http://crd.gov.pl/wzor/2023/06/29/12648/`)
- Generowanie archiwów ZIP z plikami XML przez moduł standardowy `zipfile`

### 9.6 Narzędzia wspomagające

- **Docker + Docker Compose** – konteneryzacja aplikacji i bazy danych
- **Git + GitHub** – kontrola wersji
- **VS Code** – środowisko programistyczne
- **python-dotenv** – ładowanie zmiennych środowiskowych z .env

---

## 10. Architektura aplikacji

Aplikacja zbudowana jest jako **monolityczny backend API** oparty na FastAPI z wyraźnym podziałem na warstwy.

### 10.1 Warstwy aplikacji

1. **Warstwa API (Routers)**  
   Pliki w routers — endpointy REST, obsługa żądań HTTP, dependency injection

2. **Warstwa logiki biznesowej (Services)**  
   Pliki w services — walidacja, transformacja, generowanie XML, import TSV

3. **Warstwa danych (Models + Database)**  
   Pliki w models i database — modele SQLAlchemy, sesja, konfiguracja silnika

4. **Warstwa konfiguracji i bezpieczeństwa (Core)**  
   Pliki w core — ustawienia aplikacji (`config.py`), funkcje kryptograficzne (security.py)

Komunikacja między warstwami odbywa się poprzez zależności FastAPI (`Depends`) i sesję SQLAlchemy przekazywaną do serwisów.

### 10.2 Struktura katalogów

```
app/
├── main.py                  # Punkt wejścia FastAPI
├── api/
│   ├── deps.py              # Zależności: get_current_user, require_admin
│   └── routers/             # auth, clients, imports, invoices,
│       ...                  # validation, ksef, reports
├── core/
│   ├── config.py            # Settings (BaseSettings)
│   └── security.py          # JWT, bcrypt
├── database/
│   ├── base.py              # DeclarativeBase
│   └── session.py           # engine, SessionLocal, get_db
├── models/                  # 10 modeli SQLAlchemy
├── schemas/                 # Schematy Pydantic (request/response)
├── services/                # Logika biznesowa
├── validators/              # Walidator NIP
└── utils/                   # Parser TSV
sql/migrations/
    001_initial_schema.sql   # Pełny schemat SQL
scripts/
    create_admin.py          # CLI tworzenia admina
    seed_db.py               # Seed bazy danych
docker/
    Dockerfile
docker-compose.yml
```

---

## 11. Struktura bazy danych i relacje

Baza danych zawiera **10 powiązanych ze sobą tabel** zaprojektowanych relacyjnie.

### 11.1 Główne tabele

![Diagram bazy danych](tablice.png)

| Tabela | Opis |
|--------|------|
| `users` | Użytkownicy systemu (role: `admin`, `user`) |
| `clients` | Klienci — firmy importujące faktury (klucz: `company_id`, `nip`) |
| `imports` | Rekordy wsadów importu (plik TSV, miesiąc, status) |
| `staging_invoices` | Surowe dane faktur z TSV (wszystkie pola jako TEXT) |
| `staging_invoice_items` | Surowe pozycje faktur z TSV |
| `invoices` | Faktury docelowe (typowane pola, po walidacji) |
| `invoice_items` | Pozycje faktur docelowych |
| `validation_errors` | Błędy i ostrzeżenia walidacji |
| `logs` | Dziennik audytowy operacji |
| `comments` | Komentarze administracyjne do faktur/importów |

### 11.2 Relacje między tabelami

- `clients` **1:N** `imports`
- `users` **1:N** `imports`
- `imports` **1:N** `staging_invoices`
- `imports` **1:N** `invoices`
- `staging_invoices` **1:N** `staging_invoice_items`
- `invoices` **1:N** `invoice_items`
- `imports` **1:N** `validation_errors`
- `invoices` **1:N** `validation_errors`
- `users` **1:N** `comments`
- `invoices` **1:N** `comments`

### 11.3 Integralność danych i logika po stronie bazy

- Ograniczenia **UNIQUE** na: `users.username`, `users.email`, `clients.nip`, `clients.company_id`, `invoices(client_id, invoice_number)`
- **CHECK constraints**: format NIP (`^\d{10}$`), format miesiąca (`^\d{4}-\d{2}$`), statusy przez `IN (...)`, wartości nieujemne (`>= 0`)
- Klucze obce z `ON DELETE CASCADE` (staging, items) i `ON DELETE RESTRICT` (faktury, importy)
- Wszystkie tabele posiadają pole `created_at TIMESTAMPTZ DEFAULT NOW()`

---

## 12. API – dostępne endpointy

Backend udostępnia **31 endpointów REST** z pełną dokumentacją Swagger pod adresem `http://localhost:8000/docs`.

### 12.1 Autoryzacja (`/auth`)

!(endpointy_1.png)

!(endpointy_2.png)

| Metoda | Endpoint | Opis | Dostęp |
|--------|----------|------|--------|
| `POST` | `/auth/login` | Logowanie – zwraca token JWT (OAuth2 Password Flow) | Publiczny |
| `GET` | `/auth/me` | Dane zalogowanego użytkownika | Zalogowany |
| `POST` | `/auth/register` | Rejestracja nowego użytkownika | Admin |
| `GET` | `/auth/users` | Lista użytkowników | Admin |
| `DELETE` | `/auth/users/{id}` | Dezaktywacja użytkownika | Admin |

### 12.2 Klienci (`/clients`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/clients` | Lista z paginacją, wyszukiwaniem i filtrem aktywności |
| `GET` | `/clients/{id}` | Szczegóły klienta |
| `POST` | `/clients` | Dodaj klienta (admin) |
| `PUT` | `/clients/{id}` | Aktualizuj klienta (admin) |
| `DELETE` | `/clients/{id}` | Dezaktywuj klienta (admin) |

### 12.3 Import TSV (`/imports`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/imports/upload` | Prześlij plik TSV (faktury lub pozycje) |
| `GET` | `/imports` | Lista importów z filtrowaniem |
| `GET` | `/imports/{id}` | Szczegóły importu |
| `PATCH` | `/imports/{id}/status` | Zmień status importu |
| `GET` | `/imports/{id}/staging-invoices` | Podgląd danych staging |
| `GET` | `/imports/{id}/staging-items` | Podgląd pozycji staging |

### 12.4 Walidacja (`/validation`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/validation/run/{import_id}` | Uruchom walidację biznesową |
| `GET` | `/validation/errors/{import_id}` | Lista błędów walidacji |
| `PATCH` | `/validation/errors/{id}/resolve` | Oznacz błąd jako rozwiązany |
| `DELETE` | `/validation/errors/{id}` | Usuń błąd walidacji |

### 12.5 KSeF / XML (`/ksef`)

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/ksef/transform/{import_id}` | Staging → faktury docelowe |
| `POST` | `/ksef/generate/{import_id}` | Generuj XML KSeF FA(2) |
| `GET` | `/ksef/download/{import_id}` | Pobierz archiwum ZIP z XML-ami |
| `GET` | `/ksef/download/invoice/{id}` | Pobierz XML pojedynczej faktury |
| `GET` | `/ksef/invoices/{import_id}` | Lista faktur importu z paginacją |

### 12.6 Faktury i raporty

| Metoda | Endpoint | Opis |
|--------|----------|------|
| `GET/POST/PUT/DELETE` | `/invoices/*` | Pełne CRUD faktur z filtrami |
| `GET` | `/reports/monthly` | Raport miesięczny (per klient/miesiąc) |

---

## 13. Zaimplementowane funkcjonalności

### 13.1 Import danych TSV

!(import_TSV_2.png)

!(import_TSV.png)

Parser TSV (tsv_parser.py) obsługuje:
- separator TAB, kodowanie UTF-8
- weryfikację wymaganych nagłówków (`ID_FIRMY`, `NUMER_FAKTURY`, `NIP_SPRZEDAWCY` i in.)
- sprawdzanie spójności `ID_FIRMY` we wszystkich wierszach
- masowe ładowanie do bazy przez komendę PostgreSQL `COPY` (wydajne dla dużych plików, limit 50 MB)
- dwa typy plików: faktury (`invoices`) i pozycje faktur (`items`)

### 13.2 Walidacja biznesowa

Serwis walidacji (validation_service.py) sprawdza:

| Kod błędu | Opis |
|-----------|------|
| `MISSING_FIELD` | Wymagane pole puste lub NULL |
| `INVALID_NIP` | NIP nie przechodzi walidacji sumy kontrolnej |
| `INVALID_DATE` | Data w niepoprawnym formacie (wymagany `YYYY-MM-DD`) |
| `INVALID_AMOUNT` | Wartość nie jest liczbą dziesiętną |
| `AMOUNT_MISMATCH` | `netto + VAT ≠ brutto` (tolerancja 0,01 zł) |
| `INVALID_CURRENCY` | Waluta spoza listy kodów ISO 4217 |
| `INVALID_INVOICE_TYPE` | Typ faktury spoza dozwolonych wartości |
| `MISSING_ITEMS` | Faktura nie posiada żadnych pozycji (ostrzeżenie) |

### 13.3 Walidator NIP

![Przykład wykrycia złego NIP](Walidacja_2.png)

nip.py implementuje pełną weryfikację polskiego NIP-u:
- sprawdzenie długości (dokładnie 10 cyfr)
- odrzucenie NIP złożonego z samych zer
- obliczenie sumy kontrolnej: wagi `[6,5,7,2,3,4,5,6,7]`, reszta z dzielenia przez 11

### 13.4 Generowanie XML KSeF FA(2)

Serwis ksef_xml_service.py generuje dokumenty XML zgodne ze standardem KSeF:
- namespace: `http://crd.gov.pl/wzor/2023/06/29/12648/`
- struktura: `Naglowek` → `Podmiot1` (sprzedawca) → `Podmiot2` (nabywca) → `Fa` → `FaWiersz` (pozycje)
- mapowanie stawek VAT na pola FA(2): 23% → `P_13_1`, 8% → `P_13_2`, 5% → `P_13_3`, 0% → `P_13_4`
- eksport zbiorczy do archiwum **ZIP** (jeden plik XML na fakturę)

### 13.5 System uwierzytelniania i autoryzacji

- Logowanie przez **OAuth2 Password Flow** (formularz `username`/`password`)
- Tokeny **JWT** (HS256) z konfigurowalnymi czasem wygaśnięcia i kluczem tajnym
- Dwa poziomy dostępu: `user` (odczyt) i `admin` (pełny CRUD + rejestracja użytkowników)
- Haszowanie haseł **bcrypt** przez passlib

### 13.6 Raport miesięczny

Endpoint `GET /reports/monthly` generuje zestawienie dla wybranego klienta i miesiąca:
- liczba importów i ich statusy
- łączne kwoty netto/VAT/brutto
- podział faktur wg typu (`VAT`, `KOREKTA` itd.)
- liczba błędów walidacji (rozwiązanych i nierozwiązanych)

---

## 14. Potok przetwarzania faktury

```
Plik TSV
   ↓
POST /imports/upload     → staging_invoices (status: LOADED)
   ↓
POST /validation/run/{id} → validation_errors (status: VALIDATED / ERROR)
   ↓
POST /ksef/transform/{id} → invoices + invoice_items (status: DRAFT→VALIDATED)
   ↓
POST /ksef/generate/{id}  → xml_content w tabeli invoices (status: EXPORTED)
   ↓
GET /ksef/download/{id}   → archiwum ZIP z plikami XML
```

---

## 15. Dalsze możliwości rozwoju

### 15.1 Rozszerzenia funkcjonalne

1. **Integracja z API KSeF MF** — wysyłka wygenerowanych XML bezpośrednio do systemu Ministerstwa Finansów przez REST API KSeF, odbieranie numerów referencyjnych
2. **Frontend** — panel webowy do zarządzania importami, podglądu faktur i statusów walidacji
3. **Powiadomienia e-mail** — informowanie klientów o wyniku walidacji i eksportu
4. **Obsługa korekt faktur** — rozbudowanie walidacji i generatora XML o typ `KOREKTA` z polami `FaKorygowana`
5. **Wielowątkowy import** — przetwarzanie dużych plików TSV asynchronicznie (Celery/background tasks)

### 15.2 Ulepszenia techniczne

- Uzupełnienie migracji Alembic (obecna wersja używa surowego SQL)
- Testy jednostkowe i integracyjne (katalog tests przygotowany)
- Rate limiting i throttling dla endpointów API
- Paginacja oparta na kursorze dla dużych zbiorów danych

---

## 16. Krytyczna analiza uzyskanych wyników

Podczas realizacji projektu osiągnięto wszystkie założone cele funkcjonalne. System poprawnie obsługuje pełny potok przetwarzania faktur: od importu pliku TSV po generowanie pliku XML.

### 16.1 Zalety rozwiązania

- Poprawnie zaprojektowana, relacyjna baza danych z zachowaniem integralności referencyjnej i ograniczeniami CHECK
- Wyraźny podział na warstwy (router → service → model) ułatwiający testowanie i rozbudowę
- Wydajny import masowy przez PostgreSQL `COPY` zamiast wstawiania wierszami
- Implementacja pełnej walidacji NIP (suma kontrolna) jako oddzielnego modułu
- Automatyczna dokumentacja API (Swagger UI) generowana przez FastAPI
- Konteneryzacja przez Docker Compose umożliwiająca uruchomienie jedną komendą

### 16.2 Ograniczenia projektu

- Brak frontendu — system dostępny wyłącznie przez API
- Brak bezpośredniej integracji z produkcyjnym środowiskiem KSeF MF
- Alembic skonfigurowany, lecz migracje zarządzane ręcznie przez SQL
- Uproszczony model uprawnień (dwa poziomy: `admin`/`user`)

---

## 17. Podsumowanie i wnioski

Zrealizowany projekt spełnia wszystkie założone cele. System implementuje kompletny potok przetwarzania faktur KSeF: import TSV → walidację (NIP, kwoty, daty, waluty) → transformację do struktury docelowej → generowanie XML FA(2) → eksport ZIP. Baza danych zawiera 10 powiązanych tabel z pełnymi ograniczeniami integralności. Backend udostępnia 31 endpointów REST z dokumentacją Swagger, uwierzytelnianiem JWT i kontrolą dostępu opartą na rolach.

Pełny kod źródłowy projektu dostępny jest w repozytorium projektu na GitHub: https://github.com/GitGotlib/Projekt-KSEF