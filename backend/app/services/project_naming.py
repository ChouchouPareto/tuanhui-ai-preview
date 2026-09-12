import re

DEFAULT_NAMES = {"未命名门店项目", "未命名项目", "新建创作", "店铺五图项目"}


def five_image_name(store):
    store = re.sub(r"\s+", " ", str(store or "")).strip()
    if not store or store in {"未知", "待确认", "未识别", "未命名"}:
        return None
    return store[:112] + "店铺五图项目"


def update_project_name(project, snapshot, previous=None):
    store = snapshot.get("facts", {}).get("store_name")
    name = five_image_name(store)
    old_store = (previous or {}).get("facts", {}).get("store_name")
    # Only placeholders and names derived from this store may be replaced.
    managed = DEFAULT_NAMES | {five_image_name(old_store), old_store, store}
    if name and project.name in managed:
        project.name = name
