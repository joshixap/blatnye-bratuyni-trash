# Notification Service

## Features

- POST `/notify/email`: отправка email уведомления (через SMTP)
- TODO: массовые рассылки (`/notify/bulk`)
- TODO: внутренние/system уведомления (`/notify/internal`)
- TODO: очередь сообщений (RabbitMQ/Redis)

## Переменные окружения

```
SMTP_SERVER=
SMTP_PORT=587
EMAIL_USER=
EMAIL_PASS=
```

## Запуск

```sh
uvicorn src.main:app --reload
```

## Пример запроса

```http
POST /notify/email
Content-Type: application/json

{
  "email": "user@example.com",
  "subject": "Booking Confirmed",
  "text": "Ваша бронь подтверждена!"
}
```

## Интеграция с Booking/User Service

- Сервис принимает POST запросы от Booking/User Service для рассылки email.
- TODO: добавить поддержку очереди для асинхронных уведомлений.