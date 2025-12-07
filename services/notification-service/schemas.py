from pydantic import BaseModel, EmailStr

class NotificationCreate(BaseModel):
    email: EmailStr
    subject: str
    text: str
    
class NotificationInternal(BaseModel):
    user_id: int
    type: str
    title: str
    message: str