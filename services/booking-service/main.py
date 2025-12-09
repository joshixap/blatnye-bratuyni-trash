# services/booking-service/app/main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager

from routes import router as user_router
from admin import router as admin_router

from db import engine
from models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ----------------------------
    # ВРЕМЕННОЕ РЕШЕНИЕ:
    # создаём таблицы при старте сервиса.
    # Потом это будет заменено Alembic миграциями.
    # ----------------------------
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield  # ← запуск приложения


app = FastAPI(
    title="Booking Service",
    lifespan=lifespan,
)


@app.get("/", tags=["service"])
async def root():
    return {"message": "Booking Service is running"}


app.include_router(user_router)
app.include_router(admin_router)
