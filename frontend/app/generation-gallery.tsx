"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import { apiUrl } from "../lib/api-client";
import "./generation-gallery.css";

export function GenerationGallery({ projectId, taskId, longImage, slices = [] }: {
  projectId: string; taskId: string; longImage?: string; slices?: string[];
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const items = [
    ...(longImage ? [{ file: longImage, label: "完整五连图", long: true }] : []),
    ...slices.map((file, i) => ({ file, label: `第 ${i + 1} 张切片`, long: false })),
  ];
  const url = (file: string) => apiUrl(`/projects/${projectId}/generations/${taskId}/assets/${file}`);
  const current = items[selected];
  const move = (step: number) => { setSelected(i => (i + step + items.length) % items.length); setZoomed(false); };
  if (!items.length) return null;
  return <section className="generationGallery" aria-label="生成作品">
    <div className="generationGalleryGrid">{items.map((item, index) => <figure key={item.file} className={item.long ? "generationGalleryLong" : ""}>
      <button className="generationPreviewButton" type="button" aria-label={`预览${item.label}`} onClick={() => {
        setSelected(index); setZoomed(false); dialog.current?.showModal();
      }}>
        <Image src={url(item.file)} alt={item.label} width={item.long ? 4000 : 800} height={600} unoptimized />
      </button>
      <figcaption><span>{item.label}</span><a href={url(item.file)} download aria-label={`下载${item.label}`}>下载</a></figcaption>
    </figure>)}</div>
    <dialog ref={dialog} className="generationPreviewDialog" aria-label="作品预览" onClick={event => {
      if (event.target === event.currentTarget) dialog.current?.close();
    }} onKeyDown={event => {
      if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
      if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
    }}>
      <div className="generationPreviewPanel">
        <header><strong>{current?.label}</strong><div>
          <button type="button" onClick={() => setZoomed(!zoomed)}>{zoomed ? "适应窗口" : "放大查看"}</button>
          <a href={current && url(current.file)} download>下载</a>
          <button type="button" aria-label="关闭预览" onClick={() => dialog.current?.close()}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </div></header>
        <div className={`generationPreviewStage ${zoomed ? "isZoomed" : ""}`}>
          {current && <Image src={url(current.file)} alt={`${current.label}预览`} width={current.long ? 4000 : 800} height={600} unoptimized />}
        </div>
        <footer><button type="button" onClick={() => move(-1)} disabled={items.length < 2}>上一张</button>
          <span aria-live="polite">{selected + 1} / {items.length}</span>
          <button type="button" onClick={() => move(1)} disabled={items.length < 2}>下一张</button></footer>
      </div>
    </dialog>
  </section>;
}
