from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, TokenResponse
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


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).first()
    if user is None:
        user = User(password_hash=hash_password(req.password))
        db.add(user)
        db.commit()
    elif not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")
    return TokenResponse(access_token=create_access_token())


@router.get("/me")
def me(user: str = Depends(get_current_user)):
    return {"username": user}
