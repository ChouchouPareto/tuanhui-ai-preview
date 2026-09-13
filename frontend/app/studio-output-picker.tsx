"use client";

import { useEffect, useRef } from "react";
import { OUTPUT_NAMES } from "../lib/output-options";

type Props = {
  fullPlan: boolean; outputType: string; onOutput: (value: string) => void;
  deliveryTypes: string[]; onDeliveries: (value: string[]) => void;
  style: string; styles: string[]; onStyle: (value: string) => void;
  model: string; models: string[]; onModel: (value: string) => void;
  open: boolean; onOpen: (open: boolean) => void; disabled: boolean;
  onStore: () => void; onPhoto: () => void; onLibrary: () => void;
};

/** Shared input-toolbar controls; batch selection belongs only to /full-plan. */
export function StudioOutputPicker(p: Props) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!p.open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) p.onOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { p.onOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, [p.open, p.onOpen]);
  const title = p.fullPlan ? "全案作品" : OUTPUT_NAMES[p.outputType] || "五连图";
  return <div ref={root} className="studioOutputPicker">
    <div className="studioOutputSummary">
      <button ref={trigger} type="button" className="studioOutputTrigger" disabled={p.disabled} aria-label={p.fullPlan ? "选择全案作品" : "选择图片类型"} aria-expanded={p.open} aria-controls="studio-output-options" onClick={() => p.onOpen(!p.open)}>
        <span className="studioOutputGlass" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
        <span>{title}</span>{p.fullPlan && <small>{p.deliveryTypes.length} 项</small>}
      </button>
      <span className="studioOutputDot" aria-hidden="true">·</span>
      <button type="button" className="studioStyleTrigger" disabled={p.disabled} onClick={() => p.onOpen(!p.open)}>{p.style === "智能匹配" ? "自动风格" : p.style}</button>
    </div>
    {p.open && <section id="studio-output-options" className="studioOutputPopover" aria-label={p.fullPlan ? "全案作品设置" : "图片类型与风格"}>
      <header><strong>{p.fullPlan ? "这次一起做" : "想做哪种图？"}</strong><button type="button" aria-label="收起图片设置" onClick={() => { p.onOpen(false); trigger.current?.focus(); }}>×</button></header>
      <div className="studioOutputChoices" role="group" aria-label={p.fullPlan ? "全案包含的作品" : "单项图片类型"}>
        {Object.entries(OUTPUT_NAMES).filter(([key]) => key !== "full_plan").map(([key, name]) => {
          const selected = p.fullPlan ? p.deliveryTypes.includes(key) : p.outputType === key;
          return <button key={key} type="button" aria-pressed={selected} disabled={p.disabled || (p.fullPlan && selected && p.deliveryTypes.length === 1)} onClick={() => {
            if (p.fullPlan) p.onDeliveries(selected ? p.deliveryTypes.filter(v => v !== key) : [...p.deliveryTypes, key]);
            else { p.onOutput(key); p.onOpen(false); trigger.current?.focus(); }
          }}><span>{name}</span>{selected && <span className="studioChoiceCheck" aria-hidden="true">✓</span>}</button>;
        })}
      </div>
      <div className="studioCompactSettings"><label>风格<select value={p.style} onChange={e => p.onStyle(e.target.value)}>{p.styles.map(v => <option key={v}>{v}</option>)}</select></label><label>模型<select value={p.model} onChange={e => p.onModel(e.target.value)}>{p.models.map(v => <option key={v}>{v}</option>)}</select></label></div>
      <div className="studioMaterialLinks"><button type="button" onClick={p.onStore}>门头参考</button><button type="button" onClick={p.onPhoto}>添加照片</button><button type="button" onClick={p.onLibrary}>素材库</button></div>
    </section>}
  </div>;
}
