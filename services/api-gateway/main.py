from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import user, booking, notification, admin

app = FastAPI(
    title="API Gateway",
    description="Единая точка входа для blatnye-bratuyni",
    version="1.0.0"
)

# --------------------------- CORS middleware setup ---------------------------
# Можно оставить "*" для тестов или указать свой фронт: ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # или ["http://localhost:3000"] для безопасности
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ------------------------------------------------------------------------------

# Подключаем роуты, проксирующие бизнес-логику дальше
app.include_router(user.router, prefix="/users", tags=["users"])
app.include_router(booking.router, prefix="/bookings", tags=["bookings"])
app.include_router(notification.router, prefix="/notifications", tags=["notifications"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])

@app.get("/")
async def root():
    return {"status": "ok", "gateway": True}