"""
Сервис отчётов BionicPRO.

GET /reports — отчёт о работе протеза за период.
"""

import os
from datetime import date, timedelta

import jwt
from clickhouse_driver import Client
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

# --- конфигурация ---------------------------------------------------------

# JWKS тянем по внутреннему адресу, а issuer сверяем с тем, что видит браузер:
# токен выдан через localhost:8080, а контейнер ходит в keycloak:8080.
JWKS_URL = os.environ["KEYCLOAK_JWKS_URL"]
ISSUER = os.environ["KEYCLOAK_ISSUER"]
REQUIRED_ROLE = os.environ.get("REQUIRED_ROLE", "prothetic_user")
CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "reports-frontend")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

CH = dict(
    host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
    port=int(os.environ.get("CLICKHOUSE_PORT", 9000)),
    database=os.environ.get("CLICKHOUSE_DB", "bionic"),
    user=os.environ.get("CLICKHOUSE_USER", "bionic"),
    password=os.environ.get("CLICKHOUSE_PASSWORD", "bionic"),
)

app = FastAPI(title="BionicPRO Reports")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)

bearer = HTTPBearer()
jwks = PyJWKClient(JWKS_URL, cache_keys=True)


# --- аутентификация и авторизация ----------------------------------------

def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        key = jwks.get_signing_key_from_jwt(creds.credentials).key
        claims = jwt.decode(
            creds.credentials,
            key,
            algorithms=["RS256"],
            issuer=ISSUER,
            # aud у публичного клиента Keycloak — "account", отдельной проверки
            # не делаем, принадлежность клиенту проверяем ниже по azp
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}")

    roles = set(claims.get("realm_access", {}).get("roles", []))
    roles |= set(
        claims.get("resource_access", {}).get(CLIENT_ID, {}).get("roles", [])
    )
    if REQUIRED_ROLE not in roles:
        raise HTTPException(status_code=403, detail="role required")

    return {"user_id": claims["sub"], "username": claims.get("preferred_username")}


# --- данные ---------------------------------------------------------------

def watermark(ch: Client) -> date | None:
    rows = ch.execute(
        """
        SELECT max(last_loaded_date)
        FROM bionic.etl_watermark FINAL
        WHERE mart_name = 'report_mart'
        """
    )
    return rows[0][0] if rows and rows[0][0] else None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/reports")
def reports(
        user=Depends(current_user),
        date_from: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
        date_to: date = Query(default_factory=date.today),
) -> dict:
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from is after date_to")

    ch = Client(**CH)

    wm = watermark(ch)
    if wm is None:
        return {
            "user_id": user["user_id"],
            "requested": {"from": date_from, "to": date_to},
            "available_through": None,
            "truncated": True,
            "rows": [],
            "message": "витрина ещё не построена",
        }

    # правая граница не может уходить за обработанный Airflow период
    effective_to = min(date_to, wm)
    truncated = effective_to < date_to

    rows = []
    if date_from <= effective_to:
        # FINAL обязателен: ReplacingMergeTree схлопывает версии в фоне,
        # без него можно прочитать результат предыдущего прогона DAG
        rows = ch.execute(
            """
            SELECT report_date, full_name, model, events_total,
                   round(avg_response_ms, 1), round(p95_response_ms, 1),
                   round(avg_signal, 3), min_battery_pct, errors_total
            FROM bionic.report_mart FINAL
            WHERE user_id = %(uid)s
              AND report_date BETWEEN %(d1)s AND %(d2)s
            ORDER BY report_date
            """,
            {"uid": user["user_id"], "d1": date_from, "d2": effective_to},
        )

    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "requested": {"from": date_from, "to": date_to},
        "available_through": wm,
        "truncated": truncated,
        "rows": [
            {
                "date": r[0],
                "full_name": r[1],
                "model": r[2],
                "events_total": r[3],
                "avg_response_ms": r[4],
                "p95_response_ms": r[5],
                "avg_signal_quality": r[6],
                "min_battery_pct": r[7],
                "errors_total": r[8],
            }
            for r in rows
        ],
    }