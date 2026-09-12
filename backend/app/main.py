from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.creation_api import router as creation_router
from app.core.config import settings
from app.core.database import Base, engine
from app.core.database import SessionLocal
from app.services.analysis import recover_analysis_tasks
from app.services.worker_status import worker_available


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        recover_analysis_tasks(db)
    yield


app = FastAPI(title="团绘AI M1 API", version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[item.strip() for item in settings.allowed_origins.split(",")], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(creation_router)


@app.get("/health")
def health():
    with SessionLocal() as db:
        ready = worker_available(db)
    return {"status": "ok", "version": "0.9.3", "generation_worker_ready": ready, "stage": "M1-rules-internal", "default_flow": "intake-confirmation", "analyzer_mode": settings.analyzer_mode, "image_provider": "qwen"}


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    request_id = request.headers.get("x-request-id", "unknown")
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用", "request_id": request_id}})
