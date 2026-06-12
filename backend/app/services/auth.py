from datetime import datetime, timedelta, timezone

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.config import Settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """使用 Argon2 对密码进行不可逆哈希。"""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """验证密码；格式异常时统一按验证失败处理。"""
    try:
        return password_hash.verify(password, hashed_password)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, settings: Settings) -> str:
    """签发包含用户 ID 和过期时间的 JWT。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> int | None:
    """解析 JWT，任何签名、过期或字段错误都视为无效令牌。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
