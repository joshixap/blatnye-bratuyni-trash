# API Gateway для "blatnye-bratuyni"

Маршрутизирует все обращения фронтенда/клиентов, проксирует к микросервисам, обрабатывает JWT-авторизацию.

- `/users/*`      → User Service
- `/bookings/*`   → Booking Service
- `/notifications/*` → Notification Service

## Запуск:

```bash
docker build -t api-gateway .
docker run -p 8000:8000 api-gateway
# или через docker-compose (см. корень репо)
```