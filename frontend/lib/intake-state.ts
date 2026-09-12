export type DraftInput = { text: string; assetIds: string[]; style: string; provider: string; pending?: boolean; replyField?: string | null; useAi?: boolean; chat?: boolean };
export function draftKey(input: DraftInput): string {
  return JSON.stringify([input.text.trim(), [...new Set(input.assetIds)].sort(), input.style, input.provider, Boolean(input.pending), input.replyField ?? null]);
}
export function canConfirmDraft(current: DraftInput, reviewed: DraftInput, ready: boolean): boolean {
  return ready && !current.pending && !current.replyField && draftKey(current) === draftKey(reviewed);
}
