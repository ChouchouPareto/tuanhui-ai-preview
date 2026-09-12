from datetime import timedelta
from sqlalchemy import select
from app.models import GenerationWorkerHeartbeat, utc_now


def worker_available(db):
    return db.scalar(select(GenerationWorkerHeartbeat.id).where(
        GenerationWorkerHeartbeat.updated_at > utc_now() - timedelta(seconds=45)
    ).limit(1)) is not None
