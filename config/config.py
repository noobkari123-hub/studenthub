import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///student_hub.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY", "")
    SEARCH_API_PROVIDER = os.environ.get("SEARCH_API_PROVIDER", "mock")
    # AI provider configuration. AI_API_KEY remains for backwards compatibility.
    AI_API_KEY = os.environ.get("AI_API_KEY", "")
    AI_API_PROVIDER = os.environ.get("AI_API_PROVIDER", "groq").lower()
    AI_MODEL = os.environ.get("AI_MODEL", "qwen/qwen3.6-27b")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or os.environ.get("AI_GEMINI_MODEL") or "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
    AI_OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_OPENAI_API_KEY") or (AI_API_KEY if AI_API_PROVIDER in ("auto", "openai") else "")
    AI_GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_GEMINI_API_KEY") or (AI_API_KEY if AI_API_PROVIDER == "gemini" else "")
    AI_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AI_ANTHROPIC_API_KEY") or (AI_API_KEY if AI_API_PROVIDER == "anthropic" else "")
    AI_GROQ_API_KEY = os.environ.get("GROQ_API_KEY") or os.environ.get("AI_GROQ_API_KEY") or (AI_API_KEY if AI_API_PROVIDER == "groq" else "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.6-27b")
    GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "groq/compound")
    POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "")
    POLLINATIONS_IMAGE_MODEL = os.environ.get("POLLINATIONS_IMAGE_MODEL", "flux")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    AI_FALLBACK_ENABLED = os.environ.get("AI_FALLBACK_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    AI_PROVIDER_ORDER = os.environ.get("AI_PROVIDER_ORDER", "groq")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")
    # Comma-separated email addresses allowed to view the admin user/login dashboard.
    ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "")

    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30
