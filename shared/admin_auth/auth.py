"""
shared/admin_auth/auth.py
Xac thuc Admin Portal: bcrypt password hash + JWT token.

Phu thuoc:
  bcrypt>=4.0.0
  python-jose[cryptography]>=3.3.0
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    import bcrypt as _bcrypt_lib
    _BCRYPT_OK = True
except ImportError:
    _BCRYPT_OK = False

try:
    from jose import JWTError, jwt as jose_jwt
    _JOSE_OK = True
except ImportError:
    _JOSE_OK = False

# ------------------------------------------------------------------ config ---
_JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "").strip()
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = int(os.getenv("ADMIN_TOKEN_EXPIRE_HOURS", "8"))

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------- password ---

def hash_password(plain: str) -> str:
    """Hash mat khau voi bcrypt. Raise RuntimeError neu bcrypt chua cai."""
    if not _BCRYPT_OK:
        raise RuntimeError("bcrypt chua duoc cai dat. Chay: pip install bcrypt")
    salt = _bcrypt_lib.gensalt(rounds=12)
    hashed = _bcrypt_lib.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """So sanh mat khau plain voi hash bcrypt."""
    if not _BCRYPT_OK:
        return False
    try:
        return _bcrypt_lib.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ------------------------------------------------------------------- token ---

def create_admin_token(username: str, role: str = "coordinator") -> dict[str, Any]:
    """
    Tao JWT token cho admin.
    Returns: { access_token, token_type, expires_in }
    """
    if not _JOSE_OK:
        raise RuntimeError("python-jose[cryptography] chua duoc cai dat.")
    if not _JWT_SECRET:
        raise RuntimeError("ADMIN_JWT_SECRET chua duoc cau hinh.")
    expire = datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jose_jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": _JWT_EXPIRE_HOURS * 3600,
    }


def verify_admin_token(token: str) -> dict[str, Any]:
    """
    Giai ma va xac minh JWT.
    Returns: { sub: username, role: role }
    Raises: HTTPException(401) neu token khong hop le.
    """
    if not _JOSE_OK:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service chua san sang.",
        )
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service chua duoc cau hinh.",
        )
    try:
        payload = jose_jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        role: str = payload.get("role", "coordinator")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token khong hop le.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"sub": username, "role": role}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token khong hop le hoac da het han.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ----------------------------------------------------- FastAPI dependency ---

def require_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI Dependency: Kiem tra Bearer JWT trong Authorization header."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chua xac thuc. Vui long dang nhap.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_admin_token(credentials.credentials)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """Gion nhu require_admin_token nhung tra ve payload de dung trong handler."""
    return require_admin_token(credentials)
