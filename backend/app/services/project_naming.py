import re

DEFAULT_NAMES = {"未命名门店项目", "未命名项目", "新建创作", "店铺五图项目"}
DIRECTIONS = {"five_panel": "五图", "logo": "Logo", "main_image": "主图", "full_plan": "全案"}


def five_image_name(store):
    return project_title(store, "five_panel")


def project_title(store, output_type):
    store = re.sub(r"\s+", " ", str(store or "")).strip()
    if not store or store in {"未知", "待确认", "未识别", "未命名"}:
        return None
    direction = DIRECTIONS.get(output_type)
    if not direction:
        return None
    suffix = f"店铺{direction}项目"
    return store[:120 - len(suffix)] + suffix


def update_project_name(project, snapshot, previous=None):
    store = snapshot.get("facts", {}).get("store_name")
    name = project_title(store, snapshot.get("output_type", "five_panel"))
    old_store = (previous or {}).get("facts", {}).get("store_name")
    # Only placeholders and names derived from this store may be replaced.
    managed = DEFAULT_NAMES | {project_title(old_store, (previous or {}).get("output_type", "five_panel")), old_store, store}
    if name and project.name in managed:
        project.name = name
