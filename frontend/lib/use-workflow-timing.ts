"use client";
import { useEffect, useState } from "react";
import { apiRequest } from "./api-client";
type Span = { task_id: string; stage: string; state: string; started_at: string; duration_ms: number | null; estimate?: { sample_count: number; range_ms: [number, number] | null } };
type Activity = { server_time: string; current: Span | null; spans: Span[] };
// Server timestamps survive refresh. Polling never starts a paid operation.
export function useWorkflowTiming(path: string | null, active: boolean) {
  const [data, setData] = useState<(Activity & { path: string; offset: number }) | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!path) return;
    let stopped = false;
    let pollTimer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await apiRequest<Activity>(path!);
        if (stopped) return;
        setData({ ...next, path: path!, offset: Date.parse(next.server_time) - Date.now() });
        if (active || next.current?.state === "running") pollTimer = setTimeout(poll, 1500);
      } catch {
        if (!stopped && active) pollTimer = setTimeout(poll, 3000);
      }
    }
    void poll();
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { stopped = true; clearTimeout(pollTimer); clearInterval(tick); };
  }, [path, active]);
  if (!data || data.path !== path || !data.current) return null;
  const span = data.current;
  const elapsed = span.state === "running" ? Math.max(0, now + data.offset - Date.parse(span.started_at)) : span.duration_ms;
  return { ...span, seconds: elapsed === null ? null : Math.floor(elapsed / 1000) };
}
