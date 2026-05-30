from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "algo_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer   = "json",
    result_serializer = "json",
    accept_content    = ["json"],
    timezone          = "Asia/Kolkata",
    enable_utc        = True,
    broker_connection_retry_on_startup = True,
    beat_schedule = {
        "reset-daily-risk": {
            "task":     "tasks.reset_daily_risk",
            "schedule": crontab(hour=9, minute=15),
        },
        "renew-dhan-token": {
            "task":     "tasks.renew_dhan_token",
            "schedule": crontab(hour=7, minute=45),
        },
        "refresh-instrument-csv": {
            "task":     "tasks.refresh_instrument_csv",
            "schedule": crontab(hour=8, minute=0),
        },
    },
)
