import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./econest.db")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # obligatorio: ver validate_settings()
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "./screenshots"))
MAX_SCREENSHOT_BYTES = int(os.getenv("MAX_SCREENSHOT_BYTES", 2_000_000))
MAX_FUTURE_SKEW_SECONDS = int(os.getenv("MAX_FUTURE_SKEW_SECONDS", 300))  # margen por relojes desfasados

# --- límites de tamaño (protegen la memoria del servidor frente a peticiones enormes)
MAX_DETECTIONS_PER_EVENT = int(os.getenv("MAX_DETECTIONS_PER_EVENT", 100))
# base64 ocupa 4 caracteres por cada 3 bytes
MAX_SCREENSHOT_B64_CHARS = (MAX_SCREENSHOT_BYTES + 2) // 3 * 4
# cuerpo total de una petición: captura en base64 + margen para el resto del JSON
MAX_BODY_BYTES = MAX_SCREENSHOT_B64_CHARS + 128 * 1024

MIN_ADMIN_TOKEN_LENGTH = 16
_WEAK_ADMIN_TOKENS = {"change-me", "changeme", "admin", "password", "secret", "token"}


def validate_settings() -> None:
    """Se llama al arrancar: la API no debe levantarse con un token de admin ausente o débil."""
    tok = ADMIN_TOKEN
    if not tok:
        raise RuntimeError("ADMIN_TOKEN no está definido. Genera uno con: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    if tok.lower() in _WEAK_ADMIN_TOKENS or len(tok) < MIN_ADMIN_TOKEN_LENGTH:
        raise RuntimeError(f"ADMIN_TOKEN es demasiado débil (mínimo {MIN_ADMIN_TOKEN_LENGTH} caracteres y no un valor típico).")

# --- CORS: orígenes de navegador autorizados a llamar a la API (separados por comas; "*" = todos)
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]

# --- estado de los dispositivos
# Una Raspberry se considera "online" si su último heartbeat es más reciente que esto.
ONLINE_THRESHOLD_SECONDS = int(os.getenv("ONLINE_THRESHOLD_SECONDS", 180))
