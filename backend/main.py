"""
main.py — TalentLens AI FastAPI entry-point.

Environment-based AI provider selection:
    - Default: AI_PROVIDER=groq
    - Override via environment variables when needed
"""

import os
import sys
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

print("[START] Starting TalentLens AI backend...")
print(f"Python version: {sys.version}")

load_dotenv()

# ── Required env vars ─────────────────────────────────────────────────────────
def _fatal_env(var_name: str, message: str) -> None:
    print(f"[FATAL] [{var_name}]: {message}")
    sys.exit(1)


def _required_env(var_name: str) -> str:
    value = (os.getenv(var_name) or "").strip()
    if not value:
        _fatal_env(var_name, "Environment variable is required.")
    return value


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        _fatal_env("PORT", f"Invalid integer value: '{raw}'.")
    if port < 1 or port > 65535:
        _fatal_env("PORT", f"Port out of range: {port}. Expected 1-65535.")
    return port


PORT = _parse_port((os.getenv("PORT") or "10000").strip())
AI_PROVIDER = (os.getenv("AI_PROVIDER") or "groq").strip().lower()  # "groq" | "local"

# Surface missing critical config early
_required_env("DATABASE_URL")

if not (os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY")):
    _fatal_env("JWT_SECRET", "Set JWT_SECRET (preferred) or SECRET_KEY.")

if AI_PROVIDER not in {"groq", "local"}:
    _fatal_env("AI_PROVIDER", f"Unsupported value '{AI_PROVIDER}'. Use 'groq' or 'local'.")

if AI_PROVIDER == "groq":
    _required_env("GROQ_API_KEY")

print(f"📋 PORT={PORT}  |  AI_PROVIDER={AI_PROVIDER}")

# ── Import database (exits if DATABASE_URL missing/invalid) ───────────────────
try:
    from database import engine, SessionLocal
    print("✅ Database module loaded")
except SystemExit:
    raise
except Exception as e:
    print(f"❌ Error importing database: {e}")
    sys.exit(1)

# ── Import models & routes ────────────────────────────────────────────────────
try:
    import models
    from routes import user, admin, analyze, health
    from auth import hash_password
    print("✅ Models and routes imported")
except Exception as e:
    print(f"❌ Error importing models/routes: {e}")
    sys.exit(1)

# ── Create DB tables (idempotent — safe to run every startup) ─────────────────
try:
    models.Base.metadata.create_all(bind=engine)
    print("✅ Database tables verified / created")
except Exception as e:
    print(f"⚠️  Warning creating tables: {e}")
    # Don't exit — Supabase tables may already exist via migrations

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(title="TalentLens AI", version="1.0.0")

# ── CORS ──────────────────────────────────────────────────────────────────────
# Primary frontend origin should be set via FRONTEND_URL.
# Additional comma-separated origins can be provided via CORS_ORIGINS.
_frontend_url = os.getenv("FRONTEND_URL", "").strip()
_extra_raw = os.getenv("CORS_ORIGINS", "")
_extra = [o.strip() for o in _extra_raw.split(",") if o.strip()]

_is_production = os.getenv("NODE_ENV", "development").lower() == "production"
_allow_localhost = os.getenv(
    "ALLOW_LOCALHOST_CORS",
    "false" if _is_production else "true",
).lower() == "true"

# Build a regex that matches every http(s)://localhost:<any-port>
# FastAPI's CORSMiddleware supports allow_origin_regex for this.
LOCALHOST_REGEX = r"^https?://localhost(:\d+)?$"

_explicit_origins = [
    _frontend_url,
    *_extra,
]
_explicit_origins = [origin for origin in _explicit_origins if origin]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_explicit_origins,
    allow_origin_regex=LOCALHOST_REGEX if _allow_localhost else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
print(
    "✅ CORS configured "
    f"(frontend_url={_frontend_url or 'unset'}, "
    f"localhost_regex={'enabled' if _allow_localhost else 'disabled'}, "
    f"extra={_extra})"
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(analyze.router)
app.include_router(health.router)
print("✅ All routes registered")

# Create uploads dir so FileResponse never 500 on a missing directory
os.makedirs("uploads", exist_ok=True)


# ── Startup: seed admin ───────────────────────────────────────────────────────
@app.on_event("startup")
def seed_admin():
    """Create the admin user from env vars if it doesn't already exist."""
    try:
        db = SessionLocal()
        try:
            admin_email = (os.getenv("ADMIN_EMAIL") or "admin@company.com").strip()
            existing = db.query(models.User).filter(models.User.email == admin_email).first()
            if not existing:
                admin_password = (os.getenv("ADMIN_PASSWORD") or "").strip()
                if not admin_password:
                    print("⚠️  Admin seeding skipped: ADMIN_PASSWORD is not set.")
                    return

                admin_user = models.User(
                    name=(os.getenv("ADMIN_NAME") or "Admin").strip() or "Admin",
                    email=admin_email,
                    password_hash=hash_password(admin_password),
                    role="admin",
                )
                db.add(admin_user)
                db.commit()
                print(f"✅ Admin seeded: {admin_email}")
            else:
                print(f"ℹ️  Admin already exists: {admin_email}")
        finally:
            db.close()
    except Exception as e:
        # Non-fatal: app continues even if seeding fails
        print(f"⚠️  Admin seeding warning: {e}")


# ── Health & root ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "message": "TalentLens AI API",
        "status": "running",
        "version": app.version,
        "ai_provider": AI_PROVIDER,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "TalentLens AI Backend", "ai_provider": AI_PROVIDER}


print("=" * 50)
print("✅ TalentLens AI backend ready")
print(f"🌐 Docs: http://0.0.0.0:{PORT}/docs")
print(f"🌐 Health: http://0.0.0.0:{PORT}/health")
print("=" * 50)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
