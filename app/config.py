import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or "demo-key"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
APP_ENV = os.getenv("APP_ENV", "development")

_raw_database_url = os.getenv("DATABASE_URL")
if APP_ENV == "production" and _raw_database_url:
    DATABASE_URL = _raw_database_url
else:
    DATABASE_URL = _raw_database_url if _raw_database_url and "supabase" not in _raw_database_url.lower() and "postgres" not in _raw_database_url.lower() else "sqlite+aiosqlite:///./procura_demo.db"