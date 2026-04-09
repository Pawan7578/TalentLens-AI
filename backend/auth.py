from datetime import datetime, timedelta
from typing import Optional
import hashlib
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from database import get_db
import models
import os
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", "10080"))
MAX_BCRYPT_BYTES = 72

try:
    BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "10"))
except ValueError:
    BCRYPT_ROUNDS = 10

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET (or SECRET_KEY for backward compatibility) is required")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def prepare_password_for_bcrypt(password: str) -> bytes:
    """Prepare a password so bcrypt never receives more than 72 bytes."""
    if not isinstance(password, str):
        raise ValueError("Password must be a string")

    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= MAX_BCRYPT_BYTES:
        return password_bytes

    # For long passwords, hash first to fixed-length hex then clamp to 72 bytes.
    sha256_hex = hashlib.sha256(password_bytes).hexdigest()
    return sha256_hex[:MAX_BCRYPT_BYTES].encode("utf-8")


def hash_password(password: str) -> str:
    prepared = prepare_password_for_bcrypt(password)
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(prepared, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        prepared = prepare_password_for_bcrypt(plain)
        return bcrypt.checkpw(prepared, hashed.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "token_type": "access"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "token_type": "refresh"})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if payload.get("token_type") == "refresh":
            raise credentials_exception

        subject = payload.get("sub")
        if subject is None:
            raise credentials_exception

        user = None
        if isinstance(subject, int) or (isinstance(subject, str) and subject.isdigit()):
            user = db.query(models.User).filter(models.User.id == int(subject)).first()
        elif isinstance(subject, str):
            user = db.query(models.User).filter(models.User.email == subject).first()

        if user is None:
            raise credentials_exception
        return user
    except (JWTError, ValueError, TypeError):
        raise credentials_exception


def require_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_user(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="User access required")
    return current_user