"""
Skrypt CLI do tworzenia pierwszego konta administratora.

Użycie:
    python -m scripts.create_admin
"""

import getpass
import os
import sys

# Dodaj katalog główny projektu do ścieżki
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402
from app.services.auth_service import (  # noqa: E402
    create_user,
    get_user_by_email,
    get_user_by_username,
)


def main() -> None:
    print("=== Tworzenie konta administratora KSeF ===\n")

    username = input("Nazwa użytkownika: ").strip()
    email = input("Adres e-mail: ").strip()
    password = getpass.getpass("Hasło (min. 8 znaków): ")
    password_confirm = getpass.getpass("Potwierdź hasło: ")

    if not username or not email or not password:
        print("[BŁĄD] Wszystkie pola są wymagane.")
        sys.exit(1)

    if password != password_confirm:
        print("[BŁĄD] Hasła nie są zgodne.")
        sys.exit(1)

    try:
        user_data = UserCreate(
            username=username,
            email=email,
            password=password,
            role="admin",
        )
    except ValueError as exc:
        print(f"[BŁĄD] Walidacja: {exc}")
        sys.exit(1)

    db = SessionLocal()
    try:
        if get_user_by_username(db, username):
            print(f"[BŁĄD] Użytkownik '{username}' już istnieje.")
            sys.exit(1)
        if get_user_by_email(db, email):
            print(f"[BŁĄD] E-mail '{email}' jest już zarejestrowany.")
            sys.exit(1)

        user = create_user(db, user_data)
        print(f"\n[OK] Administrator '{user.username}' (id={user.id}) został utworzony.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
