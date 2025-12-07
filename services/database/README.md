# Database сервис

Контейнеризированный PostgreSQL для микросервисов blatnye-bratuyni.
- Автоматически создает схемы для users и bookings при запуске (см. init.sql).
- Для продвинутой работы/миграций есть migrate.py (ручное обновление схемы, демо).

## Инициализация

При старте контейнера автоматически инициализирует DB по init.sql

## Запуск отдельно:
```bash
docker build -t blatnye-db .
docker run -p 5432:5432 blatnye-db
```
Рекомендуется запускать через общий docker-compose.