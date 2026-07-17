"""Compact QC configuration tests."""

from pathlib import Path

import pytest

from ..config import PRESET_NAME, load_config, resolve_config
from ..errors import ConfigurationError
from ..pipeline import _json_safe
from ..pipeline import _artifact_records


def _document(tmp_path: Path) -> dict:
    return {
        "schema_version": 1,
        "inputs": {"tracking_config": "tracking.yaml"},
        "qc": {"preset": PRESET_NAME},
        "output": {"root": "qc", "run_name": "fixed300k_all_subjects"},
    }


def test_compact_config_resolves_relative_paths(tmp_path: Path) -> None:
    config = resolve_config(_document(tmp_path), source_path=tmp_path / "qc.yaml")
    assert config.tracking_config == tmp_path / "tracking.yaml"
    assert config.output_root == tmp_path / "qc"
    assert config.output_directory == tmp_path / "qc" / "fixed300k_all_subjects"
    assert config.resolved_mapping["qc"]["resolved_preset"]["profile"]["value"] == "hit_fraction"


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    document = _document(tmp_path)
    document["unexpected"] = True
    with pytest.raises(ConfigurationError, match="Additional properties"):
        resolve_config(document, source_path=tmp_path / "qc.yaml")


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "qc.yaml"
    path.write_text(
        """schema_version: 1
inputs:
  tracking_config: a.yaml
qc:
  preset: robust_target_profile_v1
output:
  root: qc
  root: duplicate
  run_name: test
""",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="duplicate YAML key"):
        load_config(path)


def test_run_name_cannot_contain_a_path(tmp_path: Path) -> None:
    document = _document(tmp_path)
    document["output"]["run_name"] = "nested/run"
    with pytest.raises(ConfigurationError, match="does not match"):
        resolve_config(document, source_path=tmp_path / "qc.yaml")


def test_resolved_mapping_is_json_safe(tmp_path: Path) -> None:
    config = resolve_config(_document(tmp_path), source_path=tmp_path / "qc.yaml")
    result = _json_safe(config.resolved_mapping)
    assert result["qc"]["preset"] == PRESET_NAME
    assert isinstance(result, dict)


def test_artifact_manifest_ignores_appledouble_sidecars(tmp_path: Path) -> None:
    (tmp_path / "result.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (tmp_path / "._result.csv").write_bytes(b"metadata")
    artifacts = _artifact_records(tmp_path)
    assert [artifact["path"] for artifact in artifacts] == ["result.csv"]
