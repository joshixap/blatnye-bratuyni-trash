from fastapi import APIRouter, HTTPException
from mailer import send_email
from schemas import NotificationCreate

router = APIRouter()

@router.post("/notify/email")
async def notify_email(notification: NotificationCreate):
    result = send_email(notification)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to send email")
    return {"status": "sent"}

# TODO: bulk and internal endpoints