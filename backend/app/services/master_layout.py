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
        if len(lines) * spacing <= height:
            for index, value in enumerate(lines):
                draw.text((x, y + index * spacing), value, font=font, fill=color)
            return
    raise ValueError("文案超出母版容量，请缩短文案后重新确认；未截断文字")


def compose_master(background, plan, assets, font_factory):
    """One canvas; slice boundaries constrain text, not five independent scenes."""
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


def save_manifest(output_dir: Path, plan, assets):
    manifest = {
        "template": plan.get("template_version"), "canvas": [4000, 600],
        "slice_boxes": [[i*800, 0, (i+1)*800, 600] for i in range(5)],
        "style": plan["style"], "copy": plan["copy"],
        "frames": plan["frames"], "creative_direction": plan.get("creative_direction"),
        "render_mode": plan.get("render_mode", "real_assets"),
        "asset_ids": [a.id for a in eligible_dishes(assets)[:3]],
        "asset_policy": "product + dish/signature_dish only; storefront/menu excluded",
        "photo_mode": "original-contained; no automatic cutout or invented dishes",
    }
    (output_dir / "design-spec.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
