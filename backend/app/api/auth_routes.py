"""Auth endpoints: register (tenant-scoped), login, current identity."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, login_user, register_user
from app.auth.service import CurrentUser
from app.database.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


@router.post("/register", summary="Register user + tenant (first user is admin)")
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    return register_user(db, tenant_name=body.tenant_name, email=body.email,
                         password=body.password, full_name=body.full_name)


@router.post("/login", summary="Exchange credentials for a JWT")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    return login_user(db, email=body.email, password=body.password)


@router.get("/me", summary="Current identity")
def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    return {"id": user.id, "tenant_id": user.tenant_id, "email": user.email, "role": user.role}