from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os
import sys

print("🚀 Starting FastAPI app...")
print(f"Python version: {sys.version}")

load_dotenv()

# Load environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 10000))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")

print(f"📋 Environment: PORT={PORT}")
print(f"📋 Frontend origin: {FRONTEND_ORIGIN}")
if DATABASE_URL:
    print(f"📋 Database URL loaded: {DATABASE_URL[:50]}...")
else:
    print("⚠️  WARNING: DATABASE_URL not set - using SQLite fallback")

for env_name in ["DATABASE_URL", "SECRET_KEY", "ALGORITHM"]:
    if not os.getenv(env_name):
        print(f"⚠️  WARNING: {env_name} is not set")

# Import database AFTER printing logs
try:
    from database import engine, SessionLocal
    print("✅ Database module imported successfully")
except Exception as e:
    print(f"❌ Error importing database module: {e}")
    sys.exit(1)

# Import models and routes
try:
    import models
    from routes import user, admin, analyze
    from auth import hash_password
    print("✅ Models and routes imported successfully")
except Exception as e:
    print(f"❌ Error importing models/routes: {e}")
    sys.exit(1)

# Create tables - with error handling
try:
    models.Base.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified")
except Exception as e:
    print(f"⚠️  Warning creating database tables: {e}")
    print("App will continue running, but database operations may fail")

app = FastAPI(title="TalentLens AI", version="1.0.0")
print(f"✅ FastAPI app initialized: {app.title} {app.version}")

# CORS Configuration
origin_set = {
    "http://localhost:5173",
    "https://talentlens-ai.onrender.com",
    FRONTEND_ORIGIN,
}

for origin in CORS_ORIGINS.split(","):
    clean_origin = origin.strip()
    if clean_origin:
        origin_set.add(clean_origin)

allowed_origins = sorted(origin_set)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
print(f"✅ CORS middleware added for origins: {allowed_origins}")

# Routes
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(analyze.router)
print("✅ All routes registered")

# Serve uploaded files (for admin download)
os.makedirs("uploads", exist_ok=True)


@app.on_event("startup")
def seed_admin():
    """Seed admin account from environment variables if it doesn't exist."""
    try:
        db = SessionLocal()
        try:
            admin_email = os.getenv("ADMIN_EMAIL", "admin@company.com")
            existing = db.query(models.User).filter(models.User.email == admin_email).first()
            if not existing:
                admin_user = models.User(
                    name=os.getenv("ADMIN_NAME", "Admin"),
                    email=admin_email,
                    password_hash=hash_password(os.getenv("ADMIN_PASSWORD", "Admin@123")),
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
        print(f"⚠️  Warning during admin seeding: {e}")
        print("App will continue running without admin user")


@app.get("/")
def root():
    return {
        "message": "TalentLens AI API",
        "status": "running",
        "version": app.version,
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Health check endpoint for monitoring"""
    return {
        "status": "ok",
        "service": "TalentLens AI Backend"
    }


# Log startup completion
print("=" * 50)
print("✅ FastAPI App Ready!")
print("=" * 50)
print(f"🌐 API Docs: http://0.0.0.0:{PORT}/docs")
print(f"🌐 Health Check: http://0.0.0.0:{PORT}/health")
print("=" * 50)