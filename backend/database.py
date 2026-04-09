"""
database.py — Supabase-only connection (no SQLite fallback).

Supabase requires SSL. On Render, DATABASE_URL is set as an env var.
Locally, put it in your .env file.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os
import sys
from urllib.parse import urlsplit, urlunsplit

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ FATAL: DATABASE_URL environment variable is not set.")
    print("   Set it to your Supabase connection string in .env (local) or Render env vars (production).")
    sys.exit(1)

# Reject SQLite — Supabase only
if "sqlite" in DATABASE_URL.lower():
    print("❌ FATAL: SQLite is not supported. Set DATABASE_URL to your Supabase PostgreSQL connection string.")
    sys.exit(1)

# Supabase connection strings from the dashboard come in two flavours:
#   postgres://...  or  postgresql://...
# SQLAlchemy 1.4+ requires the "postgresql://" scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def _redact_database_url(raw_url: str) -> str:
    """Return a safe-to-log DB URL with credentials redacted."""
    try:
        parsed = urlsplit(raw_url)
        username = parsed.username or ""
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""

        if username:
            netloc = f"{username}:***@{host}{port}"
        else:
            netloc = f"{host}{port}"

        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "<redacted>"

print("🔄 Initialising Supabase/PostgreSQL connection...")
print(f"📦 Database URL: {_redact_database_url(DATABASE_URL)}")

try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,               # detect & discard stale connections
        connect_args={"sslmode": "require"},  # required for Supabase
        pool_recycle=3600,                # recycle connections every hour
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    print("✅ Database engine created")
except Exception as e:
    print(f"❌ Error creating database engine: {e}")
    sys.exit(1)

try:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    print("✅ Session factory created")
except Exception as e:
    print(f"❌ Error creating session factory: {e}")
    sys.exit(1)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
