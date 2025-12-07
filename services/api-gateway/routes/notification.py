from fastapi import APIRouter, Request, Response
import requests
from config import NOTIFICATION_SERVICE_URL

router = APIRouter()

@router.post("/")
async def notify(request: Request):
    body = await request.json()
    resp = requests.post(f"{NOTIFICATION_SERVICE_URL}/notify", json=body)
    return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get('content-type',"application/json"))