from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field

from crud import (
    create_user,
    confirm_user,
    get_user_by_email,
    create_recovery_code,
    reset_password
)

from auth import verify_password, create_access_token
from config import SessionLocal

router = APIRouter()

class RegisterModel(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)

class ConfirmModel(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)

class LoginModel(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class RecoverModel(BaseModel):
    email: EmailStr

class ResetModel(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/users/register")
def register_user(data: RegisterModel, db: Session = Depends(get_db)):
    if get_user_by_email(db, data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    create_user(db, data.name, data.email, data.password)
    return {"message": "User created. Check your email for confirmation code."}

@router.post("/users/confirm")
def confirm_email(data: ConfirmModel, db: Session = Depends(get_db)):
    if confirm_user(db, data.email, data.code):
        return {"message": "Email confirmed"}
    raise HTTPException(status_code=400, detail="Invalid confirmation code")

@router.post("/users/login")
def login(data: LoginModel, db: Session = Depends(get_db)):
    user = get_user_by_email(db, data.email)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.confirmed:
        raise HTTPException(status_code=403, detail="Email not confirmed")
    token = create_access_token({"user_id": user.id, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/users/recover")
def recover(data: RecoverModel, db: Session = Depends(get_db)):
    if not create_recovery_code(db, data.email):
        raise HTTPException(status_code=404, detail="Email not registered")
    return {"message": "Recovery code sent"}

@router.post("/users/reset")
def reset(data: ResetModel, db: Session = Depends(get_db)):
    if reset_password(db, data.email, data.code, data.new_password):
        return {"message": "Password reset"}
    raise HTTPException(status_code=400, detail="Invalid recovery code")
