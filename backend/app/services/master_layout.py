"""Versioned, deterministic five-slice master composition (no model-drawn facts)."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


PALETTES = {
    "appetite": ("#8a231e", "#fff2d6", "#f6c76b"),
    "brand": ("#173d35", "#fff4dc", "#d7bb7b"),
    "street": ("#493027", "#fff1da", "#eab475"),
    "minimal": ("#ecf1e7", "#213e31", "#50765b"),
}


def eligible_dishes(assets):
    # Both the upload category and the explicit semantic role must permit rendering.
    # A mislabeled storefront must never pass just because is_hero is set.
    return [a for a in assets if a.asset_type == "product"
            and a.semantic_role in {"dish", "signature_dish"}]


def fitted_text(draw, text, box, font_factory, color, size=60):
    """Wrap by measured width; fail instead of silently truncating business facts."""
    x, y, width, height = box
    text = str(text or "").strip()
    if not text:
        return
    for point_size in range(size, 17, -2):
        font = font_factory(point_size)
        lines, line = [], ""
        for character in text:
            if character == "\n":
                lines.append(line)
                line = ""
            elif line and draw.textlength(line + character, font=font) > width:
                lines.append(line)
                line = character
            else:
                line += character
        lines.append(line)
        spacing = round(point_size * 1.4)
        bounds = [draw.textbbox((0,0), value, font=font) for value in lines]
        if all(b[2]-b[0] <= width for b in bounds) and (len(lines)-1)*spacing + max(b[3]-b[1] for b in bounds) <= height:
            for index, (value, bound) in enumerate(zip(lines, bounds)):
                # Align actual glyph pixels, not font baseline (prevents clipping/overlap).
                draw.text((x-bound[0], y + index * spacing-bound[1]), value, font=font, fill=color)
            return {"text":text,"box":list(box),"font_size":point_size,"lines":lines}
    raise ValueError("文案超出母版容量，请缩短文案后重新确认；未截断文字")


def compose_master(background, plan, assets, font_factory):
    """One canvas; slice boundaries constrain text, not five independent scenes."""
    if plan.get("template_version") == "region-master-v3":
        return compose_regions(background, plan, assets, font_factory)
    base, ink, accent = PALETTES.get(plan.get("style", {}).get("key"), PALETTES["appetite"])
    canvas = Image.new("RGB", (4000, 600), base)
    # The model only supplies decorative texture, so padding is safer than cropping.
    texture = ImageOps.fit(background.convert("RGB"), canvas.size, Image.Resampling.LANCZOS)
    layer = canvas.copy()
    layer.paste(texture, ((4000 - texture.width) // 2, (600 - texture.height) // 2))
    illustration = plan.get("render_mode") == "illustration"
    canvas = Image.blend(canvas, layer, 1 if illustration else .16)
    draw = ImageDraw.Draw(canvas)
    draw.line((40, 30, 3960, 30), fill=accent, width=3)
    draw.line((40, 570, 3960, 570), fill=accent, width=3)
    dishes = [] if illustration else eligible_dishes(assets)[:3]
    # Reuse approved photographs across five complete frames instead of slicing
    # one plate into disconnected fragments. Never invent additional menu items.
    for index in range(5 if dishes else 0):
        asset = dishes[index % len(dishes)]
        center = index * 800 + 400
        with Image.open(asset.storage_path) as source:
            photo = ImageOps.exif_transpose(source).convert("RGBA")
            photo = ImageOps.contain(photo, (700, 330), Image.Resampling.LANCZOS)
        px, py = round(center - photo.width / 2), round(205 - photo.height / 2)
        draw.rounded_rectangle((px-9, py-9, px+photo.width+9, py+photo.height+9), radius=20, fill=accent)
        canvas.paste(photo, (px, py), photo)
    # Render all five planned content regions, not just the two ends.
    # A dark local gradient gives readable text regardless of the model palette.
    overlay = Image.new("RGBA", canvas.size)
    shade = ImageDraw.Draw(overlay)
    for y in range(350, 600):
        shade.line((0, y, 4000, y), fill=(12, 15, 18, min(225, int((y - 350) * .8 + 30))))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    for index, frame in enumerate(plan["frames"]):
        x = index * 800 + 44
        fitted_text(draw, frame["headline"], (x, 365, 712, 125), font_factory, "#ffffff", 52)
        fitted_text(draw, frame.get("support", ""), (x, 490, 712, 42), font_factory, "#f2eadc", 26)
    # First frame carries a visible brand lockup, not a tiny floating label.
    if plan["copy"].get("store_name"):
        draw.rounded_rectangle((32, 42, 768, 185), radius=18, fill=base)
        fitted_text(draw, plan["copy"]["store_name"], (54, 54, 692, 115), font_factory, ink, 66)
    if illustration:
        for index in range(5):
            draw.rectangle((index * 800 + 20, 535, index * 800 + 245, 580), fill=base)
            fitted_text(draw, "AI示意 · 非实拍", (index * 800 + 28, 540, 210, 32), font_factory, ink, 24)
    return canvas


def compose_regions(background, plan, assets, font_factory):
    width, height = map(int, plan["canvas"]["recommended_size"].split("x"))
    base, ink, accent = PALETTES.get(plan["style"]["key"], PALETTES["appetite"])
    texture = ImageOps.fit(background.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
    real = plan.get("render_mode") != "illustration"
    canvas = Image.blend(Image.new("RGB", (width, height), base), texture, .16) if real else texture
    dishes = eligible_dishes(assets)
    visual_regions = [r for r in plan["layout"]["regions"] if r["role"] == "visual"]
    if real:
        for region, asset in zip(visual_regions, dishes):
            x, y, w, h = region["box"]
            with Image.open(asset.storage_path) as source:
                photo = ImageOps.contain(ImageOps.exif_transpose(source).convert("RGBA"),
                                         (round(w*width), round(h*height)), Image.Resampling.LANCZOS)
            canvas.paste(photo, (round(x*width+(w*width-photo.width)/2),
                                round(y*height+(h*height-photo.height)/2)), photo)
    area = next(r["box"] for r in plan["layout"]["regions"] if r["role"] == "copy")
    x, y, w, h = area[0]*width, area[1]*height, area[2]*width, area[3]*height
    # A soft local veil improves readability without a fixed red badge/black footer.
    # Its color follows the selected palette; never alters the whole image.
    from PIL import ImageFilter, ImageColor
    veil = Image.new("RGBA", canvas.size)
    mask = Image.new("L", canvas.size)
    ImageDraw.Draw(mask).rectangle((x-12,y-12,x+w+12,y+h+12),fill=160)
    mask = mask.filter(ImageFilter.GaussianBlur(18))
    veil.paste(ImageColor.getrgb(base)+(255,), (0,0,width,height))
    veil.putalpha(mask)
    canvas = Image.alpha_composite(canvas.convert("RGBA"),veil).convert("RGB")
    draw = ImageDraw.Draw(canvas)
    entries, seen = [], set()
    for key in ("store_name", "headline", "subheadline", "price"):
        value = str(plan["copy"].get(key) or "").strip()
        if value and value not in seen:
            entries.append((key,value)); seen.add(value)
    # Only actual information consumes space; no mandatory text per export slice.
    weights = {"store_name": 1.2, "headline": 2, "subheadline": 1, "price": 1.3}
    total = sum(weights[key] for key, _ in entries)
    for key, value in entries:
        slot = h * weights[key] / total
        fitted_text(draw, value, (x, y, w, slot-8), font_factory,
                    accent if key == "price" else ink, 74 if key == "headline" else 50)
        y += slot
    return canvas


def add_export_watermark(canvas, slice_count, font_factory):
    marked = canvas.copy()
    draw = ImageDraw.Draw(marked)
    width, height = marked.size
    for i in range(slice_count):
        x = i * (width // slice_count) + 20
        # Export-only overlay; the clean master is never mutated.
        draw.rounded_rectangle((x, height-48, x+232, height-12), radius=5, fill="#333333")
        fitted_text(draw, "AI示意 · 非实拍", (x+8,height-46,216,32), font_factory, "#ffffff", 22)
    return marked


def save_manifest(output_dir: Path, plan, assets):
    manifest = {
        "template": plan.get("template_version"), "canvas": list(map(int, plan["canvas"]["recommended_size"].split("x"))),
        "slice_boxes": [[i*800, 0, (i+1)*800, 600] for i in range(plan["canvas"]["slice_count"])],
        "style": plan["style"], "copy": plan["copy"],
        "frames": plan["frames"], "creative_direction": plan.get("creative_direction"),
        "render_mode": plan.get("render_mode", "real_assets"),
        "layout": plan.get("layout"), "watermark": "export-layer-only" if plan.get("layout") else "legacy",
        "asset_ids": [a.id for a in eligible_dishes(assets)[:sum(r["role"] == "visual" for r in plan["layout"]["regions"]) if plan.get("layout") else 3]],
        "asset_policy": "product + dish/signature_dish only; storefront/menu excluded",
        "photo_mode": "original-contained; no automatic cutout or invented dishes",
    }
    (output_dir / "design-spec.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
