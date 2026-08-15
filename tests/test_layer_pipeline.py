from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from fixture_factory import build_fixture


SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "design-packaging"
    / "scripts"
    / "validate_layer_package.py"
)
SPEC = importlib.util.spec_from_file_location("validate_layer_package", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LayerPipelineTests(unittest.TestCase):
    def test_valid_fixture_recomposes_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest = build_fixture(Path(temp))
            _, report, _, _ = MODULE.validate_manifest(manifest, False)
            self.assertEqual(report["comparison"]["mean_absolute_error"], 0.0)
            self.assertTrue(report["comparison"]["passes_similarity_gate"])
            self.assertEqual(report["comparison"]["changed_pixel_ratio_over_2"], 0.0)
            self.assertEqual(report["summary"]["element_count"], 5)
            self.assertTrue(
                next(e for e in report["elements"] if e["id"] == "aux-001")[
                    "deferred_split"
                ]
            )

    def test_wrong_layer_size_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = build_fixture(root)
            Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(
                root / "layers" / "02_MAIN" / "main-001.png"
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate_manifest(manifest, False)

    def test_full_canvas_pixel_layer_with_mask_recomposes_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest_path = build_fixture(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            main_file = root / "layers" / "02_MAIN" / "main-001.png"
            with Image.open(main_file) as image:
                rgba = image.convert("RGBA")
                mask = rgba.getchannel("A")
                rgb = rgba.convert("RGB")
            rgb.save(main_file)
            mask_file = root / "layers" / "02_MAIN" / "main-001-mask.png"
            mask.save(mask_file)
            element = manifest["groups"][1]["elements"][0]
            element["isolation_mode"] = "layer-mask"
            element["mask_file"] = "layers/02_MAIN/main-001-mask.png"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _, report, _, _ = MODULE.validate_manifest(manifest_path, False)
            self.assertEqual(report["comparison"]["mean_absolute_error"], 0.0)
            self.assertEqual(report["elements"][1]["isolation_mode"], "layer-mask")

    def test_low_confidence_important_element_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manifest_path = build_fixture(Path(temp))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["groups"][1]["elements"][0]["confidence"] = "low"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate_manifest(manifest_path, False)
            _, report, _, _ = MODULE.validate_manifest(manifest_path, True)
            self.assertTrue(report["summary"]["requires_user_confirmation"])

    def test_similarity_below_ninety_percent_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest_path = build_fixture(root)
            Image.new("RGBA", (600, 800), (0, 0, 0, 255)).save(
                root / "approved-flat.png"
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate_manifest(manifest_path, False)
            report = json.loads(
                (root / "output" / "layer-fidelity-report.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(report["comparison"]["passes_similarity_gate"])


if __name__ == "__main__":
    unittest.main()
