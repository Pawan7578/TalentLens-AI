from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import os

from database import engine, SessionLocal
import models
from routes import user, admin, analyze
from auth import hash_password

load_dotenv()

# Create tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="TalentLens AI", version="1.0.0")

# CORS
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(analyze.router)

# Serve uploaded files (for admin download)
os.makedirs("uploads", exist_ok=True)


@app.on_event("startup")
def seed_admin():
    """Seed admin account from environment variables if it doesn't exist."""
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


@app.get("/")
def root():
    return {"message": "TalentLens AI API", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}