# BionicPRO — спринт 9

Решение двух заданий: усиление безопасности SSO (PKCE) и сервис отчётов
на связке Airflow + ClickHouse.

---

## Что внутри

| Каталог            | Назначение                                                      |
|--------------------|-----------------------------------------------------------------|
| `frontend/`        | React-приложение, авторизация через Keycloak, страница отчёта   |
| `keycloak/`        | `realm-export.json`: realm, роли, пользователи, клиенты         |
| `reports-service/` | Сервис отчётов на FastAPI, эндпоинт `GET /reports`              |
| `etl/`             | Airflow, ClickHouse, эмуляция CRM, DAG сборки витрины           |
| `docs/`            | Диаграммы архитектуры в draw.io                                 |

### Порты

| Сервис         | Адрес                           |
|----------------|---------------------------------|
| Фронтенд       | http://localhost:3000           |
| Сервис отчётов | http://localhost:8000           |
| Keycloak       | http://localhost:8080           |
| Airflow        | http://localhost:8081           |
| ClickHouse     | http://localhost:8123, TCP 9000 |
| CRM (эмуляция) | localhost:5434                  |

### Учётные записи

| Логин        | Пароль            | Роль             | Зачем                                      |
|--------------|-------------------|------------------|--------------------------------------------|
| `prothetic1` | `prothetic123`    | `prothetic_user` | Есть доступ к отчёту                       |
| `prothetic2` | `prothetic123`    | `prothetic_user` | Второй пользователь, для проверки изоляции |
| `user1`      | `password123`     | `user`           | Роли нет — проверка отказа в доступе       |
| Airflow      | `admin` / `admin` | —                | Веб-интерфейс Airflow                      |

---

## Запуск

```bash
# из корня репозитория
docker compose -f docker-compose.yaml -f etl/docker-compose.yaml up -d --build
```
---

## Проверка

### 1. Данные в источниках

```bash
docker compose exec clickhouse clickhouse-client -u bionic --password bionic -q "SELECT count() FROM bionic.telemetry"
```

Ожидается `120000` — тестовая телеметрия за последние ~10 дней.

```bash
docker compose exec crm_db psql -U crm_user -d crm_db -c "SELECT keycloak_user_id, full_name FROM clients"
```

Три клиента. Их `keycloak_user_id` совпадают с идентификаторами
пользователей `prothetic1..3` в Keycloak.

### 2. ETL

Откройте http://localhost:8081 (`admin` / `admin`).

DAG `bionicpro_report_mart` запускается по расписанию и при первом старте
догоняет историю за 10 дней.

```bash
docker compose exec clickhouse clickhouse-client -u bionic --password bionic -q "
SELECT report_date, user_id, events_total, avg_response_ms
FROM bionic.report_mart FINAL
ORDER BY report_date DESC LIMIT 5"
```

Витрина заполнена: строки в разрезе «пользователь × дата» с уже
посчитанными агрегатами.

```bash
docker compose exec clickhouse clickhouse-client -u bionic --password bionic -q "SELECT * FROM bionic.etl_watermark FINAL"
```

`last_loaded_date` — граница обработанных данных. Сервис отчётов не
отдаёт периоды правее неё.

### 3. Вход и PKCE

Откройте http://localhost:3000
Войдите как `prothetic1` / `prothetic123`.

Клиент `reports-frontend` настроен на обязательный PKCE: при попытке авторизоваться без `code_challenge` Keycloak отвечает `invalid_request`.

### 4. Отчёт в интерфейсе

На странице выберите период и нажмите **Получить отчёт**.

### 5. Доступ только к своим данным

**Без аутентификации:**

```bash
curl -i http://localhost:8000/reports
```

```bash
TOKEN=<вставьте токен>

curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/reports?user_id=22222222-2222-2222-2222-222222222222" | grep -o '"user_id":"[^"]*"'
```
---


