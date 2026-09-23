/** No UI state or `latest` lookup may substitute the reviewed plan. */
export function generationBinding(plan: { id: string; plan_hash: string }, provider: string) {
  if (!plan.id || !/^[a-f0-9]{64}$/.test(plan.plan_hash || "")) {
    throw new Error("方案缺少有效版本信息，请重新打开并确认方案；尚未发起生成。");
  }
  return { provider, allow_fallback: false, plan_id: plan.id, plan_hash: plan.plan_hash,
    request_id: `pro_${plan.id}_${plan.plan_hash}_${provider}` };
}

export function continuationPath(entryMode?: string, snapshotType?: string, outputType?: string) {
  return entryMode === "fullplan" || snapshotType === "full_plan" || outputType === "full_plan" ? "/full-plan" : entryMode === "professional" ? "/professional" : "/";
}
