from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get DATABASE URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")

# Create engine (handles both SQLite & PostgreSQL)
if "sqlite" in DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    # For Supabase / PostgreSQL
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,                 # avoids stale connections
        connect_args={"sslmode": "require"} # 🔥 REQUIRED for Supabase
    )

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for models
class Base(DeclarativeBase):
    pass

# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()