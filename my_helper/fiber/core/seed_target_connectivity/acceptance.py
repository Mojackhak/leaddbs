"""Explicit-fixture acceptance runner for the generic public API."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml

from .artifacts import collect_code_provenance
from .atlas import discover_targets
from .config import resolve_config
from .connectome import LeadDBSHDF5Connectome, open_connectome
from .errors import AcceptanceError
from .models import ConnectivityConfig, ConnectivityRunResult, FiberChunk
from .pipeline import compute_seed_target_statistics
from .traversal import build_sparse_lookup, optimized_membership, reference_membership


@dataclass(frozen=True)
class AcceptanceSeed:
    fixture_id: str
    path: Path


@dataclass(frozen=True)
class AcceptanceFixture:
    target_atlas_root: Path
    seeds: tuple[AcceptanceSeed, ...]
    connectome: Path
    config: ConnectivityConfig
    seed_connected_per_run: int
    background_fibers: int


@dataclass(frozen=True)
class AcceptanceRunEvidence:
    fixture_id: str
    run_dir: Path
    run_fingerprint: str
    n_seed_fibers: int
    target_cache_hit: bool
    artifact_hashes: Mapping[str, str]

    def as_mapping(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "run_dir": str(self.run_dir),
            "run_fingerprint": self.run_fingerprint,
            "n_seed_fibers": self.n_seed_fibers,
            "target_cache_hit": self.target_cache_hit,
            "artifact_hashes": dict(self.artifact_hashes),
        }


@dataclass(frozen=True)
class AcceptanceReport:
    target_count: int
    runs: tuple[AcceptanceRunEvidence, ...]
    sampled_fiber_count: int
    sampled_kernel_equivalence: bool
    identical_rerun_hashes: bool
    deterministic_ranks: bool
    finite_valid_metrics: bool
    source_state_unchanged: bool

    def as_mapping(self) -> dict[str, Any]:
        return {
            "status": "complete",
            "target_count": self.target_count,
            "runs": [run.as_mapping() for run in self.runs],
            "sampled_fiber_count": self.sampled_fiber_count,
            "sampled_kernel_equivalence": self.sampled_kernel_equivalence,
            "identical_rerun_hashes": self.identical_rerun_hashes,
            "deterministic_ranks": self.deterministic_ranks,
            "finite_valid_metrics": self.finite_valid_metrics,
            "source_state_unchanged": self.source_state_unchanged,
        }


def _strict_keys(document: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(document) - allowed)
    if unknown:
        raise AcceptanceError(f"{context} contains unknown fields: {','.join(unknown)}")


def _resolve_path(repo_root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise AcceptanceError(f"{field} must be a non-empty path string")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def load_acceptance_fixture(
    fixture_path: Path | str,
    repo_root: Path | str,
) -> AcceptanceFixture:
    """Load one strict explicit acceptance fixture."""
    source = Path(fixture_path)
    root = Path(repo_root).expanduser().resolve()
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AcceptanceError(f"failed to read acceptance fixture {source}: {exc}") from exc
    if not isinstance(document, dict):
        raise AcceptanceError("acceptance fixture must contain a YAML object")
    _strict_keys(
        document,
        {"schema_version", "target_atlas_root", "seeds", "connectome", "config", "sampling"},
        "acceptance fixture",
    )
    if document.get("schema_version") != 1:
        raise AcceptanceError("acceptance fixture schema_version must equal 1")
    seed_documents = document.get("seeds")
    if not isinstance(seed_documents, list) or not seed_documents:
        raise AcceptanceError("acceptance fixture seeds must be a non-empty list")
    seeds: list[AcceptanceSeed] = []
    for index, seed_document in enumerate(seed_documents):
        if not isinstance(seed_document, dict):
            raise AcceptanceError(f"seeds[{index}] must be an object")
        _strict_keys(seed_document, {"fixture_id", "path"}, f"seeds[{index}]")
        fixture_id = seed_document.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id:
            raise AcceptanceError(f"seeds[{index}].fixture_id must be non-empty")
        seeds.append(
            AcceptanceSeed(
                fixture_id=fixture_id,
                path=_resolve_path(root, seed_document.get("path"), f"seeds[{index}].path"),
            )
        )
    if len({seed.fixture_id for seed in seeds}) != len(seeds):
        raise AcceptanceError("acceptance fixture seed IDs must be unique")
    sampling = document.get("sampling", {})
    if not isinstance(sampling, dict):
        raise AcceptanceError("acceptance fixture sampling must be an object")
    _strict_keys(sampling, {"seed_connected_per_run", "background_fibers"}, "sampling")
    seed_sample = sampling.get("seed_connected_per_run", 8)
    background_sample = sampling.get("background_fibers", 8)
    if not isinstance(seed_sample, int) or seed_sample < 1:
        raise AcceptanceError("sampling.seed_connected_per_run must be a positive integer")
    if not isinstance(background_sample, int) or background_sample < 0:
        raise AcceptanceError("sampling.background_fibers must be a nonnegative integer")
    return AcceptanceFixture(
        target_atlas_root=_resolve_path(root, document.get("target_atlas_root"), "target_atlas_root"),
        seeds=tuple(seeds),
        connectome=_resolve_path(root, document.get("connectome"), "connectome"),
        config=resolve_config(document.get("config")),
        seed_connected_per_run=seed_sample,
        background_fibers=background_sample,
    )


def _source_snapshot(fixture: AcceptanceFixture) -> dict[str, tuple[int, int]]:
    paths = [fixture.connectome, *(seed.path for seed in fixture.seeds)]
    paths.extend(target.path for target in discover_targets(fixture.target_atlas_root))
    return {
        str(path): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(set(paths))
    }


def _sample_ids(
    results: Sequence[ConnectivityRunResult],
    n_all: int,
    per_seed: int,
    background_count: int,
) -> np.ndarray:
    selected: set[int] = set()
    for result in results:
        selected.update(int(value) for value in result.membership.seed_fiber_ids[:per_seed])
    if background_count:
        candidate_count = min(n_all, max(background_count * 16, 32))
        for candidate in np.unique(np.linspace(1, n_all, candidate_count, dtype=np.int64)):
            if int(candidate) not in selected:
                selected.add(int(candidate))
                background_count -= 1
                if background_count == 0:
                    break
        candidate = 1
        while background_count and candidate <= n_all:
            if candidate not in selected:
                selected.add(candidate)
                background_count -= 1
            candidate += 1
    return np.asarray(sorted(selected), dtype=np.int64)


def _sample_chunk(fiber_ids: np.ndarray, streamlines: Sequence[np.ndarray]) -> FiberChunk:
    lengths = np.asarray([streamline.shape[0] for streamline in streamlines], dtype=np.int64)
    offsets = np.empty(lengths.size + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(lengths, out=offsets[1:])
    points = np.concatenate(streamlines, axis=0).astype(np.float32, copy=False)
    return FiberChunk(fiber_ids=fiber_ids, point_offsets=offsets, points=points)


def _finite_metrics(results: Sequence[ConnectivityRunResult]) -> bool:
    for result in results:
        for row in result.statistics:
            values = [row.seed_normalized_fraction, row.target_background_prevalence]
            if row.connectivity_lift is not None:
                values.append(row.connectivity_lift)
            if row.connectivity_pmi is not None:
                values.append(row.connectivity_pmi)
            if not all(np.isfinite(value) for value in values):
                return False
    return True


def run_acceptance_fixture(
    fixture: AcceptanceFixture,
    output_root: Path | str,
) -> AcceptanceReport:
    """Run all fixture seeds through the generic public API and verify acceptance."""
    output = Path(output_root).expanduser().resolve()
    before = _source_snapshot(fixture)
    adapter = open_connectome(fixture.connectome)
    if not isinstance(adapter, LeadDBSHDF5Connectome):
        raise AcceptanceError("acceptance sampling requires the Lead-DBS HDF5 adapter")
    code_provenance = collect_code_provenance()
    first_results: list[ConnectivityRunResult] = []
    for seed in fixture.seeds:
        first_results.append(
            compute_seed_target_statistics(
                target_atlas_root=fixture.target_atlas_root,
                seed_roi=seed.path,
                connectome=adapter,
                config=fixture.config,
                output_root=output,
                code_provenance=code_provenance,
            )
        )
    repeated_results: list[ConnectivityRunResult] = []
    for seed in fixture.seeds:
        repeated_results.append(
            compute_seed_target_statistics(
                target_atlas_root=fixture.target_atlas_root,
                seed_roi=seed.path,
                connectome=adapter,
                config=fixture.config,
                output_root=output,
                code_provenance=code_provenance,
            )
        )

    target_count = len(first_results[0].statistics)
    if any(len(result.statistics) != target_count for result in first_results):
        raise AcceptanceError("acceptance runs produced inconsistent target row counts")
    sample_ids = _sample_ids(
        first_results,
        adapter.metadata.n_fibers,
        fixture.seed_connected_per_run,
        fixture.background_fibers,
    )
    sampled_streamlines = adapter.load_streamlines(sample_ids)
    masks = first_results[0].validation.atlas.targets
    reference = reference_membership(sampled_streamlines, masks)
    optimized = optimized_membership(
        _sample_chunk(sample_ids, sampled_streamlines),
        build_sparse_lookup(masks),
    )
    kernel_equivalence = bool(np.array_equal(reference, optimized))
    identical_hashes = all(
        first.artifacts.run_fingerprint == repeated.artifacts.run_fingerprint
        and dict(first.artifacts.artifact_hashes) == dict(repeated.artifacts.artifact_hashes)
        for first, repeated in zip(first_results, repeated_results)
    )
    deterministic_ranks = all(
        [row.rank for row in first.statistics] == [row.rank for row in repeated.statistics]
        for first, repeated in zip(first_results, repeated_results)
    )
    after = _source_snapshot(fixture)
    runs = tuple(
        AcceptanceRunEvidence(
            fixture_id=seed.fixture_id,
            run_dir=result.artifacts.run_dir,
            run_fingerprint=result.artifacts.run_fingerprint,
            n_seed_fibers=int(result.membership.seed_fiber_ids.size),
            target_cache_hit=result.membership.target_cache_hit,
            artifact_hashes=dict(result.artifacts.artifact_hashes),
        )
        for seed, result in zip(fixture.seeds, first_results)
    )
    report = AcceptanceReport(
        target_count=target_count,
        runs=runs,
        sampled_fiber_count=int(sample_ids.size),
        sampled_kernel_equivalence=kernel_equivalence,
        identical_rerun_hashes=identical_hashes,
        deterministic_ranks=deterministic_ranks,
        finite_valid_metrics=_finite_metrics(first_results),
        source_state_unchanged=before == after,
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "acceptance_report.json").write_text(
        json.dumps(report.as_mapping(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one explicit seed-target connectivity acceptance fixture.")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fixture = load_acceptance_fixture(args.fixture, args.repo_root)
    report = run_acceptance_fixture(fixture, args.output_root)
    print(json.dumps(report.as_mapping(), indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
