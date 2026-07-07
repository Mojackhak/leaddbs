#!/usr/bin/env python3
"""Self-tests for the D normative-fiber same-day immediate wrapper."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from stnsnr_ulf_normative_fiber_immediate_observed import (
    connectome_slug_for_key,
    immediate_outputs_exist,
    observed_driver_argv,
    parse_connectomes,
)


def test_parse_connectomes() -> None:
    assert parse_connectomes("ppmi,dtor") == ["ppmi", "dtor"]
    assert parse_connectomes(" ppmi , dtor ") == ["ppmi", "dtor"]


def test_observed_driver_argv() -> None:
    args = argparse.Namespace(
        repo_root="/repo",
        asset_root="/asset",
        clinical_root="/clinical",
        readiness_root="/readiness",
        readiness_csv="",
        gate_status="/gate.csv",
        output_root="/out",
        hf_output_root="/hf",
        matlab_bin="/matlab",
        tau=800,
        min_coverage=5,
        fiber_chunk_size=10000,
        max_fibers=0,
        force_flip=False,
        force_rebuild=False,
    )
    argv = observed_driver_argv(
        args,
        post_scale="MDS-UPDRS III score (STN+SNr, immediate)",
        connectome="dtor",
        source_resolver_scan=True,
    )
    assert "--post-scale" in argv
    assert argv[argv.index("--post-scale") + 1] == "MDS-UPDRS III score (STN+SNr, immediate)"
    assert "--connectome" in argv
    assert argv[argv.index("--connectome") + 1] == "dtor"
    assert "--source-resolver-scan" in argv


def test_connectome_slug_for_key() -> None:
    assert connectome_slug_for_key("dtor") == "dtor_985_full_elias_2024"


def test_immediate_outputs_exist() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        observed_root = (
            root
            / "dtor_985_full_elias_2024"
            / "mds_updrs_iii_score_stn_snr_immediate"
            / "peak_efield_tau800_observed"
        )
        for relative in [
            "ulf_peak_efield_tau800_no_delta_hf/normative_ULF_fiber_generation_manifest.json",
            "ulf_peak_efield_tau800_delta_hf_adjusted/normative_ULF_fiber_generation_manifest.json",
            "tau_coverage_source_resolver_scan/normative_ULF_fiber_tau_coverage_source_resolver_manifest.json",
        ]:
            path = observed_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        assert immediate_outputs_exist(
            root,
            connectome="dtor",
            scale_slug="mds_updrs_iii_score_stn_snr_immediate",
            tau=800,
        )


def main() -> int:
    test_parse_connectomes()
    test_observed_driver_argv()
    test_connectome_slug_for_key()
    test_immediate_outputs_exist()
    print(json.dumps({"status": "PASS"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
