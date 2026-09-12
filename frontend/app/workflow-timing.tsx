import { useWorkflowTiming } from "../lib/use-workflow-timing";
export function WorkflowTiming({ path, active }: { path: string | null; active: boolean }) {
  const timing = useWorkflowTiming(path, active);
  if (!timing) return active ? <p className="workflowTiming">正在连接服务，计时信息加载中…</p> : null;
  const label = ({ understanding: "理解需求", queue: "排队", generation: "生成全流程", image_model: "生成画面", layout_export: "排版与导出" } as Record<string, string>)[timing.stage] || "处理中";
  const range = timing.estimate?.range_ms;
  const running = timing.state === "running";
  const duration = timing.seconds === null ? "耗时暂不可用" : `${running ? "已用" : "用时"} ${timing.seconds} 秒`;
  return <p className="workflowTiming">{label} · {duration}{!running && timing.state !== "completed" ? " · 已结束，未自动重试" : ""}
    {running && <span> · {range ? (timing.seconds ?? 0) * 1000 > range[1] ? "比近期通常用时更长，仍在等待服务返回" : `同类任务通常需 ${Math.ceil(range[0]/1000)}–${Math.ceil(range[1]/1000)} 秒（非倒计时）` : "样本积累中，暂不估算完成时间"}</span>}
  </p>;
}
