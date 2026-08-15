#!/usr/bin/env python3
"""Validate a five-group packaging layer package and render QA artifacts."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


GROUP_ORDER = ["01_BG", "02_MAIN", "03_AUX", "04_LABEL", "05_TYPE"]
SOURCE_METHODS = {
    "source-extracted",
    "occlusion-completed",
    "upscaled-rebuilt",
    "retyped",
    "manual-redraw",
}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
OCCLUSION_LEVELS = {"none", "partial", "full"}
ISOLATION_MODES = {"opaque-layer", "transparent-png", "layer-mask"}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"清单不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"清单 JSON 无效：{exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("清单顶层必须是 JSON 对象。")
    return data


def require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"{label} 必须是正整数。")
    return value


def resolve_relative(base: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{label} 必须是非空相对路径。")
    candidate = Path(value)
    if candidate.is_absolute():
        raise ValidationError(f"{label} 必须使用相对路径：{value}")
    resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ValidationError(f"{label} 不能离开项目目录：{value}") from exc
    return resolved


def image_has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def alpha_is_opaque(image: Image.Image) -> bool:
    if not image_has_alpha(image):
        return True
    alpha = image.convert("RGBA").getchannel("A")
    return alpha.getextrema() == (255, 255)


def safe_name(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in text)
    return cleaned.strip("-") or fallback


def validate_manifest(
    manifest_path: Path, allow_low_confidence: bool
) -> tuple[dict[str, Any], dict[str, Any], Image.Image, Image.Image]:
    manifest = load_json(manifest_path)
    base = manifest_path.parent.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    quality_gate = manifest.get("quality_gate", {})
    if not isinstance(quality_gate, dict):
        raise ValidationError("quality_gate 必须是 JSON 对象。")
    minimum_similarity = quality_gate.get("minimum_similarity", 0.9)
    if (
        isinstance(minimum_similarity, bool)
        or not isinstance(minimum_similarity, (int, float))
        or not 0 <= minimum_similarity <= 1
    ):
        raise ValidationError("quality_gate.minimum_similarity 必须在 0 到 1 之间。")

    if manifest.get("schema_version") != "1.0":
        errors.append("schema_version 必须为 1.0。")

    canvas = manifest.get("canvas")
    if not isinstance(canvas, dict):
        raise ValidationError("canvas 必须是 JSON 对象。")
    width = require_int(canvas.get("width_px"), "canvas.width_px")
    height = require_int(canvas.get("height_px"), "canvas.height_px")
    resolution = require_int(canvas.get("resolution_ppi"), "canvas.resolution_ppi")
    if canvas.get("color_mode") != "RGB":
        errors.append("概念 PSD 当前只允许 RGB；生产 CMYK 转换必须由印厂条件决定。")
    if canvas.get("concept_only") is not True:
        errors.append("该流程只能生成概念 PSD，canvas.concept_only 必须为 true。")

    physical_width = canvas.get("physical_width_mm")
    physical_height = canvas.get("physical_height_mm")
    target_ppi = canvas.get("target_ppi", 300)
    print_check: dict[str, Any] = {"status": "concept-size-only"}
    if physical_width is not None or physical_height is not None:
        if not isinstance(physical_width, (int, float)) or physical_width <= 0:
            errors.append("physical_width_mm 必须为空或正数。")
        if not isinstance(physical_height, (int, float)) or physical_height <= 0:
            errors.append("physical_height_mm 必须为空或正数。")
        if not isinstance(target_ppi, (int, float)) or target_ppi <= 0:
            errors.append("target_ppi 必须是正数。")
        if not errors:
            required_width = math.ceil(physical_width / 25.4 * target_ppi)
            required_height = math.ceil(physical_height / 25.4 * target_ppi)
            print_check = {
                "status": "meets-target"
                if width >= required_width and height >= required_height
                else "below-target",
                "physical_width_mm": physical_width,
                "physical_height_mm": physical_height,
                "target_ppi": target_ppi,
                "required_width_px": required_width,
                "required_height_px": required_height,
                "actual_width_px": width,
                "actual_height_px": height,
            }
            if print_check["status"] == "below-target":
                warnings.append("画布像素低于按物理尺寸和目标 PPI 计算的要求。")

    try:
        reference_path = resolve_relative(base, manifest.get("reference"), "reference")
    except ValidationError as exc:
        errors.append(str(exc))
        reference_path = base / "__missing_reference__"

    reference: Image.Image | None = None
    if not reference_path.is_file():
        errors.append(f"批准目标图不存在：{reference_path}")
    else:
        with Image.open(reference_path) as image:
            if image.size != (width, height):
                errors.append(
                    f"批准目标图尺寸为 {image.size[0]}x{image.size[1]}，"
                    f"应为 {width}x{height}。"
                )
            reference = image.convert("RGBA")

    groups = manifest.get("groups")
    if not isinstance(groups, list):
        raise ValidationError("groups 必须是数组。")
    actual_group_names = [g.get("name") for g in groups if isinstance(g, dict)]
    if actual_group_names != GROUP_ORDER:
        errors.append(f"五组顺序必须严格为：{', '.join(GROUP_ORDER)}。")

    composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    seen_ids: set[str] = set()
    method_counts: Counter[str] = Counter()
    report_elements: list[dict[str, Any]] = []
    low_important: list[str] = []

    for group in groups:
        if not isinstance(group, dict):
            errors.append("每个 group 必须是 JSON 对象。")
            continue
        group_name = group.get("name")
        elements = group.get("elements")
        if not isinstance(elements, list):
            errors.append(f"{group_name}.elements 必须是数组。")
            continue
        if group_name == "01_BG" and not elements:
            errors.append("01_BG 至少需要一个完整背景元素。")
        for index, element in enumerate(elements):
            prefix = f"{group_name}.elements[{index}]"
            if not isinstance(element, dict):
                errors.append(f"{prefix} 必须是 JSON 对象。")
                continue
            element_id = element.get("id")
            if not isinstance(element_id, str) or not element_id.strip():
                errors.append(f"{prefix}.id 必须是非空字符串。")
                continue
            if element_id in seen_ids:
                errors.append(f"元素 id 重复：{element_id}")
            seen_ids.add(element_id)

            method = element.get("source_method")
            confidence = element.get("confidence")
            occlusion = element.get("occlusion")
            isolation_mode = element.get(
                "isolation_mode",
                "opaque-layer" if group_name == "01_BG" else "transparent-png",
            )
            if method not in SOURCE_METHODS:
                errors.append(f"{element_id} 的 source_method 无效：{method}")
            if confidence not in CONFIDENCE_LEVELS:
                errors.append(f"{element_id} 的 confidence 无效：{confidence}")
            if occlusion not in OCCLUSION_LEVELS:
                errors.append(f"{element_id} 的 occlusion 无效：{occlusion}")
            if isolation_mode not in ISOLATION_MODES:
                errors.append(f"{element_id} 的 isolation_mode 无效：{isolation_mode}")
            if group_name != "01_BG" and isolation_mode == "opaque-layer":
                errors.append(
                    f"非背景元素不能使用 opaque-layer：{element_id}；"
                    "请使用透明 PNG 或完整像素层加黑白蒙版。"
                )
            method_counts[str(method)] += 1
            if confidence == "low" and element.get("important") is True:
                low_important.append(element_id)

            try:
                file_path = resolve_relative(base, element.get("file"), f"{element_id}.file")
            except ValidationError as exc:
                errors.append(str(exc))
                continue
            if file_path.suffix.lower() != ".png":
                errors.append(f"元素必须使用 PNG：{element_id}")
            if not file_path.is_file():
                errors.append(f"元素文件不存在：{file_path}")
                continue

            try:
                with Image.open(file_path) as source:
                    if source.size != (width, height):
                        errors.append(
                            f"{element_id} 尺寸为 {source.size[0]}x{source.size[1]}，"
                            f"应为 {width}x{height}。"
                        )
                        continue
                    if isolation_mode == "transparent-png":
                        if not image_has_alpha(source):
                            errors.append(f"透明元素缺少透明通道：{element_id}")
                        layer = source.convert("RGBA")
                    elif isolation_mode == "layer-mask":
                        try:
                            mask_path = resolve_relative(
                                base, element.get("mask_file"), f"{element_id}.mask_file"
                            )
                        except ValidationError as exc:
                            errors.append(str(exc))
                            continue
                        if not mask_path.is_file():
                            errors.append(f"蒙版文件不存在：{mask_path}")
                            continue
                        with Image.open(mask_path) as mask_source:
                            if mask_source.size != (width, height):
                                errors.append(
                                    f"{element_id} 蒙版尺寸为 "
                                    f"{mask_source.size[0]}x{mask_source.size[1]}，"
                                    f"应为 {width}x{height}。"
                                )
                                continue
                            mask = mask_source.convert("L")
                        layer = source.convert("RGBA")
                        layer.putalpha(mask)
                    else:
                        if not alpha_is_opaque(source):
                            errors.append(f"完整像素层必须不透明：{element_id}")
                        layer = source.convert("RGBA")
                    composite = Image.alpha_composite(composite, layer)
            except OSError as exc:
                errors.append(f"无法读取元素 {element_id}：{exc}")
                continue

            report_elements.append(
                {
                    "id": element_id,
                    "name": element.get("name", element_id),
                    "group": group_name,
                    "file": str(element.get("file")),
                    "isolation_mode": isolation_mode,
                    "mask_file": element.get("mask_file"),
                    "deferred_split": bool(element.get("deferred_split")),
                    "contains": element.get("contains", []),
                    "source_method": method,
                    "confidence": confidence,
                    "occlusion": occlusion,
                    "important": bool(element.get("important")),
                    "notes": element.get("notes", ""),
                }
            )

    if low_important:
        warnings.append("以下重要元素可信度为 low，必须确认后才能装配：" + ", ".join(low_important))

    if reference is None:
        reference = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    difference = ImageChops.difference(composite, reference)
    difference_rgb = difference.convert("RGB")
    stat = ImageStat.Stat(difference_rgb)
    mean_absolute_error = sum(stat.mean) / 3.0
    normalized_similarity = max(0.0, 1.0 - mean_absolute_error / 255.0)
    max_channel_error = max(channel[1] for channel in difference_rgb.getextrema())
    gray = difference_rgb.convert("L")
    gray_values = (
        gray.get_flattened_data()
        if hasattr(gray, "get_flattened_data")
        else gray.getdata()
    )
    changed_pixels = sum(1 for value in gray_values if value > 2)
    changed_ratio = changed_pixels / (width * height)
    heatmap = difference_rgb.point(lambda value: min(255, value * 6))
    below_similarity_gate = normalized_similarity < float(minimum_similarity)
    if below_similarity_gate:
        warnings.append(
            f"重组相似度 {normalized_similarity:.4f} 低于门槛 "
            f"{float(minimum_similarity):.4f}。"
        )

    if errors:
        raise ValidationError("\n".join(errors))

    output_config = manifest.get("output")
    if not isinstance(output_config, dict):
        raise ValidationError("output 必须是 JSON 对象。")
    output_dir = resolve_relative(base, output_config.get("directory", "output"), "output.directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    project = safe_name(manifest.get("project"), "project")
    face = safe_name(manifest.get("face"), "face")
    preview_path = output_dir / f"{project}_{face}_recomposite.png"
    difference_path = output_dir / f"{project}_{face}_difference.png"
    report_path = output_dir / "layer-fidelity-report.json"
    composite.save(preview_path)
    heatmap.save(difference_path)

    report = {
        "schema_version": "1.0",
        "project": manifest.get("project"),
        "face": manifest.get("face"),
        "concept_only": True,
        "reference": manifest.get("reference"),
        "canvas": {
            "width_px": width,
            "height_px": height,
            "resolution_ppi": resolution,
            "color_mode": "RGB",
        },
        "print_size_check": print_check,
        "comparison": {
            "mean_absolute_error": round(mean_absolute_error, 4),
            "normalized_similarity": round(normalized_similarity, 6),
            "minimum_similarity": float(minimum_similarity),
            "passes_similarity_gate": not below_similarity_gate,
            "max_channel_error": max_channel_error,
            "changed_pixel_ratio_over_2": round(changed_ratio, 6),
            "preview": str(preview_path.relative_to(base)),
            "difference": str(difference_path.relative_to(base)),
        },
        "summary": {
            "element_count": len(report_elements),
            "source_extracted": method_counts["source-extracted"],
            "occlusion_completed": method_counts["occlusion-completed"],
            "upscaled_rebuilt": method_counts["upscaled-rebuilt"],
            "retyped": method_counts["retyped"],
            "manual_redraw": method_counts["manual-redraw"],
            "low_confidence": sum(1 for e in report_elements if e["confidence"] == "low"),
            "requires_user_confirmation": bool(low_important),
        },
        "warnings": warnings,
        "elements": report_elements,
        "limitations": [
            "完全被遮挡的原始像素无法精确恢复，只能合理补全。",
            "没有真实尺寸、材料和印厂参数时，本文件不是生产尺寸。",
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if low_important and not allow_low_confidence:
        raise ValidationError(
            "存在低可信重要元素，已生成报告但停止 PSD 装配。"
            "确认后可使用 --allow-low-confidence 继续。"
        )
    if below_similarity_gate:
        raise ValidationError(
            f"重组相似度 {normalized_similarity:.4f} 未达到 "
            f"{float(minimum_similarity):.4f}，请先修正责任图层。"
        )
    return manifest, report, composite, heatmap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="检查包装五层素材包并生成重组预览、差异图和还原报告。"
    )
    parser.add_argument("manifest", type=Path, help="element-manifest.json 路径")
    parser.add_argument(
        "--allow-low-confidence",
        action="store_true",
        help="用户已确认低可信重要元素后继续。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        _, report, _, _ = validate_manifest(
            args.manifest.resolve(), args.allow_low_confidence
        )
    except ValidationError as exc:
        print(f"VALIDATION_FAILED\n{exc}", file=sys.stderr)
        return 2
    print("VALIDATION_OK")
    print(json.dumps(report["comparison"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
