import { test } from "node:test";
import assert from "node:assert/strict";
import { runConfirmationFlow } from "../lib/confirmation-flow.ts";

test("save the edited revision before confirming its exact snapshot", async () => {
  const calls = [];
  const saved = { status: "READY_TO_CONFIRM", snapshot: { ready: true }, revision: 3 };
  const result = await runConfirmationFlow({
    read: async () => { calls.push("read"); return { status: "DRAFT" }; },
    save: async () => { calls.push("save"); return saved; },
    confirm: async value => { assert.equal(value, saved); calls.push("confirm"); return { ...value, status: "CONFIRMED" }; },
  });
  assert.deepEqual(calls, ["read", "save", "confirm"]);
  assert.equal(result.status, "CONFIRMED");
});
test("incomplete input is saved but never generates", async () => {
  const saved = { status: "NEEDS_INPUT", snapshot: { ready: false } };
  assert.equal(await runConfirmationFlow({
    read: async () => saved, save: async () => saved,
    confirm: async () => assert.fail("must not generate"),
  }), saved);
});
test("a failed save never generates", async () => {
  await assert.rejects(runConfirmationFlow({
    read: async () => ({ status: "DRAFT" }),
    save: async () => { throw new Error("save failed"); },
    confirm: async () => assert.fail("must not generate"),
  }), /save failed/);
});
test("recover lost confirmation response without resaving or generating", async () => {
  const current = { status: "CONFIRMED", task_id: "same-task" };
  assert.equal(await runConfirmationFlow({
    read: async () => current,
    save: async () => assert.fail("must not save again"),
    confirm: async () => assert.fail("must not generate again"),
  }), current);
});
test("confirmation failure is surfaced, not automatically retried", async () => {
  let count = 0;
  await assert.rejects(runConfirmationFlow({
    read: async () => ({ status: "DRAFT" }),
    save: async () => ({ status: "READY_TO_CONFIRM", snapshot: { ready: true } }),
    confirm: async () => { count++; throw new Error("lost response"); },
  }), /lost response/);
  assert.equal(count, 1);
});
