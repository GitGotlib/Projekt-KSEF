"""Tworzy konto administratora z predefiniowanymi danymi."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.database.session import SessionLocal
from app.schemas.user import UserCreate
from app.services.auth_service import create_user, get_user_by_username

USERNAME = "admin"
EMAIL    = "admin@ksef-system.pl"
PASSWORD = "Admin1234!"

db = SessionLocal()
try:
    existing = get_user_by_username(db, USERNAME)
    if existing:
        print(f"Admin '{USERNAME}' juz istnieje (id={existing.id}, active={existing.is_active}).")
    else:
        user_data = UserCreate(username=USERNAME, email=EMAIL, password=PASSWORD, role="admin")
        user = create_user(db, user_data)
        print(f"Admin utworzony! id={user.id}, username={user.username}")
except Exception as e:
    print(f"BLAD: {type(e).__name__}: {e}")
finally:
    db.close()
