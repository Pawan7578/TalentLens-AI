import logging
import os
from datetime import datetime, timedelta
from threading import Lock

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
EMAIL_ADAPTER = TypeAdapter(EmailStr)

try:
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "5"))
except ValueError:
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5

try:
    LOGIN_RATE_LIMIT_WINDOW_MINUTES = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"))
except ValueError:
    LOGIN_RATE_LIMIT_WINDOW_MINUTES = 15

LOGIN_RATE_LIMIT_WINDOW = timedelta(minutes=LOGIN_RATE_LIMIT_WINDOW_MINUTES)
_failed_login_attempts: dict[str, list[datetime]] = {}
_failed_login_lock = Lock()


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune_attempts(attempts: list[datetime], now: datetime) -> list[datetime]:
    cutoff = now - LOGIN_RATE_LIMIT_WINDOW
    return [ts for ts in attempts if ts >= cutoff]


def _check_rate_limit(ip: str) -> None:
    now = datetime.utcnow()
    with _failed_login_lock:
        attempts = _prune_attempts(_failed_login_attempts.get(ip, []), now)
        if attempts:
            _failed_login_attempts[ip] = attempts
        else:
            _failed_login_attempts.pop(ip, None)

        if len(attempts) >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts, please try again later",
            )


def _record_failed_attempt(ip: str) -> None:
    now = datetime.utcnow()
    with _failed_login_lock:
        attempts = _prune_attempts(_failed_login_attempts.get(ip, []), now)
        attempts.append(now)
        _failed_login_attempts[ip] = attempts


def _clear_failed_attempts(ip: str) -> None:
    with _failed_login_lock:
        _failed_login_attempts.pop(ip, None)


def _require_https_in_production(request: Request) -> None:
    if os.getenv("NODE_ENV", "development").lower() != "production":
        return

    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    scheme = forwarded_proto or request.url.scheme.lower()
    if scheme != "https":
        raise HTTPException(status_code=400, detail="HTTPS is required in production")


def _validate_login_payload(credentials: schemas.LoginRequest) -> tuple[str, str]:
    email_raw = (credentials.email or "").strip()
    password = credentials.password

    if not email_raw or not isinstance(password, str) or password == "":
        raise HTTPException(status_code=400, detail="Email and password required")

    try:
        normalized_email = str(EMAIL_ADAPTER.validate_python(email_raw))
    except ValidationError:
        raise HTTPException(status_code=400, detail="Invalid email format")

    return normalized_email, password


def _build_login_response(user: models.User) -> dict:
    token_payload = {"sub": str(user.id), "role": user.role, "email": user.email}
    token = auth.create_access_token(token_payload)
    refresh_token = auth.create_refresh_token(token_payload)
    return {
        "token": token,
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "role": user.role,
        "name": user.name,
        "id": user.id,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
        },
    }


@router.post("/signup", response_model=schemas.UserOut)
def signup(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    try:
        existing = db.query(models.User).filter(models.User.email == user_data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed = auth.hash_password(user_data.password)
        user = models.User(
            name=user_data.name,
            email=user_data.email,
            password_hash=hashed,
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while creating user")
        raise HTTPException(status_code=500, detail="Internal server error")
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during signup")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/register", response_model=schemas.Token, status_code=status.HTTP_201_CREATED)
def register(user_data: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):
    _require_https_in_production(request)
    try:
        existing = db.query(models.User).filter(models.User.email == user_data.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")

        user = models.User(
            name=user_data.name,
            email=user_data.email,
            password_hash=auth.hash_password(user_data.password),
            role="user",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return _build_login_response(user)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error during registration")
        raise HTTPException(status_code=500, detail="Internal server error")
    except Exception:
        db.rollback()
        logger.exception("Unexpected error during registration")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/login", response_model=schemas.Token)
def login(
    request: Request,
    credentials: schemas.LoginRequest = Body(default_factory=schemas.LoginRequest),
    db: Session = Depends(get_db),
):
    _require_https_in_production(request)
    client_ip = _get_client_ip(request)
    _check_rate_limit(client_ip)

    try:
        email, password = _validate_login_payload(credentials)

        user = db.query(models.User).filter(models.User.email == email).first()
        if not user or not auth.verify_password(password, user.password_hash):
            _record_failed_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Invalid email or password")

        _clear_failed_attempts(client_ip)
        return _build_login_response(user)
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("Database error during login")
        raise HTTPException(status_code=500, detail="Internal server error")
    except Exception:
        logger.exception("Unexpected login error")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/refresh", response_model=schemas.RefreshTokenResponse)
def refresh_access_token(
    payload: schemas.RefreshTokenRequest = Body(default_factory=schemas.RefreshTokenRequest),
    db: Session = Depends(get_db),
):
    incoming_token = (payload.refresh_token or payload.refreshToken or "").strip()
    if not incoming_token:
        raise HTTPException(status_code=400, detail="Refresh token required")

    credentials_exception = HTTPException(status_code=401, detail="Invalid refresh token")

    try:
        decoded = jwt.decode(incoming_token, auth.JWT_SECRET, algorithms=[auth.ALGORITHM])
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    if decoded.get("token_type") != "refresh":
        raise credentials_exception

    subject = decoded.get("sub")
    if subject is None:
        raise credentials_exception

    user = None
    if isinstance(subject, int) or (isinstance(subject, str) and subject.isdigit()):
        user = db.query(models.User).filter(models.User.id == int(subject)).first()
    elif isinstance(subject, str):
        user = db.query(models.User).filter(models.User.email == subject).first()

    if not user:
        raise credentials_exception

    token_payload = {"sub": str(user.id), "role": user.role, "email": user.email}
    access_token = auth.create_access_token(token_payload)
    refresh_token = auth.create_refresh_token(token_payload)

    return {
        "token": access_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)):
    try:
        return current_user
    except Exception:
        logger.exception("Failed to load current user")
        raise HTTPException(status_code=500, detail="Failed to load current user")