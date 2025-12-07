from sqlalchemy.orm import Session
from models import Notification

def create_notification(db: Session, user_id: int, type: str, title: str, message: str):
    notif = Notification(user_id=user_id, type=type, title=title, message=message)
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif

def get_unsent_notifs(db: Session):
    return db.query(Notification).filter_by(sent=False).all()