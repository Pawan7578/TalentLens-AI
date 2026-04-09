import os

from fastapi import APIRouter
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/provider")
async def active_provider():
    """Return active provider context used by the backend."""
    ai_provider = os.getenv("AI_PROVIDER", "groq")
    return {
        "active_provider": ai_provider,
        "auto_provider": "groq",
        "is_production": os.getenv("NODE_ENV", "development").lower() == "production",
    }
