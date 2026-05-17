-- =============================================================================
-- KSeF Invoice Processing System – Initial Schema
-- Migration: 001_initial_schema.sql
-- Database: PostgreSQL
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- USERS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id               SERIAL         PRIMARY KEY,
    username         VARCHAR(100)   NOT NULL UNIQUE,
    email            VARCHAR(255)   NOT NULL UNIQUE,
    hashed_password  VARCHAR(255)   NOT NULL,
    first_name       VARCHAR(100),
    last_name        VARCHAR(100),
    role             VARCHAR(20)    NOT NULL DEFAULT 'user'
                         CHECK (role IN ('admin', 'user')),
    is_active        BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ             DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE INDEX IF NOT EXISTS ix_users_email    ON users (email);

-- ---------------------------------------------------------------------------
-- CLIENTS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clients (
    id                  SERIAL        PRIMARY KEY,
    -- ID_FIRMY: internal business identifier used in TSV files
    company_id          VARCHAR(50)   NOT NULL UNIQUE,
    -- NIP: Polish Tax Identification Number (exactly 10 digits)
    nip                 VARCHAR(10)   NOT NULL UNIQUE
                            CHECK (nip ~ '^\d{10}$'),
    company_name        VARCHAR(255)  NOT NULL,
    address_street      VARCHAR(255),
    address_city        VARCHAR(100),
    address_postal_code VARCHAR(10),
    address_country     VARCHAR(3)    NOT NULL DEFAULT 'PL',
    email               VARCHAR(255),
    phone               VARCHAR(20),
    is_active           BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ            DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_clients_company_id   ON clients (company_id);
CREATE INDEX IF NOT EXISTS ix_clients_nip          ON clients (nip);
CREATE INDEX IF NOT EXISTS ix_clients_company_name ON clients (company_name);

-- ---------------------------------------------------------------------------
-- IMPORTS  (import batch registry)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS imports (
    id              SERIAL        PRIMARY KEY,
    client_id       INTEGER       NOT NULL REFERENCES clients (id) ON DELETE RESTRICT,
    user_id         INTEGER       NOT NULL REFERENCES users   (id) ON DELETE RESTRICT,
    -- Billing month in YYYY-MM format, e.g. "2024-01"
    import_month    VARCHAR(7)    NOT NULL
                        CHECK (import_month ~ '^\d{4}-\d{2}$'),
    filename        VARCHAR(500)  NOT NULL,
    file_size_bytes BIGINT,
    row_count       INTEGER                DEFAULT 0 CHECK (row_count >= 0),
    error_count     INTEGER                DEFAULT 0 CHECK (error_count >= 0),
    status          VARCHAR(20)   NOT NULL DEFAULT 'NEW'
                        CHECK (status IN ('NEW', 'LOADED', 'VALIDATED', 'ERROR', 'EXPORTED')),
    notes           TEXT,
    imported_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ            DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_imports_client_id    ON imports (client_id);
CREATE INDEX IF NOT EXISTS ix_imports_user_id      ON imports (user_id);
CREATE INDEX IF NOT EXISTS ix_imports_status       ON imports (status);
CREATE INDEX IF NOT EXISTS ix_imports_import_month ON imports (import_month);

-- ---------------------------------------------------------------------------
-- STAGING_INVOICES  (raw TSV data, all TEXT)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging_invoices (
    id                 SERIAL      PRIMARY KEY,
    import_id          INTEGER     NOT NULL REFERENCES imports (id) ON DELETE CASCADE,
    -- Original row number in the TSV file (1-based, excluding header row)
    row_number         INTEGER,

    -- Raw TSV fields – no type conversion
    id_firmy           TEXT,
    numer_faktury      TEXT,
    data_wystawienia   TEXT,
    data_sprzedazy     TEXT,
    typ_faktury        TEXT,
    nip_sprzedawcy     TEXT,
    nazwa_sprzedawcy   TEXT,
    adres_sprzedawcy   TEXT,
    nip_nabywcy        TEXT,
    nazwa_nabywcy      TEXT,
    adres_nabywcy      TEXT,
    wartosc_netto      TEXT,
    kwota_vat          TEXT,
    wartosc_brutto     TEXT,
    waluta             TEXT,
    termin_platnosci   TEXT,
    sposob_platnosci   TEXT,
    numer_konta        TEXT,

    -- NULL = not yet validated, TRUE = valid, FALSE = invalid
    is_valid           BOOLEAN,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_staging_invoices_import_id     ON staging_invoices (import_id);
CREATE INDEX IF NOT EXISTS ix_staging_invoices_numer_faktury ON staging_invoices (numer_faktury);
CREATE INDEX IF NOT EXISTS ix_staging_invoices_id_firmy      ON staging_invoices (id_firmy);

-- ---------------------------------------------------------------------------
-- STAGING_INVOICE_ITEMS  (raw TSV data, all TEXT)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS staging_invoice_items (
    id                       SERIAL  PRIMARY KEY,
    import_id                INTEGER NOT NULL REFERENCES imports          (id) ON DELETE CASCADE,
    staging_invoice_id       INTEGER          REFERENCES staging_invoices (id) ON DELETE CASCADE,
    row_number               INTEGER,

    -- Raw TSV fields – no type conversion
    id_firmy                 TEXT,
    numer_faktury            TEXT,
    lp                       TEXT,   -- Line position / item number
    nazwa_towaru_uslugi      TEXT,
    jednostka_miary          TEXT,
    ilosc                    TEXT,
    cena_jednostkowa_netto   TEXT,
    stawka_vat               TEXT,
    wartosc_netto            TEXT,
    kwota_vat                TEXT,
    wartosc_brutto           TEXT,

    -- NULL = not yet validated, TRUE = valid, FALSE = invalid
    is_valid                 BOOLEAN,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_staging_invoice_items_import_id          ON staging_invoice_items (import_id);
CREATE INDEX IF NOT EXISTS ix_staging_invoice_items_staging_invoice_id ON staging_invoice_items (staging_invoice_id);
CREATE INDEX IF NOT EXISTS ix_staging_invoice_items_numer_faktury      ON staging_invoice_items (numer_faktury);

-- ---------------------------------------------------------------------------
-- INVOICES  (target – post-validation, properly typed)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id                    SERIAL         PRIMARY KEY,
    client_id             INTEGER        NOT NULL REFERENCES clients (id) ON DELETE RESTRICT,
    user_id               INTEGER                 REFERENCES users   (id) ON DELETE SET NULL,
    import_id             INTEGER                 REFERENCES imports (id) ON DELETE SET NULL,

    invoice_number        VARCHAR(100)   NOT NULL,
    invoice_date          DATE           NOT NULL,
    sale_date             DATE,
    invoice_type          VARCHAR(20)    NOT NULL DEFAULT 'VAT'
                              CHECK (invoice_type IN ('VAT', 'CORRECTION', 'ADVANCE', 'PROFORMA')),

    -- Seller
    seller_nip            VARCHAR(10)    NOT NULL CHECK (seller_nip ~ '^\d{10}$'),
    seller_name           VARCHAR(255)   NOT NULL,
    seller_address        TEXT,

    -- Buyer
    buyer_nip             VARCHAR(10)    NOT NULL CHECK (buyer_nip ~ '^\d{10}$'),
    buyer_name            VARCHAR(255)   NOT NULL,
    buyer_address         TEXT,

    -- Financial totals
    net_amount            NUMERIC(15,2)  NOT NULL CHECK (net_amount >= 0),
    vat_amount            NUMERIC(15,2)  NOT NULL CHECK (vat_amount >= 0),
    gross_amount          NUMERIC(15,2)  NOT NULL CHECK (gross_amount >= 0),
    currency              VARCHAR(3)     NOT NULL DEFAULT 'PLN',

    -- Payment
    payment_method        VARCHAR(50),
    payment_due_date      DATE,
    bank_account          VARCHAR(34),   -- IBAN format

    status                VARCHAR(20)    NOT NULL DEFAULT 'DRAFT'
                              CHECK (status IN ('DRAFT', 'VALIDATED', 'EXPORTED', 'ERROR')),

    -- KSeF integration
    ksef_reference_number VARCHAR(100)   UNIQUE,
    xml_content           TEXT,          -- Generated KSeF-compliant XML
    xml_generated_at      TIMESTAMPTZ,

    notes                 TEXT,
    created_at            TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ             DEFAULT NOW(),

    -- Invoice number is unique per client (not globally)
    CONSTRAINT uq_invoices_client_invoice_number UNIQUE (client_id, invoice_number)
);

CREATE INDEX IF NOT EXISTS ix_invoices_client_id      ON invoices (client_id);
CREATE INDEX IF NOT EXISTS ix_invoices_user_id        ON invoices (user_id);
CREATE INDEX IF NOT EXISTS ix_invoices_import_id      ON invoices (import_id);
CREATE INDEX IF NOT EXISTS ix_invoices_invoice_number ON invoices (invoice_number);
CREATE INDEX IF NOT EXISTS ix_invoices_invoice_date   ON invoices (invoice_date);
CREATE INDEX IF NOT EXISTS ix_invoices_status         ON invoices (status);
CREATE INDEX IF NOT EXISTS ix_invoices_seller_nip     ON invoices (seller_nip);
CREATE INDEX IF NOT EXISTS ix_invoices_buyer_nip      ON invoices (buyer_nip);

-- ---------------------------------------------------------------------------
-- INVOICE_ITEMS  (target line items)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoice_items (
    id                  SERIAL          PRIMARY KEY,
    invoice_id          INTEGER         NOT NULL REFERENCES invoices (id) ON DELETE CASCADE,
    line_number         INTEGER         NOT NULL,
    item_name           VARCHAR(500)    NOT NULL,
    unit_of_measure     VARCHAR(20),
    quantity            NUMERIC(15,4)   NOT NULL CHECK (quantity > 0),
    unit_price_net      NUMERIC(15,4)   NOT NULL,
    vat_rate            NUMERIC(5,2)    NOT NULL CHECK (vat_rate >= 0 AND vat_rate <= 100),
    net_amount          NUMERIC(15,2)   NOT NULL CHECK (net_amount >= 0),
    vat_amount          NUMERIC(15,2)   NOT NULL CHECK (vat_amount >= 0),
    gross_amount        NUMERIC(15,2)   NOT NULL CHECK (gross_amount >= 0),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_invoice_items_invoice_line UNIQUE (invoice_id, line_number)
);

CREATE INDEX IF NOT EXISTS ix_invoice_items_invoice_id ON invoice_items (invoice_id);

-- ---------------------------------------------------------------------------
-- VALIDATION_ERRORS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS validation_errors (
    id                  SERIAL      PRIMARY KEY,
    import_id           INTEGER     REFERENCES imports          (id) ON DELETE CASCADE,
    invoice_id          INTEGER     REFERENCES invoices         (id) ON DELETE CASCADE,
    staging_invoice_id  INTEGER     REFERENCES staging_invoices (id) ON DELETE CASCADE,
    row_number          INTEGER,
    field_name          VARCHAR(100),
    -- Short machine-readable code, e.g. "MISSING_NIP", "INVALID_DATE"
    error_code          VARCHAR(50),
    error_message       TEXT        NOT NULL,
    severity            VARCHAR(10) NOT NULL DEFAULT 'ERROR'
                            CHECK (severity IN ('ERROR', 'WARNING')),
    is_resolved         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_validation_errors_import_id          ON validation_errors (import_id);
CREATE INDEX IF NOT EXISTS ix_validation_errors_invoice_id         ON validation_errors (invoice_id);
CREATE INDEX IF NOT EXISTS ix_validation_errors_staging_invoice_id ON validation_errors (staging_invoice_id);
CREATE INDEX IF NOT EXISTS ix_validation_errors_severity           ON validation_errors (severity);
CREATE INDEX IF NOT EXISTS ix_validation_errors_is_resolved        ON validation_errors (is_resolved);

-- ---------------------------------------------------------------------------
-- LOGS  (audit log)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS logs (
    id           BIGSERIAL    PRIMARY KEY,
    user_id      INTEGER      REFERENCES users   (id) ON DELETE SET NULL,
    client_id    INTEGER      REFERENCES clients (id) ON DELETE SET NULL,
    import_id    INTEGER      REFERENCES imports (id) ON DELETE SET NULL,
    -- Operation name, e.g. "IMPORT", "VALIDATE", "GENERATE_XML", "LOGIN"
    operation    VARCHAR(50)  NOT NULL,
    entity_type  VARCHAR(50),
    entity_id    INTEGER,
    details      TEXT,        -- JSON-serialised extra info
    ip_address   VARCHAR(45), -- Supports both IPv4 and IPv6
    status       VARCHAR(10)  NOT NULL DEFAULT 'INFO'
                     CHECK (status IN ('SUCCESS', 'ERROR', 'INFO')),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_logs_user_id    ON logs (user_id);
CREATE INDEX IF NOT EXISTS ix_logs_client_id  ON logs (client_id);
CREATE INDEX IF NOT EXISTS ix_logs_import_id  ON logs (import_id);
CREATE INDEX IF NOT EXISTS ix_logs_operation  ON logs (operation);
CREATE INDEX IF NOT EXISTS ix_logs_status     ON logs (status);
CREATE INDEX IF NOT EXISTS ix_logs_created_at ON logs (created_at);

-- ---------------------------------------------------------------------------
-- COMMENTS  (administrative annotations)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comments (
    id         SERIAL      PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users    (id) ON DELETE RESTRICT,
    invoice_id INTEGER              REFERENCES invoices (id) ON DELETE CASCADE,
    import_id  INTEGER              REFERENCES imports  (id) ON DELETE CASCADE,
    content    TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ          DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_comments_user_id    ON comments (user_id);
CREATE INDEX IF NOT EXISTS ix_comments_invoice_id ON comments (invoice_id);
CREATE INDEX IF NOT EXISTS ix_comments_import_id  ON comments (import_id);

COMMIT;
