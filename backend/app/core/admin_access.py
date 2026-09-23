"""Internal console guard. Separate from future merchant identity/tenancy."""
import secrets
from fastapi import Header, HTTPException
from app.core.config import settings


def require_admin(authorization: str | None = Header(default=None)):
    token = settings.admin_api_token
    if len(token) < 32:
        raise HTTPException(503, detail="内部后台未配置访问密钥，管理接口已关闭")
    supplied = (authorization or "").removeprefix("Bearer ")
    if not authorization or not authorization.startswith("Bearer ") or not secrets.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(401, detail="需要管理员身份")
