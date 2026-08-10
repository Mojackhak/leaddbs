"""Read-only status validation across both tractogram spaces and scenes."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from .. import pipeline
from ..config import resolve_config
from ..identity import file_sha256
from ..publication import OWNER
from ..state import atomic_write_json
from ..tck import write_selected_tck
from .helpers import minimal_document


def test_status_requires_exact_paired_tcks_and_visualization_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = minimal_document(tmp_path)
    subject_dir = tmp_path / "sub-001"
    document["subjects"][0]["subject_dir"] = str(subject_dir)
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    output_root = (
        subject_dir / "connectomics" / "dMRI" / "mrtrix_seed_target"
    )
    target_space = config.atlas.space
    streamlines = [np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32)]
    artifacts = []
    for coordinate_space in ("native", target_space):
        root = output_root / "tractograms" / coordinate_space / "lh" / "Seed"
        for semantic_key, path in (
            ("lh/Seed/seedwide", root / "seedwide.tck"),
            (
                "lh/Seed/target/lh/Target",
                root / "targets" / "lh" / "Target.tck",
            ),
        ):
            write_selected_tck(streamlines, np.asarray([True]), path)
            artifacts.append(
                {
                    "semantic_key": semantic_key,
                    "coordinate_space": coordinate_space,
                    "path": str(path),
                    "sha256": file_sha256(path),
                    "streamline_count": 1,
                }
            )
    scene_root = output_root / "visualization" / target_space / "lh" / "Seed"
    scene_artifacts = []
    for suffix in ("fig", "png", "pdf"):
        path = scene_root / f"scene.{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(suffix.encode("ascii"))
        scene_artifacts.append({"path": str(path), "sha256": file_sha256(path)})
    fingerprints = {"sampling": "s", "color": "c", "style_camera": "v"}
    complete_path = scene_root / "complete.json"
    atomic_write_json(
        complete_path,
        {
            "status": "complete",
            "fingerprints": fingerprints,
            "artifacts": scene_artifacts,
        },
    )
    state_path = output_root / "work" / "state.json"
    state = {
        "owner": OWNER,
        "status": "complete",
        "published_artifacts": artifacts,
        "visualization_scenes": {
            "lh/Seed": {
                "complete_path": str(complete_path),
                "fingerprints": fingerprints,
            }
        },
    }
    atomic_write_json(state_path, state)
    monkeypatch.setattr(pipeline, "load_config", lambda _path: config)
    monkeypatch.setattr(pipeline, "validate_tck", lambda *_args, **_kwargs: None)
    result = pipeline.status_batch(tmp_path / "config.yaml")
    assert result["status"] == "complete"
    assert result["subjects"][0]["artifact_count"] == 4
    assert result["subjects"][0]["artifact_errors"] == []

    Path(scene_artifacts[1]["path"]).write_bytes(b"changed")
    invalid = pipeline.status_batch(tmp_path / "config.yaml")
    assert invalid["status"] == "incomplete"
    assert invalid["subjects"][0]["status"] == "artifact_error"
    assert any(
        "visualization artifact failed" in error
        for error in invalid["subjects"][0]["artifact_errors"]
    )
