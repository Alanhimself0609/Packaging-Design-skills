#!/usr/bin/env python3
"""Inspect a concept PSD with psd-tools as an independent structural check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from psd_tools import PSDImage
except ImportError:
    print(
        "缺少 psd-tools。请先安装 scripts/requirements.txt。",
        file=sys.stderr,
    )
    raise SystemExit(3)


GROUP_ORDER = ["01_BG", "02_MAIN", "03_AUX", "04_LABEL", "05_TYPE"]


def load_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="独立检查五层概念 PSD 结构。")
    parser.add_argument("psd", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    psd = PSDImage.open(args.psd)
    manifest = load_manifest(args.manifest)
    errors: list[str] = []
    groups = [layer for layer in psd if layer.is_group()]
    actual_names = [layer.name for layer in groups]
    if actual_names != GROUP_ORDER:
        errors.append(
            "顶层组的背景到前景顺序不正确："
            + ", ".join(actual_names)
        )
    top_level_pixels = [layer.name for layer in psd if not layer.is_group()]
    if top_level_pixels:
        errors.append("存在未归组顶层图层：" + ", ".join(top_level_pixels))

    expected_counts: dict[str, int] = {}
    if manifest is not None:
        canvas = manifest.get("canvas", {})
        expected_size = (canvas.get("width_px"), canvas.get("height_px"))
        if psd.size != expected_size:
            errors.append(f"PSD 尺寸为 {psd.size}，应为 {expected_size}。")
        expected_counts = {
            group["name"]: len(group.get("elements", []))
            for group in manifest.get("groups", [])
        }

    group_details = []
    for group in groups:
        child_names = [child.name for child in group]
        if group.name in expected_counts and len(child_names) != expected_counts[group.name]:
            errors.append(
                f"{group.name} 包含 {len(child_names)} 个元素，"
                f"应为 {expected_counts[group.name]} 个。"
            )
        group_details.append(
            {"name": group.name, "element_count": len(child_names), "elements": child_names}
        )

    report = {
        "valid": not errors,
        "psd": str(args.psd.resolve()),
        "size": {"width_px": psd.width, "height_px": psd.height},
        "mode": psd.color_mode.name,
        "groups_background_to_foreground": group_details,
        "errors": errors,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
