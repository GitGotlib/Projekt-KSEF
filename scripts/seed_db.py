"""
Seed script – wypełnia bazę KSeF przykładowymi danymi.
Uruchomienie: python scripts/seed_db.py
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2
from passlib.context import CryptContext

DB_DSN = "postgresql://ksef:ksef_password@localhost:5434/ksef_db"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def h(pw): return pwd_context.hash(pw)

conn = psycopg2.connect(DB_DSN, client_encoding="UTF8")
conn.autocommit = False
cur = conn.cursor()

try:
    # -------------------------------------------------------------------------
    # USERS (skip admin – already exists)
    # -------------------------------------------------------------------------
    users_data = [
        ("jan.kowalski",  "jan.kowalski@firma.pl",  h("Test1234!"), "Jan",   "Kowalski", "user"),
        ("anna.nowak",    "anna.nowak@firma.pl",     h("Test1234!"), "Anna",  "Nowak",    "user"),
        ("piotr.wisniew", "piotr.wisniew@firma.pl",  h("Test1234!"), "Piotr", "Wiśniewski","admin"),
    ]
    inserted_users = {}
    for uname, email, hpw, fn, ln, role in users_data:
        cur.execute("SELECT id FROM users WHERE username=%s", (uname,))
        row = cur.fetchone()
        if row:
            inserted_users[uname] = row[0]
            print(f"  user '{uname}' już istnieje (id={row[0]})")
        else:
            cur.execute(
                "INSERT INTO users (username,email,hashed_password,first_name,last_name,role)"
                " VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (uname, email, hpw, fn, ln, role)
            )
            uid = cur.fetchone()[0]
            inserted_users[uname] = uid
            print(f"  user '{uname}' utworzony (id={uid})")

    # Pobierz id admina
    cur.execute("SELECT id FROM users WHERE username='admin'")
    row = cur.fetchone()
    admin_id = row[0] if row else list(inserted_users.values())[0]

    # -------------------------------------------------------------------------
    # CLIENTS
    # -------------------------------------------------------------------------
    clients_data = [
        ("FIRMA001", "5261040828", "Przykładowa Spółka z o.o.",
         "ul. Marszałkowska 1", "Warszawa", "00-001", "PL",
         "biuro@przykladowa.pl", "+48 22 123 45 67"),
        ("FIRMA002", "7272445302", "TechSolutions Sp. z o.o.",
         "ul. Puławska 100", "Warszawa", "02-595", "PL",
         "info@techsolutions.pl", "+48 22 987 65 43"),
        ("FIRMA003", "5540308842", "Handel Plus S.A.",
         "ul. Gdańska 15", "Poznań", "61-123", "PL",
         "handel@handelplus.pl", "+48 61 111 22 33"),
    ]
    client_ids = {}
    for cid, nip, name, street, city, postal, country, email, phone in clients_data:
        cur.execute("SELECT id FROM clients WHERE company_id=%s", (cid,))
        row = cur.fetchone()
        if row:
            client_ids[cid] = row[0]
            print(f"  client '{cid}' już istnieje (id={row[0]})")
        else:
            cur.execute(
                "INSERT INTO clients (company_id,nip,company_name,address_street,"
                "address_city,address_postal_code,address_country,email,phone)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (cid, nip, name, street, city, postal, country, email, phone)
            )
            cid_db = cur.fetchone()[0]
            client_ids[cid] = cid_db
            print(f"  client '{cid}' utworzony (id={cid_db})")

    # -------------------------------------------------------------------------
    # IMPORTS
    # -------------------------------------------------------------------------
    imports_data = [
        # (client_key, user_key_or_id, month, filename, size, rows, errors, status, notes)
        ("FIRMA001", admin_id,              "2024-01", "faktury_firma001_2024_01.tsv", 4096, 3, 0, "VALIDATED", "Import styczeń 2024"),
        ("FIRMA002", admin_id,              "2024-01", "faktury_firma002_2024_01.tsv", 2048, 2, 0, "EXPORTED",  "Import styczeń 2024 – wyeksportowany"),
        ("FIRMA003", admin_id,              "2024-02", "faktury_firma003_2024_02.tsv", 1024, 1, 1, "ERROR",     "Błąd walidacji NIP"),
        ("FIRMA001", admin_id,              "2024-02", "faktury_firma001_2024_02.tsv", 3200, 2, 0, "LOADED",    "Import luty 2024"),
    ]
    import_ids = {}
    for i, (ck, uid, month, fname, sz, rows, errs, status, notes) in enumerate(imports_data):
        cur.execute(
            "SELECT id FROM imports WHERE client_id=%s AND import_month=%s AND filename=%s",
            (client_ids[ck], month, fname)
        )
        row = cur.fetchone()
        if row:
            import_ids[i] = row[0]
            print(f"  import '{fname}' już istnieje (id={row[0]})")
        else:
            cur.execute(
                "INSERT INTO imports (client_id,user_id,import_month,filename,file_size_bytes,"
                "row_count,error_count,status,notes)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (client_ids[ck], uid, month, fname, sz, rows, errs, status, notes)
            )
            iid = cur.fetchone()[0]
            import_ids[i] = iid
            print(f"  import '{fname}' utworzony (id={iid})")

    # -------------------------------------------------------------------------
    # STAGING INVOICES (import 0 = FIRMA001 2024-01)
    # -------------------------------------------------------------------------
    staging_invoices_data = [
        # import_idx, row, id_firmy, numer, data_wyst, data_sprz, typ, nip_s, nazwa_s, adres_s,
        #   nip_n, nazwa_n, adres_n, netto, vat, brutto, waluta, termin, sposob, konto, is_valid
        (0, 1, "FIRMA001","FV/2024/01/001","2024-01-05","2024-01-05","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "1234567890","Nabywca Sp. z o.o.","ul. Prosta 10, 00-002 Warszawa",
         "1000.00","230.00","1230.00","PLN","2024-01-19","przelew","12 1234 5678 9012 3456 7890 1234", True),
        (0, 2, "FIRMA001","FV/2024/01/002","2024-01-10","2024-01-10","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "9876543210","Inny Klient S.A.","ul. Długa 20, 00-003 Warszawa",
         "2500.00","575.00","3075.00","PLN","2024-01-24","przelew","12 1234 5678 9012 3456 7890 1234", True),
        (0, 3, "FIRMA001","FV/2024/01/003","2024-01-15","2024-01-15","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "1111111118","Trzecia Firma Sp.k.","ul. Krótka 5, 00-004 Warszawa",
         "800.00","184.00","984.00","PLN","2024-01-29","gotówka","", True),
        # import 1 = FIRMA002 2024-01
        (1, 1, "FIRMA002","FV/2024/01/001","2024-01-08","2024-01-08","VAT",
         "7272445302","TechSolutions Sp. z o.o.","ul. Puławska 100, 02-595 Warszawa",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "5000.00","1150.00","6150.00","PLN","2024-01-22","przelew","98 7654 3210 9876 5432 1098 7654", True),
        (1, 2, "FIRMA002","FV/2024/01/002","2024-01-20","2024-01-20","VAT",
         "7272445302","TechSolutions Sp. z o.o.","ul. Puławska 100, 02-595 Warszawa",
         "1234567890","Nabywca Sp. z o.o.","ul. Prosta 10, 00-002 Warszawa",
         "1200.00","276.00","1476.00","PLN","2024-02-03","przelew","98 7654 3210 9876 5432 1098 7654", True),
        # import 2 = FIRMA003 2024-02 (błędny NIP)
        (2, 1, "FIRMA003","FV/2024/02/001","2024-02-03","2024-02-03","VAT",
         "5540308842","Handel Plus S.A.","ul. Gdańska 15, 61-123 Poznań",
         "0000000000","Błędny NIP Sp. z o.o.","ul. Testowa 1, 00-001 Warszawa",
         "300.00","69.00","369.00","PLN","2024-02-17","przelew","", False),
        # import 3 = FIRMA001 2024-02
        (3, 1, "FIRMA001","FV/2024/02/001","2024-02-05","2024-02-05","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "9876543210","Inny Klient S.A.","ul. Długa 20, 00-003 Warszawa",
         "1500.00","345.00","1845.00","PLN","2024-02-19","przelew","12 1234 5678 9012 3456 7890 1234", True),
        (3, 2, "FIRMA001","FV/2024/02/002","2024-02-12","2024-02-12","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "1111111118","Trzecia Firma Sp.k.","ul. Krótka 5, 00-004 Warszawa",
         "600.00","138.00","738.00","PLN","2024-02-26","gotówka","", True),
    ]
    staging_ids = {}  # (import_idx, numer) -> staging_id
    for rec in staging_invoices_data:
        imp_idx, row_nr, id_firmy, numer = rec[0], rec[1], rec[2], rec[3]
        cur.execute(
            "SELECT id FROM staging_invoices WHERE import_id=%s AND numer_faktury=%s",
            (import_ids[imp_idx], numer)
        )
        row = cur.fetchone()
        if row:
            staging_ids[(imp_idx, numer)] = row[0]
        else:
            cur.execute(
                "INSERT INTO staging_invoices (import_id,row_number,id_firmy,numer_faktury,"
                "data_wystawienia,data_sprzedazy,typ_faktury,nip_sprzedawcy,nazwa_sprzedawcy,"
                "adres_sprzedawcy,nip_nabywcy,nazwa_nabywcy,adres_nabywcy,wartosc_netto,"
                "kwota_vat,wartosc_brutto,waluta,termin_platnosci,sposob_platnosci,"
                "numer_konta,is_valid)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " RETURNING id",
                (import_ids[imp_idx], row_nr, id_firmy, numer,
                 rec[4], rec[5], rec[6], rec[7], rec[8], rec[9],
                 rec[10], rec[11], rec[12], rec[13], rec[14], rec[15],
                 rec[16], rec[17], rec[18], rec[19] if rec[19] else None, rec[20])
            )
            sid = cur.fetchone()[0]
            staging_ids[(imp_idx, numer)] = sid
    print(f"  staging_invoices: {len(staging_ids)} rekordów")

    # -------------------------------------------------------------------------
    # STAGING INVOICE ITEMS
    # -------------------------------------------------------------------------
    items_staging = [
        # (import_idx, numer_faktury, staging_key, lp, nazwa, jm, ilosc, cena, stawka, netto, vat, brutto)
        (0,"FV/2024/01/001",1,"Usługa konsultingowa","godz","10","100.00","23","1000.00","230.00","1230.00"),
        (0,"FV/2024/01/002",1,"Oprogramowanie licencja","szt","1","2000.00","23","2000.00","460.00","2460.00"),
        (0,"FV/2024/01/002",2,"Wsparcie techniczne","godz","5","100.00","23","500.00","115.00","615.00"),
        (0,"FV/2024/01/003",1,"Szkolenie online","os","4","200.00","23","800.00","184.00","984.00"),
        (1,"FV/2024/01/001",1,"Wdrożenie systemu","szt","1","5000.00","23","5000.00","1150.00","6150.00"),
        (1,"FV/2024/01/002",1,"Hosting miesięczny","mies","1","1200.00","23","1200.00","276.00","1476.00"),
        (2,"FV/2024/02/001",1,"Towar A","szt","10","30.00","23","300.00","69.00","369.00"),
        (3,"FV/2024/02/001",1,"Usługa projektowa","godz","15","100.00","23","1500.00","345.00","1845.00"),
        (3,"FV/2024/02/002",1,"Materiały biurowe","kpl","1","600.00","23","600.00","138.00","738.00"),
    ]
    for imp_idx, numer, lp, nazwa, jm, ilosc, cena, stawka, netto, vat, brutto in items_staging:
        stg_id = staging_ids.get((imp_idx, numer))
        cur.execute(
            "SELECT id FROM staging_invoice_items WHERE import_id=%s AND numer_faktury=%s AND lp=%s",
            (import_ids[imp_idx], numer, str(lp))
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO staging_invoice_items (import_id,staging_invoice_id,row_number,"
                "id_firmy,numer_faktury,lp,nazwa_towaru_uslugi,jednostka_miary,ilosc,"
                "cena_jednostkowa_netto,stawka_vat,wartosc_netto,kwota_vat,wartosc_brutto,is_valid)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (import_ids[imp_idx], stg_id, lp,
                 "FIRMA001" if imp_idx in (0,3) else f"FIRMA00{imp_idx+1}",
                 numer, str(lp), nazwa, jm, ilosc, cena, stawka, netto, vat, brutto,
                 True if imp_idx != 2 else False)
            )
    print("  staging_invoice_items: OK")

    # -------------------------------------------------------------------------
    # INVOICES (zwalidowane – import 0 i 1)
    # -------------------------------------------------------------------------
    invoices_data = [
        # imp_idx, client_key, numer, inv_date, sale_date, typ,
        # nip_s, nazwa_s, adres_s, nip_n, nazwa_n, adres_n,
        # netto, vat, brutto, waluta, pay_method, due_date, konto, status
        (0,"FIRMA001","FV/2024/01/001","2024-01-05","2024-01-05","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "1234567890","Nabywca Sp. z o.o.","ul. Prosta 10, 00-002 Warszawa",
         1000.00,230.00,1230.00,"PLN","przelew","2024-01-19","PL12123456789012345678901234","VALIDATED"),
        (0,"FIRMA001","FV/2024/01/002","2024-01-10","2024-01-10","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "9876543210","Inny Klient S.A.","ul. Długa 20, 00-003 Warszawa",
         2500.00,575.00,3075.00,"PLN","przelew","2024-01-24","PL12123456789012345678901234","VALIDATED"),
        (0,"FIRMA001","FV/2024/01/003","2024-01-15","2024-01-15","VAT",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         "1111111118","Trzecia Firma Sp.k.","ul. Krótka 5, 00-004 Warszawa",
         800.00,184.00,984.00,"PLN","gotówka","2024-01-29",None,"VALIDATED"),
        (1,"FIRMA002","FV/2024/01/001","2024-01-08","2024-01-08","VAT",
         "7272445302","TechSolutions Sp. z o.o.","ul. Puławska 100, 02-595 Warszawa",
         "5261040828","Przykładowa Spółka z o.o.","ul. Marszałkowska 1, 00-001 Warszawa",
         5000.00,1150.00,6150.00,"PLN","przelew","2024-01-22","PL98765432109876543210987654","EXPORTED"),
        (1,"FIRMA002","FV/2024/01/002","2024-01-20","2024-01-20","VAT",
         "7272445302","TechSolutions Sp. z o.o.","ul. Puławska 100, 02-595 Warszawa",
         "1234567890","Nabywca Sp. z o.o.","ul. Prosta 10, 00-002 Warszawa",
         1200.00,276.00,1476.00,"PLN","przelew","2024-02-03","PL98765432109876543210987654","EXPORTED"),
    ]
    invoice_ids = {}  # (imp_idx, numer) -> invoice_id
    for rec in invoices_data:
        imp_idx, ck, numer = rec[0], rec[1], rec[2]
        cur.execute(
            "SELECT id FROM invoices WHERE client_id=%s AND invoice_number=%s",
            (client_ids[ck], numer)
        )
        row = cur.fetchone()
        if row:
            invoice_ids[(imp_idx, numer)] = row[0]
        else:
            cur.execute(
                "INSERT INTO invoices (client_id,user_id,import_id,invoice_number,"
                "invoice_date,sale_date,invoice_type,seller_nip,seller_name,seller_address,"
                "buyer_nip,buyer_name,buyer_address,net_amount,vat_amount,gross_amount,"
                "currency,payment_method,payment_due_date,bank_account,status)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                " RETURNING id",
                (client_ids[ck], admin_id, import_ids[imp_idx], numer,
                 rec[3], rec[4], rec[5], rec[6], rec[7], rec[8],
                 rec[9], rec[10], rec[11], rec[12], rec[13], rec[14],
                 rec[15], rec[16], rec[17], rec[18], rec[19])
            )
            inv_id = cur.fetchone()[0]
            invoice_ids[(imp_idx, numer)] = inv_id
    print(f"  invoices: {len(invoice_ids)} rekordów")

    # -------------------------------------------------------------------------
    # INVOICE ITEMS
    # -------------------------------------------------------------------------
    inv_items_data = [
        (0,"FV/2024/01/001",1,"Usługa konsultingowa","godz",10.0,100.0000,23.0,1000.00,230.00,1230.00),
        (0,"FV/2024/01/002",1,"Oprogramowanie licencja","szt",1.0,2000.0000,23.0,2000.00,460.00,2460.00),
        (0,"FV/2024/01/002",2,"Wsparcie techniczne","godz",5.0,100.0000,23.0,500.00,115.00,615.00),
        (0,"FV/2024/01/003",1,"Szkolenie online","os",4.0,200.0000,23.0,800.00,184.00,984.00),
        (1,"FV/2024/01/001",1,"Wdrożenie systemu","szt",1.0,5000.0000,23.0,5000.00,1150.00,6150.00),
        (1,"FV/2024/01/002",1,"Hosting miesięczny","mies",1.0,1200.0000,23.0,1200.00,276.00,1476.00),
    ]
    for imp_idx, numer, lp, nazwa, jm, qty, up, vr, netto, vat, brutto in inv_items_data:
        inv_id = invoice_ids.get((imp_idx, numer))
        if not inv_id:
            continue
        cur.execute(
            "SELECT id FROM invoice_items WHERE invoice_id=%s AND line_number=%s",
            (inv_id, lp)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO invoice_items (invoice_id,line_number,item_name,unit_of_measure,"
                "quantity,unit_price_net,vat_rate,net_amount,vat_amount,gross_amount)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (inv_id, lp, nazwa, jm, qty, up, vr, netto, vat, brutto)
            )
    print("  invoice_items: OK")

    # -------------------------------------------------------------------------
    # VALIDATION ERRORS
    # -------------------------------------------------------------------------
    stg_bad_id = staging_ids.get((2, "FV/2024/02/001"))
    val_errors = [
        # import 2 (FIRMA003) – błędny NIP nabywcy
        (import_ids[2], None, stg_bad_id, 1, "nip_nabywcy", "INVALID_NIP",
         "NIP nabywcy '0000000000' jest nieprawidłowy – same zera.", "ERROR", False),
        # import 2 – ostrzeżenie o brakującym koncie bankowym
        (import_ids[2], None, stg_bad_id, 1, "numer_konta", "MISSING_BANK_ACCOUNT",
         "Brak numeru konta bankowego przy płatności przelewem.", "WARNING", True),
        # import 0 – ostrzeżenie rozwiązane
        (import_ids[0], invoice_ids.get((0,"FV/2024/01/003")), None, 3, "numer_konta",
         "MISSING_BANK_ACCOUNT", "Brak numeru konta – płatność gotówkowa.", "WARNING", True),
    ]
    for imp_id, inv_id, stg_id, row_nr, field, code, msg, sev, resolved in val_errors:
        cur.execute(
            "SELECT id FROM validation_errors WHERE import_id=%s AND error_code=%s AND field_name=%s",
            (imp_id, code, field)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO validation_errors (import_id,invoice_id,staging_invoice_id,"
                "row_number,field_name,error_code,error_message,severity,is_resolved)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (imp_id, inv_id, stg_id, row_nr, field, code, msg, sev, resolved)
            )
    print("  validation_errors: OK")

    # -------------------------------------------------------------------------
    # COMMENTS
    # -------------------------------------------------------------------------
    comments_data = [
        (admin_id, invoice_ids.get((0,"FV/2024/01/001")), None,
         "Faktura zweryfikowana i zatwierdzona do eksportu KSeF."),
        (admin_id, invoice_ids.get((1,"FV/2024/01/001")), None,
         "Eksport do KSeF zakończony sukcesem – nr ref. KSeF wygenerowany."),
        (admin_id, None, import_ids[2],
         "Import odrzucony – błędny NIP nabywcy. Klient FIRMA003 poinformowany."),
    ]
    for uid, inv_id, imp_id, content in comments_data:
        if inv_id or imp_id:
            cur.execute(
                "INSERT INTO comments (user_id,invoice_id,import_id,content)"
                " VALUES (%s,%s,%s,%s)",
                (uid, inv_id, imp_id, content)
            )
    print("  comments: OK")

    # -------------------------------------------------------------------------
    # LOGS
    # -------------------------------------------------------------------------
    logs_data = [
        (admin_id, client_ids["FIRMA001"], import_ids[0], "IMPORT",  "import",  import_ids[0],
         '{"rows": 3, "file": "faktury_firma001_2024_01.tsv"}', "127.0.0.1", "SUCCESS"),
        (admin_id, client_ids["FIRMA001"], import_ids[0], "VALIDATE","import",  import_ids[0],
         '{"valid": 3, "invalid": 0}', "127.0.0.1", "SUCCESS"),
        (admin_id, client_ids["FIRMA002"], import_ids[1], "IMPORT",  "import",  import_ids[1],
         '{"rows": 2, "file": "faktury_firma002_2024_01.tsv"}', "127.0.0.1", "SUCCESS"),
        (admin_id, client_ids["FIRMA002"], import_ids[1], "GENERATE_XML","import",import_ids[1],
         '{"invoices_exported": 2}', "127.0.0.1", "SUCCESS"),
        (admin_id, client_ids["FIRMA003"], import_ids[2], "IMPORT",  "import",  import_ids[2],
         '{"rows": 1, "file": "faktury_firma003_2024_02.tsv"}', "127.0.0.1", "SUCCESS"),
        (admin_id, client_ids["FIRMA003"], import_ids[2], "VALIDATE","import",  import_ids[2],
         '{"valid": 0, "invalid": 1, "errors": ["INVALID_NIP"]}', "127.0.0.1", "ERROR"),
        (admin_id, None, None, "LOGIN", "user", admin_id,
         '{"username": "admin"}', "127.0.0.1", "SUCCESS"),
    ]
    for uid, cid, imp_id, op, ent_type, ent_id, details, ip, status in logs_data:
        cur.execute(
            "INSERT INTO logs (user_id,client_id,import_id,operation,entity_type,"
            "entity_id,details,ip_address,status)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (uid, cid, imp_id, op, ent_type, ent_id, details, ip, status)
        )
    print("  logs: OK")

    conn.commit()
    print("\n✓ Seed zakończony pomyślnie!")

except Exception as e:
    conn.rollback()
    print(f"\n✗ BŁĄD – rollback: {type(e).__name__}: {e}")
    raise
finally:
    cur.close()
    conn.close()
