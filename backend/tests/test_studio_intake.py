from test_m1_creations import setup_creation, submit, confirm


def test_studio_brand_without_photo_can_generate(client):
    _, asset, base = setup_creation(client, dish=False)
    review = submit(client, base, asset, text="店名：袁记云饺", input_mode="chat", allow_illustration=True).json()
    assert review["snapshot"]["ready"]
    assert review["snapshot"]["render_mode"] == "illustration"
    assert review["snapshot"]["assets"][0]["usage"] == "recognition_only"
    assert confirm(client, base, review).status_code == 200


def test_studio_real_dishes_are_not_replaced_with_illustrations(client):
    _, asset, base = setup_creation(client)
    review = submit(client, base, asset, text="", input_mode="chat", allow_illustration=True).json()
    assert review["snapshot"]["ready"]
    assert review["snapshot"]["render_mode"] == "real_assets"


def test_studio_cannot_invent_direction_or_ignore_real_only(client):
    _, asset, base = setup_creation(client, dish=False)
    review = submit(client, base, asset, text="帮我做图", input_mode="chat", allow_illustration=True).json()
    assert not review["snapshot"]["ready"]
    review = submit(client, base, asset, expected_revision=1, text="店名：测试店，使用真实照片", input_mode="chat", allow_illustration=True).json()
    assert not review["snapshot"]["ready"]
    assert review["snapshot"]["render_mode"] == "real_assets"
