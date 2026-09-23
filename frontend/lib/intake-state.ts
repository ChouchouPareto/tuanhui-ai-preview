export type DraftInput = { outputType?: string; deliveryTypes?: string[]; text: string; assetIds: string[]; style: string; provider: string; pending?: boolean; replyField?: string | null; useAi?: boolean; chat?: boolean; localOnly?: boolean };
export function draftKey(input: DraftInput): string {
  return JSON.stringify([input.text.trim(), [...new Set(input.assetIds)].sort(), input.style, input.provider, Boolean(input.pending), input.replyField ?? null, input.outputType || "five_panel", input.outputType === "full_plan" ? input.deliveryTypes || ["voucher_main", "five_panel", "logo"] : null]);
}
export function canConfirmDraft(current: DraftInput, reviewed: DraftInput, ready: boolean): boolean {
  return ready && !current.pending && !current.replyField && draftKey(current) === draftKey(reviewed);
}
