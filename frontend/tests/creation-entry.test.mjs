import test from "node:test";
import assert from "node:assert/strict";
import { originalCreationUrl, entryPath } from "../lib/creation-entry.ts";
import { continuationPath } from "../lib/generation-binding.ts";

test("three entries resolve to original product pages", () => {
  assert.equal(entryPath("oneclick"), "/");
  assert.equal(entryPath("professional"), "/professional");
  assert.equal(entryPath("fullplan"), "/full-plan");
  assert.equal(continuationPath("professional", "five_panel"), "/professional");
});
test("compatibility URL preserves saved work but never actions or model authority", () => {
  assert.equal(originalCreationUrl({entry:"professional", project:"p", run:"r", task:"t", approved_text_calls:"2", execute:"1"}), "/professional?project=p&task=t&run=r");
  assert.equal(originalCreationUrl({entry:"fullplan", project:"p", creation:"c"}), "/full-plan?project=p&creation=c");
  assert.equal(originalCreationUrl({entry:"https://example.com", project:["p", "q"]}), "/");
});
