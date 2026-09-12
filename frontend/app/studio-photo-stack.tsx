"use client";

import Image from "next/image";
import { ReactNode, useEffect, useId, useRef, useState } from "react";

export function StudioPhotoStack({ photos, children, onAdd, disabled }: {
  photos: { id: string; src: string }[]; children: ReactNode; onAdd: () => void; disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const expanded = open && photos.length > 0;
  useEffect(() => {
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, []);
  return <div ref={root} className="studioPhotoStack"
    onPointerEnter={event => { if (event.pointerType === "mouse") setOpen(true); }}
    onPointerLeave={event => { if (event.pointerType === "mouse" && !root.current?.querySelector("dialog[open]")) setOpen(false); }}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
    onKeyDown={event => { if (event.key === "Escape" && !root.current?.querySelector("dialog[open]")) { setOpen(false); trigger.current?.focus(); } }}>
    <button ref={trigger} type="button" className={`studioUploadCard ${photos.length ? "hasPhotos" : ""}`}
      aria-label={photos.length ? `查看 ${photos.length} 张照片` : "添加照片"} aria-expanded={expanded} aria-controls={panelId}
      disabled={disabled} onClick={() => { if (photos.length) setOpen(value => !value); else onAdd(); }}>
      {photos.slice(0, 3).map((photo, index) => <span className="studioStackImage" key={photo.id} style={{ transform: `translate(${index * 4}px, ${-index * 4}px) rotate(${index * 5}deg)`, zIndex: 3 - index }}><Image src={photo.src} alt="" fill unoptimized sizes="72px" /></span>)}
      {photos.length ? <small className="studioPhotoCount">{photos.length} 张</small> : <><span aria-hidden="true">＋</span><small>加照片</small></>}
    </button>
    <div id={panelId} className="studioPhotoPopover" hidden={!expanded} role="region" aria-label="本次照片">
      <header><span>{photos.length} 张照片</span><button type="button" disabled={disabled} onClick={onAdd}>＋ 添加</button><button type="button" aria-label="收起照片" onClick={() => { setOpen(false); trigger.current?.focus(); }}>×</button></header>
      <div className="studioPhotoGrid" inert={disabled}>{children}</div>
    </div>
  </div>;
}
