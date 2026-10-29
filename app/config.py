"""All settings come from environment variables (see .env.example)."""
import os


def _load_dotenv(path: str = ".env") -> None:
    # Local development only; on Render variables are set in the dashboard.
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()
_env = os.environ.get

BOT_TOKEN = _env("BOT_TOKEN", "")
DATABASE_URL = _env("DATABASE_URL", "")
GEMINI_API_KEY = _env("GEMINI_API_KEY", "")

# Tried in order; next model when one is overloaded (503) or rate-limited (429). Lite models go first:
# their free daily quota is much larger than flash (20 requests/day per flash model).
_DEFAULT_CHAT = "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.6-flash,gemini-3.5-flash,gemini-3.8-flash,gemini-3.7-flash"
CHAT_MODELS = [m.strip() for m in _env("CHAT_MODELS", _DEFAULT_CHAT).split(",")]
# Picks applicable laws from the ~40k-char law list: measured fastest/most available first.
ROUTER_MODELS = [m.strip() for m in _env("ROUTER_MODELS", "gemini-3.1-flash-lite,gemini-3.6-flash,gemini-3.5-flash-lite").split(",")]
LITE_MODELS = [m.strip() for m in _env("LITE_MODELS", "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.6-flash").split(",")]
EMBED_MODEL = _env("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = 768  # must match vector(768) in db.SCHEMA

# Webhook mode when set (Render sets RENDER_EXTERNAL_URL itself); long polling otherwise.
WEBHOOK_BASE_URL = _env("WEBHOOK_BASE_URL") or _env("RENDER_EXTERNAL_URL", "")
WEBHOOK_SECRET = _env("WEBHOOK_SECRET", "")
PORT = int(_env("PORT", "10000"))

ADMIN_IDS = {int(x) for x in _env("ADMIN_IDS", "").split(",") if x.strip()}
FREE_DAILY_LIMIT = int(_env("FREE_DAILY_LIMIT", "25"))

# Manual card-transfer payments.
CARD_NUMBER = _env("CARD_NUMBER", "")
CARD_HOLDER = _env("CARD_HOLDER", "")
DOC_PRICE = int(_env("DOC_PRICE", "15000"))  # so'm per paid document
RECEIPT_MAX_AGE_HOURS = int(_env("RECEIPT_MAX_AGE_HOURS", "48"))


def require(*names: str) -> None:
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
