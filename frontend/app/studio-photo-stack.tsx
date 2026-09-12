"use client";

import Image from "next/image";
import { Children, CSSProperties, Fragment, isValidElement, ReactNode, useEffect, useId, useRef, useState } from "react";

function flattenPhotos(children: ReactNode): ReactNode[] {
  return Children.toArray(children).flatMap(child => isValidElement<{children: ReactNode}>(child) && child.type === Fragment ? flattenPhotos(child.props.children) : [child]);
}

export function StudioPhotoStack({ photos, children, onAdd, disabled }: {
  photos: { id: string; src: string }[]; children: ReactNode; onAdd: () => void; disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(0);
  const cards = flattenPhotos(children);
  const currentPage = Math.min(page, Math.max(0, Math.ceil(cards.length / 5) - 1));
  const visibleCards = cards.slice(currentPage * 5, currentPage * 5 + 5);
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
      <span className="studioGlassBack" aria-hidden="true" /><span className="studioGlassFront" aria-hidden="true" />
      {photos.slice(0, 3).map((photo, index) => <span className="studioStackImage" key={photo.id} style={{ transform: `translate(${index * 4}px, ${-index * 4}px) rotate(${index * 5}deg)`, zIndex: 3 - index }}><Image src={photo.src} alt="" fill unoptimized sizes="72px" /></span>)}
      {photos.length ? <small className="studioPhotoCount">{photos.length} 张</small> : <><span aria-hidden="true">＋</span><small>加照片</small></>}
    </button>
    <div id={panelId} className="studioPhotoPopover" hidden={!expanded} role="region" aria-label="本次照片">
      <header><span>{photos.length} 张照片</span><button type="button" disabled={disabled} onClick={onAdd}>＋ 添加</button><button type="button" aria-label="收起照片" onClick={() => { setOpen(false); trigger.current?.focus(); }}>×</button></header>
      <div className="studioPhotoGrid studioPhotoFan" inert={disabled}>{visibleCards.map((card, index) => {
        const offset = index - (visibleCards.length - 1) / 2;
        return <div className="studioFanCard" key={currentPage * 5 + index} style={{"--fan-x": `${offset * 46}px`, "--fan-y": `${Math.abs(offset) * 9}px`, "--fan-angle": `${offset * 9}deg`, "--fan-delay": `${index * 35}ms`} as CSSProperties}>{card}</div>;
      })}</div>
      {cards.length > 5 && <footer className="studioFanPages"><button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一组</button><span>{currentPage + 1} / {Math.ceil(cards.length / 5)}</span><button type="button" disabled={(currentPage + 1) * 5 >= cards.length} onClick={() => setPage(currentPage + 1)}>下一组</button></footer>}
    </div>
  </div>;
}
