from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.config import settings
from app.core.security import create_access_token
from app.database import get_db
from app.models.user import User
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_user,
    deactivate_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=Token,
    summary="Zaloguj się i pobierz token JWT",
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Logowanie przez OAuth2 PasswordFlow.
    Zwraca token Bearer używany do autoryzacji pozostałych endpointów.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy login lub hasło",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Pobierz dane aktualnie zalogowanego użytkownika",
)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Zarejestruj nowego użytkownika (tylko admin)",
)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Tworzy nowego użytkownika w systemie.
    Dostępne wyłącznie dla administratorów.
    """
    if get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Podana nazwa użytkownika jest już zajęta",
        )
    if get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Podany adres e-mail jest już zarejestrowany",
        )
    return create_user(db, user_data)


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="Lista wszystkich użytkowników (tylko admin)",
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return db.query(User).order_by(User.id).all()


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dezaktywuj użytkownika (tylko admin)",
)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Dezaktywuje konto użytkownika (soft-delete).
    Administrator nie może dezaktywować własnego konta.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nie możesz dezaktywować własnego konta",
        )
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Użytkownik nie istnieje",
        )
    deactivate_user(db, user_id)
