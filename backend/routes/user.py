from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/auth", tags=["auth"])


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
        raise HTTPException(status_code=500, detail="Database error while creating user")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unexpected error during signup")


@router.post("/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    try:
        user = db.query(models.User).filter(models.User.email == credentials.email).first()
        if not user or not auth.verify_password(credentials.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        token = auth.create_access_token({"sub": str(user.id), "role": user.role})
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": user.role,
            "name": user.name,
            "id": user.id,
        }
    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(status_code=500, detail="Database error during login")
    except Exception:
        raise HTTPException(status_code=500, detail="Unexpected error during login")


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)):
    try:
        return current_user
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load current user")