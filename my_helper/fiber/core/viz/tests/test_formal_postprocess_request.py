"""Static guards for the formal all-scale postprocess request."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
REQUEST_PATH = (
    REPOSITORY_ROOT
    / "my_helper/stnsnr/config/four_model_v1/formal_postprocess.json"
)
EXPECTED_REQUEST_SHA256 = (
    "144ad7a1e775c1bf01f5d99df285a87b31bae7075aa3692d714201f1953e6ab0"
)
EXPECTED_OUTPUT_ROOT = (
    "/Volumes/VAL/STNSNr/summary/spot/postprocess/"
    "dual_frequency_four_model_v1/task17-formal-postprocess-v1-20260722"
)
EXPECTED_PUBLICATIONS = {
    "direct_voxel_main": {
        "root": (
            "/Volumes/VAL/STNSNr/summary/spot/direct_voxel/"
            "dual_frequency_four_model_v1"
        ),
        "manifest": "model_manifest.json",
    },
    "direct_voxel_in_sample": {
        "root": (
            "/Volumes/VAL/STNSNr/summary/spot/direct_voxel/"
            "dual_frequency_four_model_v1/extensions/"
            "task17-final-in-sample-v2-20260719"
        ),
        "manifest": "extension_manifest.json",
    },
    "normative_fiber_main": {
        "root": (
            "/Volumes/VAL/STNSNr/summary/spot/normative_fiber/"
            "dual_frequency_four_model_v1"
        ),
        "manifest": "model_manifest.json",
    },
    "normative_fiber_in_sample": {
        "root": (
            "/Volumes/VAL/STNSNr/summary/spot/normative_fiber/"
            "dual_frequency_four_model_v1/extensions/"
            "task17-final-in-sample-v2-20260719"
        ),
        "manifest": "extension_manifest.json",
    },
}
EXPECTED_RESOURCES = {
    "background": "/Volumes/VAL/STNSNr/config/atlas/7T_100um_Edlow_2019.nii",
    "reference_mask": (
        "/Users/mojackhu/Github/leaddbs/templates/space/"
        "MNI152NLin2009bAsym/atlases/"
        "Custom_Ewert_Zhang_Middlebrooks0.05/rh/STN.nii.gz"
    ),
    "addon_mask": (
        "/Users/mojackhu/Github/leaddbs/templates/space/"
        "MNI152NLin2009bAsym/atlases/"
        "Custom_Ewert_Zhang_Middlebrooks0.05/rh/SNr.nii.gz"
    ),
    "fiber_spatial_config": (
        "/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/"
        "config/four_model_v1/fiber_spatial_projection.yaml"
    ),
}
FORBIDDEN_SOURCE_PARTS = frozenset({".runs", "tasks", "work", "runtime_work"})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_formal_postprocess_request_is_frozen_and_public_only() -> None:
    document = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))

    assert _sha256(REQUEST_PATH) == EXPECTED_REQUEST_SHA256
    assert set(document) == {
        "schema_version",
        "output_root",
        "publications",
        "scales",
        "components",
        "resources",
    }
    assert document["schema_version"] == "dual_frequency_formal_postprocess_v1"
    assert document["output_root"] == EXPECTED_OUTPUT_ROOT
    assert document["publications"] == EXPECTED_PUBLICATIONS
    assert document["scales"] == "all_available"
    assert document["components"] == ["paired_fit", "voxel_2d", "fiber_2d"]
    assert document["resources"] == EXPECTED_RESOURCES

    guarded_paths = [
        Path(document["output_root"]),
        *(
            Path(publication["root"])
            for publication in document["publications"].values()
        ),
    ]
    assert all(path.is_absolute() for path in guarded_paths)
    assert all(
        FORBIDDEN_SOURCE_PARTS.isdisjoint(path.parts) for path in guarded_paths
    )
    assert "file://" not in REQUEST_PATH.read_text(encoding="utf-8")
