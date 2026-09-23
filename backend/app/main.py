from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.creation_api import router as creation_router
from app.dialogue_api import router as dialogue_router
from app.canvas_api import router as canvas_router
from app.agent_api import router as agent_router
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
        from app.services.intake_understanding import recover_stale_understanding
        recover_stale_understanding(db)
    yield


app = FastAPI(title="团绘AI M1 API", version="0.11.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[item.strip() for item in settings.allowed_origins.split(",")], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(creation_router)
app.include_router(dialogue_router)
app.include_router(canvas_router)
app.include_router(agent_router)


@app.get("/health")
def health():
    with SessionLocal() as db:
        ready = worker_available(db)
    return {"status": "ok", "version": "0.11.1", "agent_contract": "bounded-agent-v1", "workbench": "/workbench", "generation_contract": "region-master-v3", "workflow_contract": "creative-workflow-v1", "template_catalog": "layout-regions-v2", "generation_worker_ready": ready, "stage": "M1-internal-preview", "default_flow": "intake-confirmation", "analyzer_mode": settings.analyzer_mode, "image_provider": "qwen"}


@app.get("/api/v1/design-system/contracts")
def design_contracts():
    from app.services.layout_catalog import ALL_LAYOUTS, catalog_entry, OUTPUT_SPECS
    from app.services.category_policy import PACKS
    from app.services.creative_workflow import ROLE_CONTRACTS
    return {"version":"0.11.1", "review_status":"pending_owner_review", "templates":[catalog_entry(x) for x in ALL_LAYOUTS],
            "categories":PACKS, "roles":ROLE_CONTRACTS, "outputs":OUTPUT_SPECS,
            "figma_review":"https://www.figma.com/design/3NScJVMCFE33Ec7lI5iVyW?node-id=7-2"}


@app.get("/api/v1/editor/contracts")
def editor_contracts():
    from app.canvas_schemas import Scene, SIZES
    return {"schema_version": "editable-scene-v1", "render_contract": "native-render-v1",
            "stage": "functional-workbench-preview", "scene_schema": Scene.model_json_schema(),
            "master_sizes": {**SIZES, "single": (800, 600, 1)},
            "operations": ["add", "update", "remove", "lock", "unlock", "restore", "fork"],
            "requires": ["project_id", "document_id", "base_version_id", "request_key"],
            "local_edit_image_calls": 0, "semantic_agent_ready": True,
            "semantic_agent_scope": ["bounded_preparation", "text_edit_proposal"],
            "legacy_flat_image_layer_recovery": False, "frontend_ready": True, "formal_design_approved": False}


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    request_id = request.headers.get("x-request-id", "unknown")
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "服务暂时不可用", "request_id": request_id}})
