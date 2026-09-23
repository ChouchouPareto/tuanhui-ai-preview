import test from "node:test";
import assert from "node:assert/strict";
import {mayPrepare, dialogueTarget} from "../lib/dialogue-routing.ts";

test("only a typed preparation decision can enter generation consent", () => {
  const route={schema_version:"dialogue-safety-v1",intent:"new_creation",action:"prepare",can_prepare:true};
  assert.equal(mayPrepare(route),true);
  for (const change of [{intent:"report_issue"},{intent:"question"},{intent:"unclear"},{action:"answer"},{can_prepare:false},{schema_version:"unknown"}]) {
    assert.equal(mayPrepare({...route,...change}),false);
  }
  assert.equal(mayPrepare(null),false);
  assert.equal(mayPrepare({}),false);
});

test("explicit history target is retained and compose clears old IDs", () => {
  assert.deepEqual(dialogueTarget("p","?project=p&task=old"),{project_id:"p",creation_id:null,task_id:"old"});
  assert.deepEqual(dialogueTarget("p","?creation=c"),{project_id:"p",creation_id:"c",task_id:null});
  assert.deepEqual(dialogueTarget("p","?compose=1&task=old&creation=c"),{project_id:"p",creation_id:null,task_id:null});
});
