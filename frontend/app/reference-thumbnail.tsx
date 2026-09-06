"use client";

import Image from "next/image";
import { ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function ReferenceCategory({ label, count, onAdd, children }: { label: string; count: number; onAdd: () => void; children: ReactNode }) {
  return <section className="referenceCategory" aria-label={`${label}素材`}>
    <header><span>{label}</span><small aria-label={`${label}素材 ${count} 张`}>{count}</small></header>
    <div className={`referenceCategoryItems ${count ? "hasAssets" : ""}`}>
      {children}
      <button className="referenceCategoryAdd" type="button" aria-label={`添加${label}素材`} onClick={onAdd}><span aria-hidden="true" style={{ fontSize: 28 }}>+</span>{count > 0 && <small>继续添加</small>}</button>
    </div>
  </section>;
}

export function ReferenceThumbnail({ src, name, reading = false, onRemove }: {
  src: string; name: string; reading?: boolean; onRemove?: () => void;
}) {
  const [hover, setHover] = useState<{ left: number; top: number } | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dismiss = () => setHover(null);
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") dismiss(); };
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    window.addEventListener("blur", dismiss);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
      window.removeEventListener("blur", dismiss);
      window.removeEventListener("keydown", escape);
    };
  }, []);
  return <article className="referenceThumbnail">
    <button type="button" className="referenceThumbnailImage" aria-label={`预览 ${name}`} disabled={reading}
      onPointerEnter={(event) => {
        if (event.pointerType !== "mouse" || reading || !window.matchMedia("(hover: hover)").matches) return;
        const rect = event.currentTarget.getBoundingClientRect();
        // Place the non-interactive preview beside the source, never over its remove button.
        const left = rect.right + 12 + 280 <= window.innerWidth ? rect.right + 12 : rect.left - 292;
        setHover({ left: Math.max(8, left), top: Math.max(8, Math.min(rect.top, window.innerHeight - 308)) });
      }} onPointerLeave={() => setHover(null)} onPointerDown={() => setHover(null)}
      onClick={() => { setHover(null); dialogRef.current?.showModal(); }}>
      <Image src={src} alt={name} fill unoptimized sizes="160px" />
      {reading && <span className="assetReadingState" role="status"><i aria-hidden="true" /><small>读取中</small></span>}
    </button>
    {onRemove && <button type="button" className="referenceThumbnailRemove" aria-label={`移除 ${name}`}
      onPointerEnter={() => setHover(null)} onFocus={() => setHover(null)}
      onClick={() => { setHover(null); dialogRef.current?.close(); onRemove(); }}>×</button>}
    {hover && createPortal(<div className="referenceHoverPreview" style={hover} aria-hidden="true">
      <Image src={src} alt="" fill unoptimized sizes="280px" /><small>{name}</small>
    </div>, document.body)}
    <dialog ref={dialogRef} className="referenceImageDialog" aria-label={`图片预览：${name}`}
      onCancel={(event) => { event.stopPropagation(); setHover(null); }}
      onClick={(event) => { if (event.target === event.currentTarget) dialogRef.current?.close(); }}>
      <div className="referenceImageContent">
        <header><span>{name}</span><button type="button" autoFocus aria-label="关闭图片预览" onClick={() => dialogRef.current?.close()}>×</button></header>
        <div className="referenceFullImage"><Image src={src} alt={name} fill unoptimized sizes="90vw" /></div>
        {onRemove && <button type="button" className="referencePreviewRemove" onClick={() => { dialogRef.current?.close(); onRemove(); }}>移除这张素材</button>}
      </div>
    </dialog>
  </article>;
}
