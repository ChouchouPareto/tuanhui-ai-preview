import test from "node:test";
import assert from "node:assert/strict";
import { generationBinding, continuationPath } from "../lib/generation-binding.ts";

test("generation binds exact reviewed version and replays identical submissions", () => {
  const plan = { id: "a".repeat(36), plan_hash: "b".repeat(64) };
  const request = generationBinding(plan, "doubao");
  assert.deepEqual(request, generationBinding(plan, "doubao"));
  assert.equal(request.plan_id, plan.id);
  assert.equal(request.plan_hash, plan.plan_hash);
  assert.equal(request.allow_fallback, false);
  assert.ok(request.request_id.length <= 120);
  assert.match(request.request_id, /^[A-Za-z0-9_-]{1,128}$/);
  assert.notEqual(request.request_id, generationBinding({ ...plan, plan_hash: "c".repeat(64) }, "doubao").request_id);
});
test("missing hash must not fall back to latest", () => {
  assert.throws(() => generationBinding({ id: "plan" }, "qwen"));
});
test("full-plan single output stays in full-plan, including historical snapshots", () => {
  assert.equal(continuationPath("fullplan", undefined, "logo"), "/full-plan");
  assert.equal(continuationPath(undefined, "full_plan", "store_decoration"), "/full-plan");
  assert.equal(continuationPath("oneclick", "logo", "logo"), "/");
});
