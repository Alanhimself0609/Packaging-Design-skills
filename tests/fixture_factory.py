from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


GROUPS = ["01_BG", "02_MAIN", "03_AUX", "04_LABEL", "05_TYPE"]


def build_fixture(root: Path, *, width: int = 600, height: int = 800) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    layer_specs = {
        "01_BG": [("bg-001", "background", "source-extracted")],
        "02_MAIN": [("main-001", "tea-leaf", "source-extracted")],
        "03_AUX": [("aux-001", "dots", "source-extracted")],
        "04_LABEL": [("label-001", "label-frame", "source-extracted")],
        "05_TYPE": [("type-001", "product-name", "source-extracted")],
    }
    images: dict[str, Image.Image] = {}

    background = Image.new("RGBA", (width, height), (242, 235, 210, 255))
    images["bg-001"] = background

    main = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(main)
    draw.ellipse((110, 220, 370, 510), fill=(35, 92, 65, 255))
    draw.polygon([(210, 250), (430, 150), (340, 400)], fill=(75, 130, 83, 255))
    images["main-001"] = main

    aux = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(aux)
    for x, y in [(70, 90), (510, 110), (490, 640), (80, 670)]:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(214, 156, 48, 255))
    images["aux-001"] = aux

    label = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(label)
    draw.rounded_rectangle((150, 520, 450, 690), radius=20, outline=(110, 62, 35, 255), width=8)
    images["label-001"] = label

    type_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(type_layer)
    draw.rectangle((205, 570, 395, 615), fill=(70, 40, 28, 255))
    draw.rectangle((250, 635, 350, 655), fill=(70, 40, 28, 255))
    images["type-001"] = type_layer

    groups = []
    composite = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for group_name in GROUPS:
        group_dir = root / "layers" / group_name
        group_dir.mkdir(parents=True, exist_ok=True)
        elements = []
        for element_id, name, method in layer_specs[group_name]:
            relative = Path("layers") / group_name / f"{element_id}.png"
            images[element_id].save(root / relative, dpi=(300, 300))
            composite = Image.alpha_composite(composite, images[element_id])
            elements.append(
                {
                    "id": element_id,
                    "name": name,
                    "file": relative.as_posix(),
                    "isolation_mode": (
                        "opaque-layer" if group_name == "01_BG" else "transparent-png"
                    ),
                    "mask_file": None,
                    "deferred_split": group_name == "03_AUX",
                    "contains": [name],
                    "source_method": method,
                    "confidence": "high",
                    "occlusion": "none",
                    "important": True,
                    "notes": "",
                }
            )
        groups.append({"name": group_name, "elements": elements})

    composite.save(root / "approved-flat.png", dpi=(300, 300))
    manifest = {
        "schema_version": "1.0",
        "project": "fixture-tea",
        "face": "front",
        "version": "v001",
        "reference": "approved-flat.png",
        "canvas": {
            "width_px": width,
            "height_px": height,
            "resolution_ppi": 300,
            "color_mode": "RGB",
            "concept_only": True,
            "physical_width_mm": None,
            "physical_height_mm": None,
            "target_ppi": 300,
        },
        "groups": groups,
        "output": {"directory": "output"},
        "quality_gate": {"minimum_similarity": 0.9},
    }
    manifest_path = root / "element-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
