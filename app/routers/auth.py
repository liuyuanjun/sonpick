from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse, SetupRequest, PasswordChangeRequest
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

bearer = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
    db: Session = Depends(get_db),
) -> str:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    from app.security import decode_token
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("sub") != "admin":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return "admin"
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    """前端据此判断是需要初始化（设置密码）还是正常登录。"""
    initialized = db.query(User).first() is not None
    return {"initialized": initialized}


@router.post("/setup", response_model=TokenResponse)
def setup(req: SetupRequest, db: Session = Depends(get_db)):
    """首次设置管理员密码；仅在数据库无用户时可用。"""
    if db.query(User).first() is not None:
        raise HTTPException(status_code=409, detail="管理员密码已设置")
    if len(req.password) < 6:
        raise HTTPException(status_code=422, detail="密码至少 6 位")
    user = User(password_hash=hash_password(req.password))
    db.add(user)
    db.commit()
    return TokenResponse(access_token=create_access_token())


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).first()
    if user is None:
        raise HTTPException(status_code=428, detail="请先设置管理员密码")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")
    return TokenResponse(access_token=create_access_token())


@router.put("/password")
def change_password(
    req: PasswordChangeRequest,
    user: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改管理员密码；需验证旧密码。"""
    db_user = db.query(User).first()
    if not db_user:
        raise HTTPException(status_code=428, detail="请先设置管理员密码")
    if not verify_password(req.old_password, db_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="旧密码错误")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=422, detail="新密码至少 6 位")
    db_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: str = Depends(get_current_user)):
    return {"username": user}
