"""Offline, isolated first-stage routing evaluation; never an image/model benchmark.

Run: .venv/bin/python scripts/evaluate_intent.py
Reports are exclusive-create. Context coverage is explicit; missing capabilities
are not counted as successful execution merely because the router abstained.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]

# Manually encoded fixture profiles, not expected answers. IDs prevent inference
# from expected labels or accidental assumption that every case has a result.
PROFILES = {
    "E001": "done", "E002": "done", "E003": "running", "E004": "empty",
    "E005": "done", "E006": "done", "E007": "ambiguous", "E008": "old_selected",
    "E009": "ambiguous", "E010": "done", "E011": "done", "E012": "empty",
    "E013": "empty", "E014": "empty", "E015": "empty", "E016": "done",
    "E017": "running", "E018": "done", "E019": "unknown", "E020": "queued",
    "E021": "running", "E022": "done", "E023": "done", "E024": "done",
    "E025": "done", "E026": "failed", "E027": "done", "E028": "empty",
    "E029": "empty", "E030": "empty", "E031": "done", "E032": "ambiguous",
    "E033": "empty", "E034": "empty", "E035": "done", "E036": "done",
    "E037": "empty", "E038": "done", "E039": "done", "E040": "empty",
}

NORMALIZED = {
    "report_issue": {"diagnose"}, "status": {"query_status"},
    "question": {"consult"}, "cancel": {"cancel"}, "unclear": {"clarify"},
    "edit_copy": {"edit_copy"}, "new_creation": {"new_generation", "regenerate", "edit_visual"},
}


def score(case, response):
    """Stage-level checks only. 'prepare' is NOT an executed image call."""
    expected = case["expected"]
    match = expected["intent"] in NORMALIZED.get(response.get("intent"), set())
    # Preparing an explicit new request without generation budget is legitimate:
    # the downstream confirmation boundary has not been crossed yet.
    unauthorized_prepare = bool(response.get("can_prepare") and expected["intent"] not in {
        "new_generation", "regenerate", "edit_visual", "execute_frozen_plan", "edit_copy"})
    return {"intent_match": match, "unexpected_image_preparation": unauthorized_prepare,
            "workflow_acceptance": "not_run",
            "reason": "仅评测真实路由阶段；完整动作、授权、素材识别和视觉效果未由此用例执行。"}


def evaluate(dataset):
    # Imports only after process-local environment points to disposable data.
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.main import app
    from app.models import ModelCallRecord, StoreProject, TaskStatus, WorkflowTask
    from app.services.dialogue_routing import VERSION
    outcomes = []
    with TestClient(app, raise_server_exceptions=False) as client:
        for case in dataset["cases"]:
            profile = PROFILES.get(case["id"])
            if profile is None:
                outcomes.append({"case_id": case["id"], "status": "unsupported_fixture"})
                continue
            with SessionLocal() as db:
                project = StoreProject(name="离线评测项目")
                db.add(project)
                db.flush()
                project_id, target_id = project.id, None
                states = {"running": TaskStatus.RUNNING, "queued": TaskStatus.PENDING,
                          "unknown": TaskStatus.NEEDS_USER, "failed": TaskStatus.FAILED_FINAL}
                tasks = []
                if profile != "empty":
                    for n in range(2 if profile in {"ambiguous", "old_selected"} else 1):
                        task = WorkflowTask(project_id=project_id, task_type="group_buying_image_generation",
                            status=states.get(profile, TaskStatus.SUCCEEDED), result={"fixture_version": n + 1})
                        if profile == "unknown":
                            task.error_code = "RECONCILING"
                        db.add(task)
                        db.flush()
                        tasks.append(task)
                    if profile != "ambiguous":
                        target_id = tasks[0].id
                db.commit()
                before = {t.id: (t.status.value, t.result) for t in tasks}
            started = datetime.now(timezone.utc).isoformat()
            body = {"project_id": project_id, "text": case["message"]}
            if target_id:
                body["task_id"] = target_id
            response = client.post("/api/v1/dialogue/route", json=body)
            result = response.json()
            with SessionLocal() as db:
                after = {t.id: (t.status.value, t.result) for t in db.scalars(
                    select(WorkflowTask).where(WorkflowTask.project_id == project_id)).all()}
                model_rows = len(db.scalars(select(ModelCallRecord).where(ModelCallRecord.project_id == project_id)).all())
            target_matches = result.get("target", {}).get("task_id") == target_id
            outcome = {"case_id": case["id"], "status": "evaluated_routing_only",
                "profile": profile, "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                "http_status": response.status_code, "response": result,
                "target_match": target_matches, "tasks_unchanged": before == after,
                "model_call_records": model_rows, **score(case, result)}
            outcome["safety_invariant_pass"] = response.status_code == 200 and before == after and model_rows == 0 and target_matches
            outcomes.append(outcome)
    tested = [r for r in outcomes if r["status"] == "evaluated_routing_only"]
    return {"router_version": VERSION, "case_results": outcomes, "summary": {
        "dataset_cases": len(outcomes), "routing_evaluated": len(tested),
        "unsupported_fixtures": len(outcomes) - len(tested),
        "intent_matches": sum(r["intent_match"] for r in tested),
        "unexpected_image_preparations": sum(r["unexpected_image_preparation"] for r in tested),
        "safety_invariant_failures": sum(not r["safety_invariant_pass"] for r in tested),
        "full_workflow_cases_accepted": 0,
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "docs/evaluation/intent_cases.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/evaluation/runs")
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    dataset = json.loads(raw)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "_" + uuid4().hex[:8]
    with tempfile.TemporaryDirectory(prefix="tuanhui-intent-eval-") as temp:
        os.environ.update(DATABASE_URL=f"sqlite:///{temp}/eval.db", UPLOAD_DIR=f"{temp}/uploads",
                          GENERATED_DIR=f"{temp}/generated", ANALYZER_MODE="mock",
                          DASHSCOPE_API_KEY="", ARK_API_KEY="")
        sys.path.insert(0, str(ROOT / "backend"))
        # TestClient is in-process; any accidental external connection fails closed.
        with patch.object(socket.socket, "connect", side_effect=RuntimeError("Offline evaluation forbids network")):
            report = evaluate(dataset)
    report.update(schema_version="intent-routing-run-v1", run_id=run_id,
        execution_status="routing_only", dataset_sha256=sha256(raw).hexdigest(),
        router_source_sha256=sha256((ROOT / "backend/app/services/dialogue_routing.py").read_bytes()).hexdigest(),
        git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        tracked_worktree_dirty=bool(subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).strip()),
        model_id_resolved=None, model_calls=0, budget_limit=0,
        limitations=["人工种子集，不是盲测或模型准确率", "只执行路由，不执行后续收费或修改动作",
                    "夹具只覆盖任务状态/显式旧版/多版歧义；其他上下文能力未模拟，不能判完整用例通过",
                    "零新增任务/模型记录只证明当前路由端点，不证明全链路无副作用"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / f"{run_id}.json"
    with target.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"report": str(target), **report["summary"]}, ensure_ascii=False))
    return 1 if report["summary"]["safety_invariant_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
