from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os
import sys

# Load environment variables
load_dotenv()

# Get DATABASE URL from .env
DATABASE_URL = os.getenv("DATABASE_URL")

print("🔄 Initializing database connection...")

# Fallback to SQLite if DATABASE_URL not set
if not DATABASE_URL:
    print("⚠️  DATABASE_URL not found, using SQLite fallback")
    DATABASE_URL = "sqlite:///./test.db"

print(f"📦 Database URL: {DATABASE_URL[:40]}...")

# Create engine (handles both SQLite & PostgreSQL)
try:
    if "sqlite" in DATABASE_URL:
        print("📦 SQLite mode detected")
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False}
        )
    else:
        # For Supabase / PostgreSQL
        print("📦 PostgreSQL/Supabase mode detected")
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,                 # avoids stale connections
            connect_args={"sslmode": "require"},  # 🔥 REQUIRED for Supabase
            echo=False,  # Set to True for SQL debugging
            pool_recycle=3600,  # Recycle connections every hour
        )
    print("✅ Database engine created successfully")
except Exception as e:
    print(f"❌ Error creating database engine: {e}")
    print("⚠️  App will attempt to continue, but database operations may fail")

# Session factory
try:
    SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    print("✅ Session factory created successfully")
except Exception as e:
    print(f"❌ Error creating session factory: {e}")
    sys.exit(1)

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