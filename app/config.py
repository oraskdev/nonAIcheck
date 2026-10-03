"""Environment-only secrets. No provider credential is ever sent to the browser."""
import base64
import hashlib
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self):
        self.production = os.getenv("APP_ENV", "development") == "production"
        self.app_url = os.getenv("APP_URL", "").rstrip("/") or os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000").rstrip("/")
        secret = os.getenv("APP_SECRET", "")
        if not secret:
            if self.production:
                raise RuntimeError("APP_SECRET is required in production.")
            path = ROOT / ".local-secret"
            if not path.exists():
                path.write_text(secrets.token_urlsafe(48))
                path.chmod(0o600)
            secret = path.read_text().strip()
        if len(secret) < 32:
            raise RuntimeError("APP_SECRET must contain at least 32 characters.")
        self.encryption_key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self.database_url = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'txtzi.db'}")
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.production and self.database_url.startswith("sqlite"):
            raise RuntimeError("Production requires a persistent PostgreSQL DATABASE_URL.")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.xai_key = os.getenv("XAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-6.1-sol")
        # Model identifiers are recorded on every completed job.
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        self.xai_model = os.getenv("XAI_MODEL", "grok-4.7")
        self.openai_reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium")
        self.xai_reasoning_effort = os.getenv("XAI_REASONING_EFFORT", "low")
        if self.openai_reasoning_effort not in ("low", "medium", "high"):
            raise RuntimeError("OPENAI_REASONING_EFFORT must be low, medium or high")
        if self.xai_reasoning_effort not in ("low", "medium", "high"):
            raise RuntimeError("XAI_REASONING_EFFORT must be low, medium or high")
        self.detector_key = os.getenv("GPTZERO_API_KEY", "")
        self.detector_provider = os.getenv("DETECTOR_PROVIDER", "local")
        self.detector_model_dir = os.getenv("DETECTOR_MODEL_DIR", "/opt/txtzi/detector")
        if self.detector_provider not in ("local", "gptzero"):
            raise RuntimeError("DETECTOR_PROVIDER must be local or gptzero")
        self.stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
        self.stripe_webhook = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.bootstrap_token = os.getenv("ADMIN_BOOTSTRAP_TOKEN", "")
        self.resend_key = os.getenv("RESEND_API_KEY", "")
        self.email_from = os.getenv("EMAIL_FROM", "")
        self.support_email = os.getenv("SUPPORT_EMAIL", "")
        self.worker_enabled = os.getenv("WORKER_ENABLED", "true").lower() == "true"
        self.retention_hours = max(1, min(int(os.getenv("RETENTION_HOURS", "168")), 720))
        self.max_words = 12000
        self.max_chars = 100000
        self.max_file_bytes = 20 * 1024 * 1024
        self.base_price = max(100, int(os.getenv("PRICE_BASE_CENTS", "399")))
        self.extra_price = max(1, int(os.getenv("PRICE_EXTRA_1000_CENTS", "200")))
        self.detector_price = max(1, int(os.getenv("PRICE_DETECTOR_1000_CENTS", "100")))
        self.ocr_price = max(0, int(os.getenv("PRICE_OCR_PAGE_CENTS", "20")))
        self.slide_price = max(0, int(os.getenv("PRICE_SLIDE_CENTS", "10")))
        # Promotional balance granted once per account each ISO week; set to 0 to disable.
        self.weekly_free_credits = max(0, int(os.getenv("WEEKLY_FREE_CREDITS", "500")))

    @property
    def detector_ready(self):
        if self.detector_provider == "gptzero":
            return bool(self.detector_key)
        from .local_detector import available
        return available(self.detector_model_dir)

    @property
    def detector_name(self):
        return "txtzi detector" if self.detector_provider == "local" else "GPTZero"

    @property
    def ai_ready(self):
        return bool(self.openai_key and self.anthropic_key and self.xai_key)

    @property
    def payments_ready(self):
        return bool(self.stripe_key and self.stripe_webhook)


settings = Settings()
