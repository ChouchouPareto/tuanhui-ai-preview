"""Bounded, opt-in live acceptance probe; never retries paid operations.

Uses the existing local API. Saves receipts only under a fresh audit directory;
does not patch runtime code, alter old projects, or submit multi-image batches.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("entry", choices=["oneclick", "fullplan", "professional-preflight"])
    parser.add_argument("--execute-authorized", action="store_true")
    args = parser.parse_args()
    if not args.execute_authorized:
        parser.error("Explicit authorization flag is required; this probe may incur model fees")
    root = Path(__file__).resolve().parents[1]
    directory = root / "data" / "acceptance" / "20260920-three-entries" / args.entry
    directory.mkdir(parents=True, exist_ok=True)
    # A second invocation cannot create another billable run for the same entry.
    with (directory / "started.json").open("x", encoding="utf-8") as stream:
        json.dump({"entry": args.entry, "started_at": datetime.now(timezone.utc).isoformat(),
                   "max_understanding_calls": 1, "max_image_calls": 1,
                   "automatic_retries": 0}, stream)
    client = httpx.Client(base_url="http://127.0.0.1:8011/api/v1", timeout=110)
    sequence = 0

    def request(method, path, body=None, *, label="request", **kwargs):
        nonlocal sequence
        sequence += 1
        started = time.monotonic()
        receipt = {"method": method, "path": path, "body": body,
                   "started_at": datetime.now(timezone.utc).isoformat()}
        try:
            response = client.request(method, path, json=body, **kwargs)
            receipt.update(status=response.status_code, response=response.json())
        except Exception as exc:
            receipt["transport_error"] = type(exc).__name__
            raise
        finally:
            receipt["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            with (directory / f"{sequence:03d}-{label}.json").open("x", encoding="utf-8") as stream:
                json.dump(receipt, stream, ensure_ascii=False, indent=2)
            print(json.dumps({k: receipt.get(k) for k in ("path", "status", "elapsed_ms", "transport_error")}, ensure_ascii=False), flush=True)
        return response

    def ok(response):
        response.raise_for_status()
        return response.json()

    project = ok(request("POST", "/projects", {"name": f"验收专用-{args.entry}-20260920"}, label="project"))["project_id"]
    print("PROJECT " + project, flush=True)
    if args.entry == "professional-preflight":
        # Exactly the ordinary no-asset professional analysis request. A rejection
        # is evidence, not permission to seed the database or bypass the UI rules.
        response = request("POST", f"/projects/{project}/analysis-runs", {"use_ai": True}, label="analysis-preflight")
        print("PROFESSIONAL_PREFLIGHT " + response.text, flush=True)
        request("GET", f"/projects/{project}/usage", label="usage")
        return

    output = "five_panel" if args.entry == "oneclick" else "full_plan"
    text = "店名：验收面馆；主推：面食；不展示价格；清爽简约。请制作" + ("五连图" if args.entry == "oneclick" else "全案")
    route = ok(request("POST", "/dialogue/route", {"project_id": project, "text": text, "new_session": True}, label="route"))
    if not route.get("can_prepare"):
        raise RuntimeError("Route did not authorize preparation; probe stopped")
    base = f"/projects/{project}/creations"
    creation = ok(request("POST", base, {}, label="creation"))["creation_id"]
    base += "/" + creation
    payload = {"expected_revision": 0, "text": text, "asset_ids": [],
               "style": "minimal", "provider": "qwen", "output_type": output,
               "input_mode": "chat", "allow_illustration": True,
               "use_ai": True, "accepted_understanding_policy": "text-understanding-paid-v1"}
    if args.entry == "fullplan":
        payload["delivery_types"] = ["store_decoration"]
    response = request("POST", base + "/intake-runs", payload,
                       headers={"Idempotency-Key": str(uuid4())}, label="intake")
    if response.status_code != 200:
        request("GET", f"/projects/{project}/usage", label="usage")
        print("STOPPED_INTAKE " + response.text, flush=True)
        return
    review = response.json()
    snapshot = review["snapshot"]
    print("INTAKE " + json.dumps({"ready": snapshot["ready"], "facts": snapshot["facts"],
          "gaps": snapshot["gaps"], "output_type": snapshot["output_type"],
          "delivery_types": snapshot["delivery_types"], "creative_draft": snapshot.get("creative_draft")}, ensure_ascii=False), flush=True)
    if not snapshot["ready"] or len(snapshot["delivery_types"]) != 1 or snapshot["output_type"] != output:
        request("GET", f"/projects/{project}/usage", label="usage")
        print("STOPPED_UNREADY_OR_SCOPE_CHANGED", flush=True)
        return
    queued = ok(request("POST", base + "/confirm", {"expected_revision": review["revision"],
        "snapshot_hash": review["snapshot_hash"], "accepted_budget_policy": "local-paid-generation-v1",
        "materials_confirmed": True, "approved_image_calls": 1},
        headers={"Idempotency-Key": str(uuid4())}, label="confirm"))
    task_id = queued["task_id"]
    print("TASK " + task_id, flush=True)
    deadline = time.monotonic() + 420
    previous = None
    while time.monotonic() < deadline:
        task = ok(request("GET", "/tasks/" + task_id, label="task"))
        status = (task["status"], task["progress"])
        if status != previous:
            print("STATE " + json.dumps(task, ensure_ascii=False), flush=True)
            previous = status
        if task["status"] not in {"PENDING", "RUNNING"}:
            break
        time.sleep(5)
    request("GET", base + "/review", label="restored-review")
    request("GET", f"/projects/{project}/tasks/{task_id}/activity", label="activity")
    request("GET", f"/projects/{project}/usage", label="usage")
    request("POST", "/dialogue/route", {"project_id": project, "task_id": task_id,
        "creation_id": creation, "text": "这张图文字重叠了，先检查原因，不要重新生成"}, label="complaint-route")
    request("GET", f"/projects/{project}/usage", label="usage-after-complaint")
    print("RECEIPTS " + str(directory), flush=True)


if __name__ == "__main__":
    main()
