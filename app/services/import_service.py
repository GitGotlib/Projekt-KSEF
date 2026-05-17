"""
Serwis importu TSV.

Architektura:
1. ORM (SQLAlchemy Session) – zarządzanie rekordem Import i metadanymi.
2. PostgreSQL COPY FROM STDIN – efektywne ładowanie danych do staging.
   Używa surowego połączenia psycopg2 niezależnie od sesji ORM.
"""

import io
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.database.session import engine
from app.models.import_ import Import
from app.models.staging import StagingInvoice, StagingInvoiceItem
from app.utils.tsv_parser import (
    INVOICE_COLUMNS,
    ITEM_COLUMNS,
    TsvParseResult,
    escape_copy_value,
)

# ---------------------------------------------------------------------------
# Odczyt importów
# ---------------------------------------------------------------------------


def get_import_by_id(db: Session, import_id: int) -> Optional[Import]:
    return db.query(Import).filter(Import.id == import_id).first()


def get_imports(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    import_month: Optional[str] = None,
) -> Tuple[int, List[Import]]:
    query = db.query(Import)
    if client_id is not None:
        query = query.filter(Import.client_id == client_id)
    if status:
        query = query.filter(Import.status == status)
    if import_month:
        query = query.filter(Import.import_month == import_month)
    total = query.count()
    items = (
        query.order_by(Import.imported_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, items


def update_import_status(
    db: Session,
    import_id: int,
    status: str,
    notes: Optional[str] = None,
    error_count: Optional[int] = None,
) -> Optional[Import]:
    import_record = get_import_by_id(db, import_id)
    if not import_record:
        return None
    import_record.status = status
    if notes is not None:
        import_record.notes = notes
    if error_count is not None:
        import_record.error_count = error_count
    db.commit()
    db.refresh(import_record)
    return import_record


# ---------------------------------------------------------------------------
# Tworzenie rekordu importu
# ---------------------------------------------------------------------------


def create_import_record(
    db: Session,
    client_id: int,
    user_id: int,
    import_month: str,
    filename: str,
    file_size_bytes: int,
) -> Import:
    import_record = Import(
        client_id=client_id,
        user_id=user_id,
        import_month=import_month,
        filename=filename,
        file_size_bytes=file_size_bytes,
        status="NEW",
    )
    db.add(import_record)
    db.commit()
    db.refresh(import_record)
    return import_record


# ---------------------------------------------------------------------------
# Ładowanie danych staging via PostgreSQL COPY FROM STDIN
# ---------------------------------------------------------------------------


def _build_copy_buffer(
    import_id: int,
    rows: List[dict],
    columns: List[str],
) -> io.StringIO:
    """
    Buduje bufor danych w formacie PostgreSQL COPY TEXT.
    Puste wartości są wysyłane jako puste stringi – polecenie COPY
    używa NULL '' aby traktować je jako NULL w bazie.
    """
    buf = io.StringIO()
    for row_number, row in enumerate(rows, start=1):
        values = [str(import_id), str(row_number)] + [
            escape_copy_value(row.get(col, "")) for col in columns
        ]
        buf.write("\t".join(values) + "\n")
    buf.seek(0)
    return buf


def _run_copy(table: str, db_columns: List[str], buf: io.StringIO) -> None:
    """
    Wykonuje COPY FROM STDIN na podanej tabeli.
    Używa surowego połączenia psycopg2 (poza sesją ORM).
    """
    col_list = ", ".join(["import_id", "row_number"] + db_columns)
    sql = (
        f"COPY {table} ({col_list}) "
        f"FROM STDIN WITH (FORMAT TEXT, DELIMITER '\t', NULL '')"
    )
    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.copy_expert(sql, buf)
        raw_conn.commit()
        cursor.close()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def load_invoices_to_staging(
    db: Session,
    import_record: Import,
    parse_result: TsvParseResult,
) -> None:
    """
    Ładuje faktury ze staging za pomocą PostgreSQL COPY FROM STDIN.
    Aktualizuje rekord importu: row_count i status LOADED.
    W razie błędu ustawia status ERROR.
    """
    db_columns = [col.lower() for col in INVOICE_COLUMNS]
    buf = _build_copy_buffer(import_record.id, parse_result.rows, INVOICE_COLUMNS)
    try:
        _run_copy("staging_invoices", db_columns, buf)
        import_record.row_count = parse_result.row_count
        import_record.status = "LOADED"
        db.commit()
        db.refresh(import_record)
    except Exception as exc:
        update_import_status(
            db,
            import_record.id,
            status="ERROR",
            notes=f"Błąd COPY do staging_invoices: {exc}",
        )
        raise


def load_items_to_staging(
    db: Session,
    import_record: Import,
    parse_result: TsvParseResult,
) -> None:
    """
    Ładuje pozycje faktur do staging_invoice_items via PostgreSQL COPY.
    """
    db_columns = [col.lower() for col in ITEM_COLUMNS]
    buf = _build_copy_buffer(import_record.id, parse_result.rows, ITEM_COLUMNS)
    try:
        _run_copy("staging_invoice_items", db_columns, buf)
        import_record.row_count = parse_result.row_count
        import_record.status = "LOADED"
        db.commit()
        db.refresh(import_record)
    except Exception as exc:
        update_import_status(
            db,
            import_record.id,
            status="ERROR",
            notes=f"Błąd COPY do staging_invoice_items: {exc}",
        )
        raise


# ---------------------------------------------------------------------------
# Odczyt danych staging
# ---------------------------------------------------------------------------


def get_staging_invoices(
    db: Session,
    import_id: int,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[int, List[StagingInvoice]]:
    query = db.query(StagingInvoice).filter(StagingInvoice.import_id == import_id)
    total = query.count()
    items = query.order_by(StagingInvoice.row_number).offset(skip).limit(limit).all()
    return total, items


def get_staging_items(
    db: Session,
    import_id: int,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[int, List[StagingInvoiceItem]]:
    query = db.query(StagingInvoiceItem).filter(
        StagingInvoiceItem.import_id == import_id
    )
    total = query.count()
    items = query.order_by(StagingInvoiceItem.row_number).offset(skip).limit(limit).all()
    return total, items
