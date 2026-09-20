"""
ETL для сервиса отчётов BionicPRO.

Шаги:
  1. load_crm_clients   — инкрементальная выгрузка клиентов из CRM в ClickHouse
  2. build_report_mart  — агрегация телеметрии за сутки + джойн с CRM в витрину
  3. update_watermark   — фиксация границы обработанных данных

Watermark обновляется последним: сервис отчётов не отдаёт периоды,
которых ещё нет в витрине.
"""

import os
from datetime import datetime, timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from clickhouse_driver import Client

CH_SETTINGS = dict(
    host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
    port=int(os.environ.get("CLICKHOUSE_PORT", 9000)),
    database=os.environ.get("CLICKHOUSE_DB", "bionic"),
    user=os.environ.get("CLICKHOUSE_USER", "bionic"),
    password=os.environ.get("CLICKHOUSE_PASSWORD", "bionic"),
)

BATCH_SIZE = 50_000


def clickhouse() -> Client:
    return Client(**CH_SETTINGS)


@dag(
    dag_id="bionicpro_report_mart",
    description="Витрина отчётности по работе протезов",
    schedule="0 2 * * *",
    start_date=pendulum.datetime(2026, 9, 10, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    default_args={
        "owner": "bionicpro",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["bionicpro", "etl", "reports"],
)
def report_mart_etl():

    @task
    def load_crm_clients() -> int:
        """Инкрементальная выгрузка справочника клиентов из CRM."""
        ch = clickhouse()

        # точка отсчёта — самая свежая запись, уже лежащая в ClickHouse
        rows = ch.execute("SELECT max(updated_at) FROM bionic.crm_clients")
        since = rows[0][0] or datetime(1970, 1, 1)

        pg = PostgresHook(postgres_conn_id="crm_db")
        records = pg.get_records(
            """
            SELECT username,
                   full_name,
                   city,
                   model,
                   purchased_at,
                   updated_at
            FROM clients
            WHERE updated_at > %s
            ORDER BY updated_at
            """,
            parameters=[since],
        )

        if not records:
            return 0

        ch.execute(
            """
            INSERT INTO bionic.crm_clients
                (user_id, full_name, city, model, purchased_at, updated_at)
            VALUES
            """,
            [tuple(r) for r in records],
        )
        return len(records)

    @task
    def build_report_mart(ds=None) -> int:
        """Агрегация телеметрии за сутки в разрезе пользователей."""
        ch = clickhouse()

        # ReplacingMergeTree по built_at: повторный прогон перекроет прошлый
        ch.execute(
            """
            INSERT INTO bionic.report_mart
                (user_id, report_date, full_name, model, events_total,
                 avg_response_ms, p95_response_ms, avg_signal,
                 min_battery_pct, errors_total)
            SELECT
                t.user_id,
                toDate(%(day)s)                        AS report_date,
                any(c.full_name)                       AS full_name,
                any(c.model)                           AS model,
                count()                                AS events_total,
                avg(t.response_ms)                     AS avg_response_ms,
                quantile(0.95)(t.response_ms)          AS p95_response_ms,
                avg(t.signal_quality)                  AS avg_signal,
                min(t.battery_pct)                     AS min_battery_pct,
                countIf(t.error_code != '')            AS errors_total
            FROM bionic.telemetry AS t
            LEFT JOIN (
                SELECT user_id, full_name, model
                FROM bionic.crm_clients FINAL
            ) AS c ON t.user_id = c.user_id
            WHERE t.event_time >= toDateTime(%(day)s)
              AND t.event_time <  toDateTime(%(day)s) + INTERVAL 1 DAY
            GROUP BY t.user_id
            """,
            {"day": ds},
        )

        rows = ch.execute(
            """
            SELECT count()
            FROM bionic.report_mart
            WHERE report_date = toDate(%(day)s)
            """,
            {"day": ds},
        )
        return rows[0][0]

    @task
    def update_watermark(ds=None) -> str:
        """Граница обработанных данных для сервиса отчётов."""
        ch = clickhouse()
        ch.execute(
            """
            INSERT INTO bionic.etl_watermark (mart_name, last_loaded_date)
            VALUES
            """,
            [("report_mart", datetime.strptime(ds, "%Y-%m-%d").date())],
        )
        return ds

    load_crm_clients() >> build_report_mart() >> update_watermark()


report_mart_etl()
