"""
database.py — Supabase-only connection (no SQLite fallback).

Supabase requires SSL. On Render, DATABASE_URL is set as an env var.
Locally, put it in your .env file.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.exc import OperationalError, DatabaseError
from dotenv import load_dotenv
import os
import sys
import logging
from urllib.parse import urlsplit, urlunsplit
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

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
        connect_args={
            "sslmode": "require",         # required for Supabase
            "connect_timeout": 10,        # connection timeout in seconds
        },
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def test_database_connection():
    """Test database connection with retry logic.
    
    Retries up to 3 times with exponential backoff:
    - 1st attempt: immediate
    - 2nd attempt: 4-8 seconds
    - 3rd attempt: 8-16 seconds
    """
    try:
        db = SessionLocal()
        try:
            result = db.execute(text("SELECT 1"))
            logger.info("✅ Database connection test successful")
            return True
        finally:
            db.close()
    except (OperationalError, DatabaseError) as e:
        logger.warning(f"Database connection attempt failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected database error: {e}")
        raise
