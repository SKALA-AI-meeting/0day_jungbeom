"""인증: bcrypt 비밀번호, 역할별 JWT, 초대 토큰 해시, FastAPI 의존성.

역할: admin(company_id), candidate(session_id), debrief(session_id, 디브리핑만 읽음).
생명주기와 만료 규칙은 docs/common/contracts.md의 인증 생명주기 표가 정본이다.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

ALGORITHM = "HS256"
INVITE_TTL = timedelta(hours=72)
DEBRIEF_TTL = timedelta(days=7)
SESSION_JWT_MARGIN = timedelta(minutes=120)

_bearer = HTTPBearer(auto_error=False)
Bearer = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def new_invite_token() -> tuple[str, str]:
    """(원문, 해시). 원문은 링크에만 쓰고 DB에는 해시만 저장한다."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_invite_token(raw)


def hash_invite_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Principal:
    role: str  # admin | candidate | debrief
    subject: uuid.UUID  # admin_id 또는 session_id
    company_id: uuid.UUID | None = None


def _encode(claims: dict, ttl: timedelta, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {**claims, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITHM)


def admin_token(admin_id: uuid.UUID, company_id: uuid.UUID, ttl: timedelta = timedelta(hours=12)):
    return _encode({"role": "admin", "sub": str(admin_id), "company_id": str(company_id)}, ttl)


def session_token(session_id: uuid.UUID, session_minutes: int) -> str:
    """세션 JWT. 만료 = now + session_minutes + 120분."""
    ttl = timedelta(minutes=session_minutes) + SESSION_JWT_MARGIN
    return _encode({"role": "candidate", "sub": str(session_id)}, ttl)


def debrief_deadline(ended_at: datetime) -> datetime:
    """디브리핑을 읽을 수 있는 기한: 세션 종료 시각 + 7일."""
    return ended_at + DEBRIEF_TTL


def debrief_token(session_id: uuid.UUID, expires_at: datetime | None = None) -> str:
    """expires_at을 주면 그 시각이 exp다(종료 기준 기한). 없으면 지금부터 7일."""
    now = datetime.now(UTC)
    ttl = expires_at - now if expires_at is not None else DEBRIEF_TTL
    return _encode({"role": "debrief", "sub": str(session_id)}, ttl, now)


def decode_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        company = claims.get("company_id")
        return Principal(
            role=claims["role"],
            subject=uuid.UUID(claims["sub"]),
            company_id=uuid.UUID(company) if company else None,
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "invalid token") from exc


def _error(code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(code, detail={"error": {"code": error_code, "message": message}})


def _principal(creds: HTTPAuthorizationCredentials | None) -> Principal:
    if creds is None:
        raise _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "missing bearer token")
    return decode_token(creds.credentials)


def require_admin(creds: Bearer) -> Principal:
    principal = _principal(creds)
    if principal.role != "admin" or principal.company_id is None:
        raise _error(status.HTTP_403_FORBIDDEN, "forbidden", "admin only")
    return principal


def _require_session(roles: set[str]):
    def dependency(session_id: Annotated[uuid.UUID, Path()], creds: Bearer) -> Principal:
        principal = _principal(creds)
        if principal.role not in roles or principal.subject != session_id:
            raise _error(status.HTTP_403_FORBIDDEN, "forbidden", "other session")
        return principal

    return dependency


# 경로의 session_id와 토큰의 세션이 같아야 한다. 다르면 403.
require_candidate = _require_session({"candidate"})
require_debrief_reader = _require_session({"candidate", "debrief"})


def require_internal(x_internal_token: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().internal_token
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "invalid internal token")
