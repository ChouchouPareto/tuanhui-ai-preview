"""Deterministic scene validation/rendering shared by generation and editing.

This module cannot call a model. A scene describes editable objects, not executable
markup. Flat visual underlays remain honestly flat; only native objects are editable.
"""
from PIL import Image, ImageDraw, ImageOps

from app.canvas_schemas import Node, Scene
from app.services.master_layout import PALETTES, fitted_text


def scene_from_plan(plan):
    width, height = map(int, plan["canvas"]["recommended_size"].split("x"))
    base, ink, accent = PALETTES.get(plan["style"]["key"], PALETTES["appetite"])
    x, y, w, h = next(r["box"] for r in plan["layout"]["regions"] if r["role"] == "copy")
    count = plan["canvas"]["slice_count"]
    # Keep each text object inside one export tile, while retaining the planned
    # copy region. Visuals remain continuous across the native master canvas.
    intersections = [(max(x, i/count + .012/count), min(x+w, (i+1)/count - .012/count)) for i in range(count)]
    left, right = max(intersections, key=lambda b: b[1]-b[0])
    if right <= left:
        raise ValueError("构图没有可用文字区域")
    x, w = left, right-left
    entries, seen = [], set()
    for key in ("store_name", "headline", "subheadline", "price"):
        text = str(plan["copy"].get(key) or "").strip()
        if text and text not in seen:
            entries.append((key, text))
            seen.add(text)
    weights = {"store_name": 1.2, "headline": 2, "subheadline": 1, "price": 1.3}
    total = sum(weights[key] for key, _ in entries)
    nodes = []
    # Leave space for optional export watermarks; never bake one into a text layer.
    h = min(h, .90-y)
    for key, text in entries:
        slot = h*weights[key]/total
        nodes.append(Node(id=f"text_{key}", role=key, text=text,
                          box=(x, y, w, slot-8/height), color=accent if key == "price" else ink,
                          font_size=74 if key == "headline" else 50))
        y += slot
    return Scene(output_type=plan.get("output_type", "five_panel"), width=width, height=height,
                 slice_count=count, background_color=base,
                 ai_generated=plan.get("render_mode") == "illustration", nodes=nodes)


def validate_geometry(scene):
    text_nodes = [n for n in scene.nodes if n.visible and n.kind == "text" and n.text.strip()]
    if scene.output_type in {"logo", "package_main", "voucher_main"}:
        for node in scene.nodes:
            if node.visible and node.kind == "image" and node.role != "decoration":
                x, _, w, _ = node.box
                if x < .125-1e-8 or x+w > .875+1e-8:
                    raise ValueError(f"核心图片对象 {node.id} 超出中央 1:1 内容安全区")
    for node in text_nodes:
        x, y, w, h = node.box
        if scene.slice_count > 1:
            tile = min(scene.slice_count-1, int((x+1e-9)*scene.slice_count))
            if x+w > (tile+1)/scene.slice_count + 1e-8:
                raise ValueError(f"文字对象 {node.id} 跨越裁切边界")
        if scene.output_type in {"logo", "package_main", "voucher_main"} and (x < .125-1e-8 or x+w > .875+1e-8):
            raise ValueError(f"文字对象 {node.id} 超出中央 1:1 内容安全区")
        if scene.ai_generated and y+h > .92:
            raise ValueError(f"文字对象 {node.id} 占用了导出水印区域")
    for i, a in enumerate(text_nodes):
        ax, ay, aw, ah = a.box
        for b in text_nodes[i+1:]:
            bx, by, bw, bh = b.box
            if min(ax+aw, bx+bw)-max(ax, bx) > 1e-8 and min(ay+ah, by+bh)-max(ay, by) > 1e-8:
                raise ValueError(f"文字对象 {a.id} 与 {b.id} 的区域重叠")


def render_scene(scene, font_factory, background=None, assets=None):
    validate_geometry(scene)
    assets = assets or {}
    if background is not None and background.size != (scene.width, scene.height):
        raise ValueError("底图尺寸与版本不一致")
    canvas = background.convert("RGB").copy() if background is not None else Image.new("RGB", (scene.width, scene.height), scene.background_color)
    rendered = []
    for node in sorted(scene.nodes, key=lambda n: (n.z_index, n.id)):
        if not node.visible:
            continue
        x, y, w, h = (node.box[0]*scene.width, node.box[1]*scene.height,
                       node.box[2]*scene.width, node.box[3]*scene.height)
        draw = ImageDraw.Draw(canvas)
        if node.kind == "text":
            detail = fitted_text(draw, node.text, (x, y, w, h), font_factory, node.color, node.font_size)
            rendered.append({"id": node.id, "role": node.role, "layout": detail})
        elif node.kind == "shape":
            draw.rectangle((x, y, x+w-1, y+h-1), fill=node.color)
        else:
            asset = assets.get(node.asset_id)
            if not asset:
                raise ValueError("图片对象缺少已审核素材")
            with Image.open(asset.storage_path) as source:
                photo = ImageOps.contain(ImageOps.exif_transpose(source).convert("RGBA"),
                                         (max(1, round(w)), max(1, round(h))), Image.Resampling.LANCZOS)
                canvas.paste(photo, (round(x+(w-photo.width)/2), round(y+(h-photo.height)/2)), photo)
    return canvas, rendered
