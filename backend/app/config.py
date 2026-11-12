import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./econest.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "./screenshots"))
MAX_SCREENSHOT_BYTES = int(os.getenv("MAX_SCREENSHOT_BYTES", 2_000_000))
MAX_FUTURE_SKEW_SECONDS = int(os.getenv("MAX_FUTURE_SKEW_SECONDS", 300))  # margen por relojes desfasados
