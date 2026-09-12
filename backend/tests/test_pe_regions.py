import importlib.util
import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from app.schemas import OCRPayload
from app.services.layout_catalog import LAYOUTS, OUTPUT_SPECS, FULL_PLAN_DEFAULTS
from app.services.design_plan import build_design_plan, validate_design_plan
from app.services.image_generation import render_and_slice, build_visual_prompt


def test_twelve_distinct_original_layouts():
    assert len(LAYOUTS) == 12
    assert len({json.dumps(x["regions"]) for x in LAYOUTS}) == 12
    for layout in LAYOUTS:
        assert sum(r["role"] == "copy" for r in layout["regions"]) == 1
        for region in layout["regions"]:
            x,y,w,h = region["box"]
            assert min(x,y) >= 0 and min(w,h) > 0 and x+w <= 1.001 and y+h <= 1.001
            assert region["visible_border"] is False


def test_layout_tampering_fails():
    plan = build_design_plan({"store_name":"山西面馆"})
    plan["layout"]["regions"][0]["box"] = [0,0,1,1]
    with pytest.raises(ValueError, match="模板库"):
        validate_design_plan(plan)


def test_one_photo_selects_one_visual_region():
    plan = build_design_plan({"store_name":"山西面馆"}, asset_count=1)
    assert sum(r["role"]=="visual" for r in plan["layout"]["regions"]) == 1


@pytest.mark.parametrize("bad", ["全国第一", "百分百有效", "吊打同行"])
def test_risky_copy_is_not_passed_to_generation(bad):
    with pytest.raises(ValueError, match="文案"):
        build_design_plan({"store_name":"山西面馆", "hero_item":bad})


@pytest.mark.parametrize("spec,count,width", [("five_panel",5,4000),("three_panel",3,2400)])
def test_export_ratio_and_watermark_are_independent(tmp_path,spec,count,width):
    plan = build_design_plan({"store_name":"山西面馆"}, output_type=spec)
    plan["render_mode"]="illustration"
    raw=io.BytesIO();Image.new("RGB",(width,600),"#752424").save(raw,"PNG")
    result=render_and_slice(raw.getvalue(),plan,tmp_path)
    assert len(result["slices"]) == len(result["clean_slices"]) == count
    with Image.open(tmp_path/result["long_image"]) as marked, Image.open(tmp_path/result["clean_long_image"]) as clean:
        assert marked.size == clean.size == (width,600)
        assert ImageChops.difference(marked,clean).getbbox()
        # Outside the export-only watermark footer, pixels are identical.
        assert ImageChops.difference(marked.crop((0,0,width,552)),clean.crop((0,0,width,552))).getbbox() is None
        for i,file in enumerate(result["clean_slices"]):
            with Image.open(tmp_path/file) as part:
                assert part.size==(800,600)
                assert ImageChops.difference(part,clean.crop((800*i,0,800*(i+1),600))).getbbox() is None
    prompt=build_visual_prompt(plan)
    assert plan["layout"]["id"] in prompt
    assert "全宽分成五个等宽构图区域" not in prompt
    assert "底部黑色渐变" not in prompt


def test_output_catalog_matches_confirmed_rules():
    assert len(OUTPUT_SPECS)==9
    assert FULL_PLAN_DEFAULTS==["voucher_main","five_panel","logo"]
    for kind in ("logo","package_main","voucher_main"):
        assert OUTPUT_SPECS[kind]["safe_area"]==[.125,0,.75,1]
    assert OUTPUT_SPECS["detail"]["configured"] is False


@pytest.mark.parametrize("confidence,evidence,visible", [
    (.4,"山西面馆","山西面馆"),
    (.99,"不存在","山西面馆"),
    (.99,"山西面馆","另一家店"),
])
def test_explicit_model_store_name_cannot_bypass_evidence(confidence,evidence,visible):
    value=OCRPayload.model_validate({"visible_text":visible,"store_name":"山西面馆",
        "store_name_candidates":[{"name":"山西面馆","evidence":evidence,"confidence":confidence}]})
    assert value.store_name is None and value.needs_confirmation


def test_backup_is_append_only_with_hashes(tmp_path):
    path=Path(__file__).resolve().parents[2]/"scripts/backup_pe.py"
    spec=importlib.util.spec_from_file_location("backup_pe",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    first=module.backup("test",tmp_path);content=first.read_bytes()
    second=module.backup("test",tmp_path)
    assert first!=second and first.read_bytes()==content
    assert "SHA256" in content.decode()
