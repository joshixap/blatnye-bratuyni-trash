from sqlalchemy.orm import Session
from models import User
from auth import hash_password
from email_utils import generate_code, send_email

def create_user(db: Session, name: str, email: str, password: str):
    code = generate_code()
    user = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        confirmation_code=code
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    send_email(email, "Email confirmation", f"Your code: {code}")

    return user

def confirm_user(db: Session, email: str, code: str):
    user = db.query(User).filter(User.email == email).first()
    if user and user.confirmation_code == code:
        user.confirmed = True
        user.confirmation_code = None
        db.commit()
        return True
    return False

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def create_recovery_code(db: Session, email: str):
    user = get_user_by_email(db, email)
    if not user:
        return False
    code = generate_code()
    user.recovery_code = code
    db.commit()

    send_email(email, "Password recovery", f"Your code: {code}")
    return True

def reset_password(db: Session, email: str, code: str, new_password: str):
    user = get_user_by_email(db, email)
    if user and user.recovery_code == code:
        user.hashed_password = hash_password(new_password)
        user.recovery_code = None
        db.commit()
        return True
    return False
