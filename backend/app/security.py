import hashlib
import hmac

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import Device

bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_admin(cred: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not cred or not config.ADMIN_TOKEN or not hmac.compare_digest(cred.credentials, config.ADMIN_TOKEN):
        raise HTTPException(401, "Invalid admin token")


def require_device(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Device:
    if not cred:
        raise HTTPException(401, "Missing device token")
    device = db.scalar(select(Device).where(Device.token_hash == hash_token(cred.credentials)))
    if not device:
        raise HTTPException(401, "Invalid device token")
    return device
