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
    texture = ImageOps.contain(background.convert("RGB"), canvas.size, Image.Resampling.LANCZOS)
    layer = canvas.copy()
    layer.paste(texture, ((4000 - texture.width) // 2, (600 - texture.height) // 2))
    illustration = plan.get("render_mode") == "illustration"
    canvas = Image.blend(canvas, layer, 1 if illustration else .16)
    draw = ImageDraw.Draw(canvas)
    draw.line((40, 30, 3960, 30), fill=accent, width=3)
    draw.line((40, 570, 3960, 570), fill=accent, width=3)
    copy = plan["copy"]
    fitted_text(draw, copy["store_name"], (60, 90, 680, 150), font_factory, ink, 76)
    fitted_text(draw, copy["headline"], (60, 270, 680, 130), font_factory, ink, 52)
    fitted_text(draw, copy["subheadline"], (60, 435, 680, 100), font_factory, accent, 28)
    dishes = [] if illustration else eligible_dishes(assets)[:3]
    # Reserve the middle three windows for the same real-material visual language.
    # One dish spans the visual center without inventing extra dishes to fill slots.
    widths = {1: 2200, 2: 1020, 3: 680}
    width = widths.get(len(dishes), 680)
    for index, asset in enumerate(dishes):
        center = 800 + (index + .5) * 2400 / len(dishes)
        with Image.open(asset.storage_path) as source:
            photo = ImageOps.exif_transpose(source).convert("RGBA")
            photo = ImageOps.contain(photo, (width, 440), Image.Resampling.LANCZOS)
        px, py = round(center - photo.width / 2), round(300 - photo.height / 2)
        draw.rounded_rectangle((px-9, py-9, px+photo.width+9, py+photo.height+9), radius=20, fill=accent)
        canvas.paste(photo, (px, py), photo)
    price = copy.get("price", "")
    if price in {"价格不展示", "待确认"}:
        price = copy["store_name"]
    fitted_text(draw, price, (3260, 135, 680, 170), font_factory, ink, 80)
    fitted_text(draw, copy["headline"], (3260, 330, 680, 110), font_factory, ink, 38)
    fitted_text(draw, copy["subheadline"], (3260, 460, 680, 80), font_factory, accent, 24)
    if illustration:
        for index in range(5):
            draw.rectangle((index * 800 + 20, 535, index * 800 + 245, 580), fill=base)
            fitted_text(draw, "AI示意 · 非实拍", (index * 800 + 28, 540, 210, 32), font_factory, ink, 24)
    return canvas


def save_manifest(output_dir: Path, plan, assets):
    manifest = {
        "template": "continuous-food-master-v1", "canvas": [4000, 600],
        "slice_boxes": [[i*800, 0, (i+1)*800, 600] for i in range(5)],
        "style": plan["style"], "copy": plan["copy"],
        "asset_ids": [a.id for a in eligible_dishes(assets)[:3]],
        "asset_policy": "product + dish/signature_dish only; storefront/menu excluded",
        "photo_mode": "original-contained; no automatic cutout or invented dishes",
    }
    (output_dir / "design-spec.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
