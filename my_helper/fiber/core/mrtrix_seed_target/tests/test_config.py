"""Strict YAML and approved real-configuration contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .. import cli
from ..cli import build_parser
from ..config import load_config, resolve_config
from ..errors import ConfigurationError
from ..identity import git_head_commit
from ..validation import _layer_paths
from .helpers import minimal_document


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    document = yaml.safe_dump(minimal_document(tmp_path), sort_keys=False)
    path.write_text(document + "schema_version: 1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="duplicate YAML key"):
        load_config(path)


def test_unknown_and_removed_pairwise_fields_are_rejected(tmp_path: Path) -> None:
    document = minimal_document(tmp_path)
    document["tracking"]["stop_at_target"] = False
    with pytest.raises(ConfigurationError, match="Additional properties"):
        resolve_config(document, source_path=tmp_path / "config.yaml")


def test_duplicate_subject_id_and_directory_are_rejected(tmp_path: Path) -> None:
    document = minimal_document(tmp_path, subject_count=2)
    document["subjects"][1]["id"] = document["subjects"][0]["id"]
    with pytest.raises(ConfigurationError, match="duplicate subject id"):
        resolve_config(document, source_path=tmp_path / "config.yaml")
    document = minimal_document(tmp_path, subject_count=2)
    document["subjects"][1]["subject_dir"] = document["subjects"][0]["subject_dir"]
    with pytest.raises(ConfigurationError, match="duplicate resolved subject directory"):
        resolve_config(document, source_path=tmp_path / "config.yaml")


def test_cli_exposes_only_yaml_config_for_three_commands() -> None:
    parser = build_parser()
    for command in ("validate", "run", "status"):
        parsed = parser.parse_args([command, "--config", "/tmp/config.yaml"])
        assert parsed.command == command
        assert vars(parsed).keys() == {"command", "config"}
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["run", "--config", "/tmp/config.yaml", "--target-atlas-root", "/tmp/a"]
        )


def test_cli_reports_keyboard_interrupt_with_exit_130(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "run_batch", lambda _path: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert cli.main(["run", "--config", "/tmp/config.yaml"]) == 130
    assert '"status": "interrupted"' in capsys.readouterr().err


def test_approved_formal_and_test_yaml_counts() -> None:
    formal_path = Path("/Volumes/VAL/STNSNr/config/mrtrix_seed_target.yaml")
    test_path = Path("/Volumes/VAL/STNSNr/config/mrtrix_seed_target_test.yaml")
    if not formal_path.is_file() or not test_path.is_file():
        pytest.skip("approved real YAML files are unavailable")
    formal = load_config(formal_path)
    test = load_config(test_path)
    assert len(formal.subjects) == 16
    assert [len(seed.targets) for seed in formal.atlas.seeds] == [18, 18]
    assert [target.roi_id for target in formal.atlas.seeds[0].targets] == [
        "VM_thalamus",
        "VLA_thalamus",
        "GPi",
        "sPf_thalamus",
        "GPe",
        "PPN",
        "VLP_thalamus",
        "VA_thalamus",
        "Pf_thalamus",
        "preSMA",
        "SMA",
        "posterior_putamen",
        "CM_thalamus",
        "caudate",
        "premotor",
        "M1",
        "DLPFC",
        "RN",
    ]
    assert formal.execution.maximum_seedwide_streamlines == 100_000_000
    assert len(test.subjects) == 2
    assert [len(seed.targets) for seed in test.atlas.seeds] == [2, 2]
    assert test.execution.generation_chunk_streamlines == 50_000
    assert test.execution.maximum_seedwide_streamlines == 50_000


def test_code_identity_layers_do_not_cross_invalidate_scientific_work() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    preparation = {path.name for path in _layer_paths(repo_root, "preparation")}
    tracking = {path.name for path in _layer_paths(repo_root, "tracking")}
    publication = {path.name for path in _layer_paths(repo_root, "publication")}
    assert "publication.py" not in preparation
    assert "publication.py" not in tracking
    assert "tracking.py" not in preparation
    assert "tracking.py" in tracking
    assert "publication.py" in publication


def test_git_head_commit_is_recorded_as_full_sha() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    commit = git_head_commit(repo_root)
    assert len(commit) == 40
    assert set(commit).issubset(set("0123456789abcdef"))
