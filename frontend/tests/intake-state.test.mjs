import { test } from "node:test";
import assert from "node:assert/strict";
import { draftKey, canConfirmDraft } from "../lib/intake-state.ts";
const reviewed = { text: "店名：山城，主推：清蒸鱼", assetIds: ["a","b"], style: "brand", provider: "qwen" };
test("unchanged reviewed input is eligible; cosmetic asset order is irrelevant", () => {
  assert.equal(draftKey(reviewed), draftKey({...reviewed,assetIds:["b","a"]}));
  assert.ok(canConfirmDraft(reviewed,reviewed,true));
});
for (const [name, patch] of [["text",{text:"改成火锅"}],["assets",{assetIds:["a"]}],["model",{provider:"doubao"}],["style",{style:"street"}],["upload",{pending:true}],["reply",{replyField:"hero_item"}]]) {
  test(name + " changes invalidate old confirmation", () => assert.equal(canConfirmDraft({...reviewed,...patch},reviewed,true),false));
}
test("incomplete input never confirms", () => assert.equal(canConfirmDraft(reviewed,reviewed,false),false));
