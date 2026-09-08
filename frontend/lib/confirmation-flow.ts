/** Save and validate before the only billable operation. No automatic retries. */
export async function runConfirmationFlow<T extends { status: string; snapshot: { ready: boolean } | null }>(
  steps: { read: () => Promise<T>; save: () => Promise<T>; confirm: (saved: T) => Promise<T> },
): Promise<T> {
  const current = await steps.read();
  if (current.status === "CONFIRMED") return current;
  const saved = await steps.save();
  if (!saved.snapshot?.ready) return saved;
  return steps.confirm(saved);
}
