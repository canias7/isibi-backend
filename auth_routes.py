from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import create_user, verify_user
from jose import jwt
import os
from datetime import datetime, timedelta

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"

def make_token(payload: dict) -> str:
    data = payload.copy()
    data["exp"] = datetime.utcnow() + timedelta(days=7)
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGO)


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    tenant_phone: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register")
def register(data: RegisterIn):
    try:
        create_user(data.email, data.password, data.tenant_phone)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
def login(data: LoginIn):
    user = verify_user(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user
