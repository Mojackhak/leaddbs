"""Project-neutral synthetic acceptance for the complete generic workflow."""

from __future__ import annotations

import copy
import csv
import hashlib
import importlib.abc
import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urlsplit

import h5py
import nibabel as nib
import numpy as np
import yaml

from dual_frequency.application.publication import CanonicalPublisher
from dual_frequency.application.service import (
    SensitivityExtensionRequest,
    WorkflowRequest,
    WorkflowService,
)
from dual_frequency.backends.sensitivity import (
    FinalSensitivityTarget,
    JitterReplicateEvidence,
    jitter_rebuild_identity,
)
from dual_frequency.cache import RunScopedArtifactPublisher
from dual_frequency.catalog import EndpointRecord, build_endpoint_catalog
from dual_frequency.config import WorkflowOverrides, load_workflow
from dual_frequency.contracts import (
    ActivationArtifact,
    ActivationRequest,
    ArtifactRef,
    AxisRef,
    BootstrapNuisanceEvidence,
    BootstrapRebuildProvenance,
    DeltaReferenceBundle,
    EndpointInputRecord,
    FeatureAxisRef,
    FinalModelRecord,
    FinalSelectionRecord,
    FormalRequest,
    FormalResult,
    HardComputabilityLimits,
    InSampleRequest,
    NormativeFiberScoreSettings,
    ObservedRequest,
    PreparedExposureRecord,
    PPAMObservedWorkspaceRecord,
    ReferenceDependencyRecord,
    SensitiveRecord,
    SourceGrid,
    SourceRecord,
    canonical_hash,
    load_study_base,
)
from dual_frequency.runtime.service_adapters import PRODUCTION_SERVICE_HANDLERS
from dual_frequency.runtime.ppam_observed_workspace import (
    ppam_observed_workspace_record,
    publish_ppam_nuisance_failure,
)
from dual_frequency.workflow import RegisteredService, ServiceRegistry
from dual_frequency.workflow.executor import ServiceResult, TaskExecutionRequest


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
PROFILE_ROOT = REPOSITORY_ROOT / "my_helper" / "stnsnr" / "config" / "four_model_v1"
PUBLICATION_TREE_FIXTURE = Path(__file__).with_name(
    "canonical_publication_tree_v1.json"
)
MODEL_FAMILIES = frozenset(
    {"reference_voxel", "addon_voxel", "reference_fiber", "addon_fiber"}
)
FINAL_DECISION_STATUSES = frozenset(
    {
        "realized_primary",
        "realized_fallback",
        "no_final_model",
        "dependency_failure",
        "execution_failure",
    }
)


def _is_blocked_project_namespace(fullname: str) -> bool:
    normalized = str(fullname).lower()
    return normalized == "projects.stnsnr" or normalized.startswith(
        ("projects.stnsnr.", "my_helper.fiber.projects.stnsnr")
    )


class _ProjectNamespaceBlocker(importlib.abc.MetaPathFinder):
    def __init__(self) -> None:
        self.attempted_imports: list[str] = []

    def find_spec(self, fullname, path=None, target=None):
        del path, target
        if _is_blocked_project_namespace(fullname):
            self.attempted_imports.append(fullname)
            raise ImportError(f"blocked project namespace import: {fullname}")
        return None


@contextmanager
def _blocked_project_namespace():
    blocker = _ProjectNamespaceBlocker()
    displaced = {
        name: module
        for name, module in tuple(sys.modules.items())
        if _is_blocked_project_namespace(name)
    }
    for name in displaced:
        del sys.modules[name]
    sys.meta_path.insert(0, blocker)
    try:
        yield blocker
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(displaced)


def _clinical_observation(
    subject_id: str,
    phase_id: str,
    program_id: int,
    value: float,
) -> dict[str, object]:
    return {
        "observation_id": (
            f"observation:{subject_id}:{phase_id}:{program_id}:response_scale:total"
        ),
        "scale_id": "response_scale",
        "subscale_id": "total",
        "value": int(round(value)),
        "status": "observed",
    }


def _stimulation_source(
    source_id: str,
    component_id: str,
    frequency_hz: float,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_label": (
            "Component Alpha"
            if component_id == "component_alpha"
            else "Component Beta"
        ),
        "component_id": component_id,
        "frequency_hz": frequency_hz,
        "control_mode": "voltage",
        "amplitude": 2.0,
        "pulse_width_us": 60.0,
        "contacts": [
            {"contact": 0, "polarity": "cathode", "fraction": 1.0},
            {"contact": "case", "polarity": "anode", "fraction": 1.0},
        ],
    }


def _program(
    subject_id: str,
    phase_id: str,
    program_id: int,
    condition_role: str,
    value: float,
    sources: tuple[dict[str, object], ...],
) -> dict[str, object]:
    groups = []
    for index, source in enumerate(sources, start=1):
        groups.append(
            {
                "frequency_group_id": f"frequency_group_{index}",
                "delivery_mode": "continuous",
                "sources": [source],
            }
        )
    electrode_programs = (
        []
        if not groups
        else [{"electrode_id": "lead-right", "frequency_groups": groups}]
    )
    return {
        "program_id": program_id,
        "program_label": f"Program {program_id}",
        "condition_role": condition_role,
        "stimulation_state": "none" if condition_role == "none" else "active",
        "assessment_order": program_id,
        "exposure": {
            "duration_label": "configured",
            "stimulation_start_date": None,
            "assessment_date": None,
            "exposure_days": None,
        },
        "clinical_observations": [
            _clinical_observation(subject_id, phase_id, program_id, value)
        ],
        "electrode_programs": electrode_programs,
    }


def _study_payload(root: Path, subject_count: int = 16) -> dict[str, object]:
    formal_path = (root / "formal_connectome.mat").resolve()
    sensitive_path = (root / "sensitive_connectome.mat").resolve()
    subjects = []
    for index in range(subject_count):
        subject_id = f"participant-{index + 1:02d}"
        baseline_value = 45.0 + 2.0 * np.cos(index * 1.1)
        reference_value = 60.0 + 3.0 * np.sin(index * 1.3)
        addon_value = 55.0 + 2.5 * np.cos(index * 0.9)
        subjects.append(
            {
                "subject_id": subject_id,
                "subject_label": f"Participant {index + 1:02d}",
                "subject_sources": {
                    "leaddbs_subject_dir": str(root / "subjects" / subject_id),
                    "electrode_reconstruction": {
                        "path": str(root / "subjects" / subject_id / "reconstruction.mat")
                    },
                },
                "contact_numbering": {
                    "convention": "bilateral_contiguous_zero_based",
                    "electrode_order": ["lead-right"],
                },
                "electrodes": [
                    {
                        "electrode_id": "lead-right",
                        "hemisphere": "R",
                        "electrode_model": "Synthetic Lead",
                        "contact_count": 4,
                        "reconstruction_lead_id": 1,
                    }
                ],
                "phases": [
                    {
                        "phase_id": "baseline_window",
                        "phase_label": "Baseline Window",
                        "date": {
                            "window_start_date": None,
                            "window_end_date": None,
                        },
                        "programs": [
                            _program(
                                subject_id,
                                "baseline_window",
                                101,
                                "none",
                                baseline_value,
                                (),
                            )
                        ],
                    },
                    {
                        "phase_id": "reference_window",
                        "phase_label": "Reference Window",
                        "date": {
                            "window_start_date": None,
                            "window_end_date": None,
                        },
                        "programs": [
                            _program(
                                subject_id,
                                "reference_window",
                                202,
                                "reference_only",
                                reference_value,
                                (
                                    _stimulation_source(
                                        "reference_source",
                                        "component_alpha",
                                        140.0,
                                    ),
                                ),
                            )
                        ],
                    },
                    {
                        "phase_id": "addon_window",
                        "phase_label": "Add-on Window",
                        "date": {
                            "window_start_date": None,
                            "window_end_date": None,
                        },
                        "programs": [
                            _program(
                                subject_id,
                                "addon_window",
                                303,
                                "combined",
                                addon_value,
                                (
                                    _stimulation_source(
                                        "reference_source",
                                        "component_alpha",
                                        140.0,
                                    ),
                                    _stimulation_source(
                                        "addon_source",
                                        "component_beta",
                                        30.0,
                                    ),
                                ),
                            )
                        ],
                    },
                ],
            }
        )
    return {
        "schema_version": "dual_frequency_study_v1",
        "study": {
            "study_id": "project_neutral_study",
            "study_label": "Project-neutral synthetic study",
            "data_version": "1",
            "stimulation_components": [
                {"component_id": "component_alpha", "label": "Component Alpha"},
                {"component_id": "component_beta", "label": "Component Beta"},
            ],
            "scale_definitions": [
                {
                    "scale_id": "response_scale",
                    "label": "Response Scale",
                    "value_type": "integer",
                    "unit": "score",
                    "direction": "lower",
                    "subscales": [{"subscale_id": "total", "label": "Total"}],
                }
            ],
            "spot_model_sources": {
                "canonical_space": "MNI152NLin2009bAsym",
                "hemisphere_mapping": {
                    "canonical_hemisphere": "R",
                    "left_to_right_transform": {"path": str(root / "flip.mat")},
                },
                "reference_images": [
                    {
                        "image_id": "reference_t1",
                        "modality": "T1w",
                        "label": "Reference T1",
                        "path": str(root / "reference_t1.nii.gz"),
                    },
                    {
                        "image_id": "reference_t2",
                        "modality": "T2w",
                        "label": "Reference T2",
                        "path": str(root / "reference_t2.nii.gz"),
                    },
                ],
                "brainmask": {
                    "brainmask_id": "synthetic_brainmask",
                    "space": "MNI152NLin2009bAsym",
                    "path": str(root / "brainmask.nii.gz"),
                },
                "connectomes": [
                    {
                        "connectome_id": "formal_connectome",
                        "label": "Formal Connectome",
                        "space": "MNI152NLin2009bAsym",
                        "modality": "diffusion",
                        "representation": "streamlines",
                        "streamlines": {
                            "format": "leaddbs_data_mat_v7_3",
                            "path": str(formal_path),
                        },
                        "metadata": {"path": None},
                    },
                    {
                        "connectome_id": "sensitive_connectome",
                        "label": "Sensitive Connectome",
                        "space": "MNI152NLin2009bAsym",
                        "modality": "diffusion",
                        "representation": "streamlines",
                        "streamlines": {
                            "format": "leaddbs_data_mat_v7_3",
                            "path": str(sensitive_path),
                        },
                        "metadata": {"path": None},
                    },
                ],
            },
            "subjects": subjects,
            "provenance": {
                "created_at": "2026-07-15T00:00:00Z",
                "importer": {
                    "name": "project_neutral_synthetic_fixture",
                    "version": "1",
                    "code_commit": None,
                },
                "source_files": [
                    {
                        "role": "synthetic_clinical_fixture",
                        "path": str(root / "synthetic_clinical.json"),
                    },
                    {
                        "role": "synthetic_stimulation_fixture",
                        "path": str(root / "synthetic_stimulation.json"),
                    },
                ],
                "notes": None,
            },
        },
    }


def _write_profiles(root: Path) -> WorkflowRequest:
    direct = yaml.safe_load(
        (PROFILE_ROOT / "direct_voxel_model_test.yaml").read_text(encoding="utf-8")
    )
    fiber = yaml.safe_load(
        (PROFILE_ROOT / "normative_fiber_model_test.yaml").read_text(encoding="utf-8")
    )
    workflow = yaml.safe_load(
        (PROFILE_ROOT / "workflow.yaml").read_text(encoding="utf-8")
    )
    endpoint_pair = {
        "baseline": {"phase_id": "baseline_window", "program_id": 101},
        "reference": {"phase_id": "reference_window", "program_id": 202},
        "addon": {"phase_id": "addon_window", "program_id": 303},
    }
    for profile in (direct, fiber):
        profile["model_set_id"] = "project_neutral_synthetic_e2e_v1"
        profile["output"]["root"] = str(root / "outputs")
        profile["scales"] = ["response_scale"]
        profile["endpoint_pair"] = copy.deepcopy(endpoint_pair)
    direct["shared"]["formal_resampling"]["permutation_resamples"] = 2
    direct["shared"]["formal_resampling"]["bootstrap_resamples"] = 2
    direct["shared"]["formal_resampling"]["jitter_resamples"] = 1
    fiber["formal_resampling"]["permutation_resamples"] = 2
    fiber["formal_resampling"]["bootstrap_resamples"] = 2
    fiber["formal_resampling"]["jitter_resamples"] = 1

    fiber["connectomes"]["entries"] = [
        {
            "connectome_id": "formal_connectome",
            "label": "Formal Connectome",
            "path": str((root / "formal_connectome.mat").resolve()),
            "role": "formal",
            "fold_candidate_fibers_min": 1,
        },
        {
            "connectome_id": "sensitive_connectome",
            "label": "Sensitive Connectome",
            "path": str((root / "sensitive_connectome.mat").resolve()),
            "role": "sensitive",
            "fold_candidate_fibers_min": 1,
        },
    ]
    fiber["source"] = {
        "pre_specified": {"tau_v_per_m": 200, "coverage_subjects_min": 5},
        "scan": {
            "tau_v_per_m": [180, 200, 220],
            "coverage_subjects_min": [5, 6],
        },
        "minimum_adjacent_passing_cells": 2,
    }
    fiber["score"] = {
        "sweet_fraction": 0.25,
        "sour_fraction": 0.25,
        "weighted_peak_fraction": 0.25,
        "sweet_selected_min_count": 4,
        "sour_selected_min_count": 3,
        "weighted_peak_min_count": 2,
    }
    fiber["sensitivity"]["high_threshold"] = {
        "tau_v_per_m": 220,
        "coverage_subjects_min": 5,
    }
    fiber["sensitivity"]["fixed_outer_library"] = {
        "sweet_count": 8,
        "sour_count": 4,
    }
    fiber["oss"]["permutation_resamples"] = 2

    direct_path = root / "direct_voxel_model.yaml"
    fiber_path = root / "normative_fiber_model.yaml"
    workflow_path = root / "workflow.yaml"
    study_path = root / "study_base.json"
    direct_path.write_text(yaml.safe_dump(direct, sort_keys=False), encoding="utf-8")
    fiber_path.write_text(yaml.safe_dump(fiber, sort_keys=False), encoding="utf-8")
    workflow["model_profiles"] = {
        "direct_voxel": direct_path.name,
        "normative_fiber": fiber_path.name,
    }
    workflow["selection"] = {"models": ["all"], "connectomes": ["all"]}
    workflow["execution"].update(
        {
            "through": "report",
            "resume": False,
            "force": False,
            "continue_on_endpoint_failure": True,
            "allow_expensive_producers": False,
            "workers": 3,
        }
    )
    workflow["storage"] = {
        "cache_root": str(root / "cache"),
        "run_root": str(root / "runs"),
    }
    workflow_path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    study_path.write_text(
        json.dumps(_study_payload(root), sort_keys=False),
        encoding="utf-8",
    )
    return WorkflowRequest(
        study_base=study_path,
        direct_voxel_model=direct_path,
        normative_fiber_model=fiber_path,
        workflow_profile=workflow_path,
        overrides=WorkflowOverrides(all_available=True, through="report"),
    )


def _write_publication_assets(root: Path, study_path: Path) -> None:
    shape = (4, 4, 4)
    affine = np.eye(4, dtype=np.float64)
    for name in ("brainmask.nii.gz", "reference_t1.nii.gz", "reference_t2.nii.gz"):
        nib.save(
            nib.Nifti1Image(np.ones(shape, dtype=np.float32), affine),
            root / name,
        )
    transform_path = root / "flip.tfm"
    transform_path.write_text(
        "#Insight Transform File V1.0\n"
        "# Transform 0\n"
        "Transform: AffineTransform_double_3_3\n"
        "Parameters: 1 0 0 0 1 0 0 0 1 0 0 0\n"
        "FixedParameters: 0 0 0\n",
        encoding="utf-8",
    )
    study = json.loads(study_path.read_text(encoding="utf-8"))
    study["study"]["spot_model_sources"]["hemisphere_mapping"][
        "left_to_right_transform"
    ]["path"] = str(transform_path)
    study_path.write_text(
        json.dumps(study, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    fiber_count = 20_064
    lengths = np.full(fiber_count, 2, dtype=np.float64)
    fiber_ids = np.repeat(np.arange(1, fiber_count + 1, dtype=np.float32), 2)
    position = np.repeat(np.arange(fiber_count, dtype=np.float32), 2)
    coordinates = np.column_stack(
        (
            np.mod(position, 4.0),
            np.mod(np.floor(position / 4.0), 4.0),
            np.mod(np.floor(position / 16.0), 4.0),
        )
    ).astype(np.float32)
    coordinates[1::2, 0] += 0.25
    for name in ("formal_connectome.mat", "sensitive_connectome.mat"):
        with h5py.File(root / name, "w") as handle:
            handle.create_dataset("idx", data=lengths.reshape(1, -1))
            handle.create_dataset(
                "fibers",
                data=np.vstack((coordinates.T, fiber_ids.reshape(1, -1))),
            )


def _publication_files(root: Path) -> tuple[str, ...]:
    return tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and not path.name.startswith("._")
        )
    )


def _publication_tree_sha256(files: tuple[str, ...]) -> str:
    return hashlib.sha256(("\n".join(files) + "\n").encode("utf-8")).hexdigest()


def _publication_index(
    root: Path,
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    with (root / "artifact_index.csv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle)
        rows = tuple(reader)
        fields = tuple(reader.fieldnames or ())
    return fields, rows


def _artifact_array(artifact: ArtifactRef) -> np.ndarray:
    parsed = urlsplit(artifact.uri)
    if parsed.scheme != "file":
        raise AssertionError("synthetic artifacts must use file URIs")
    return np.load(Path(unquote(parsed.path)), allow_pickle=False)


class _SyntheticRuntimeProvider:
    """Deterministic arrays for all generic observed, formal, and jitter paths."""

    def __init__(self, configuration, catalog: tuple[EndpointRecord, ...], root: Path):
        self.configuration = configuration
        self._endpoints = {endpoint.endpoint_id: endpoint for endpoint in catalog}
        self._root = root
        self._subject_ids = tuple(f"participant-{index + 1:02d}" for index in range(16))
        self._latent_reference = np.linspace(-1.5, 1.5, len(self._subject_ids))
        self._latent_addon = np.sin(
            np.linspace(0.0, 2.6 * np.pi, len(self._subject_ids))
        )
        index = np.arange(len(self._subject_ids), dtype=np.float64)
        self._baseline = 45.0 + 2.0 * np.cos(index * 1.1)
        self._reference_outcome = (
            60.0 - 8.0 * self._latent_reference + 0.3 * self._baseline
            + 0.1 * np.sin(index * 2.2)
        )
        self._addon_outcome = (
            52.0 - 7.0 * self._latent_addon + 0.35 * self._reference_outcome
            + 0.1 * np.cos(index * 1.7)
        )

    def endpoint(self, endpoint_id: str) -> EndpointRecord:
        return self._endpoints[endpoint_id]

    @staticmethod
    def _domain(endpoint: EndpointRecord) -> str:
        if endpoint.key.model_family.endswith("voxel"):
            return "voxel"
        return f"fiber:{endpoint.key.connectome_id}"

    def _feature_values(self, endpoint: EndpointRecord) -> tuple[AxisRef, np.ndarray]:
        count = 56
        domain = self._domain(endpoint)
        offset = {
            "voxel": 0,
            "fiber:formal_connectome": 10_000,
            "fiber:sensitive_connectome": 20_000,
        }[domain]
        values = np.arange(offset, offset + count, dtype=np.int64)
        axis = AxisRef(
            f"synthetic_features:{domain}",
            count,
            canonical_hash({"domain": domain, "values": values.tolist()}),
        )
        return axis, values

    def _exposure_arrays(
        self,
        endpoint: EndpointRecord,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        count = 56
        subject = np.arange(len(self._subject_ids), dtype=np.float64)[:, None]
        feature = np.arange(count, dtype=np.float64)[None, :]
        reference = np.full((len(self._subject_ids), count), 40.0, dtype=np.float64)
        addon = np.full_like(reference, 35.0)
        reference_component = np.full_like(reference, 40.0)
        reference_loadings = np.linspace(0.8, 1.2, 24)
        addon_loadings = np.linspace(1.2, 0.8, 24)
        reference[:, :24] = (
            260.0
            + 20.0
            * self._latent_reference[:, None]
            * reference_loadings[None, :]
            + 0.25 * np.sin((subject + 1.0) * (feature[:, :24] + 1.0))
        )
        reference_component[:, :24] = (
            reference[:, :24]
            + 8.0 * self._latent_addon[:, None] * reference_loadings[None, :]
        )
        addon[:, 24:48] = (
            260.0
            + 22.0
            * self._latent_addon[:, None]
            * addon_loadings[None, :]
            + 0.25 * np.cos((subject + 1.0) * (feature[:, 24:48] + 1.0))
        )
        reference[:, 48:] += 2.0 * np.cos(
            (subject + 1.0) * (feature[:, 48:] + 1.0)
        )
        addon[:, 48:] += 2.0 * np.sin(
            (subject + 1.0) * (feature[:, 48:] + 1.0)
        )
        if endpoint.connectome_role == "sensitive":
            reference *= 0.98
            addon *= 0.98
            reference_component *= 0.98
        return reference, addon, reference_component

    def publish_endpoint_input(
        self,
        endpoint_id: str,
        publisher,
    ) -> EndpointInputRecord:
        endpoint = self.endpoint(endpoint_id)
        subject_axis = AxisRef(
            f"subjects:{endpoint.key.scale_id}",
            len(self._subject_ids),
            canonical_hash({"subjects": self._subject_ids}),
        )
        if endpoint.key.model_family.startswith("reference_"):
            baseline = self._baseline
            outcome = self._reference_outcome
        else:
            baseline = self._reference_outcome
            outcome = self._addon_outcome
        return EndpointInputRecord(
            endpoint=endpoint.key,
            readiness_status="ready",
            candidate_subject_ids=self._subject_ids,
            included_subject_ids=self._subject_ids,
            exclusions=(),
            minimum_subjects=endpoint.minimum_subjects,
            subject_axis=subject_axis,
            baseline=publisher.array(
                "baseline.npy",
                baseline,
                kind="synthetic_baseline",
                axes=(subject_axis,),
                units="score",
                space=None,
            ),
            outcome=publisher.array(
                "outcome.npy",
                outcome,
                kind="synthetic_outcome",
                axes=(subject_axis,),
                units="score",
                space=None,
            ),
        )

    @staticmethod
    def _reference_tau(record: SourceRecord | SensitiveRecord) -> float:
        if isinstance(record, SourceRecord):
            if record.selected_tau is None:
                raise AssertionError("accepted reference source has no tau")
            return record.selected_tau
        return record.evaluated_tau

    def publish_prepared_exposure(
        self,
        endpoint_input: EndpointInputRecord,
        reference_dependency: ReferenceDependencyRecord | None,
        publisher,
    ) -> PreparedExposureRecord:
        endpoint = self.endpoint(endpoint_input.endpoint.identifier)
        if endpoint_input.subject_axis is None:
            raise AssertionError("ready endpoint input has no subject axis")
        feature_axis, feature_ids = self._feature_values(endpoint)
        reference, addon, reference_component = self._exposure_arrays(endpoint)
        feature_id_ref = publisher.array(
            "feature_ids.npy",
            feature_ids,
            kind="synthetic_feature_ids",
            axes=(feature_axis,),
            units=None,
            space="synthetic_canonical_space",
        )
        if endpoint.key.model_family.startswith("reference_"):
            exposure = publisher.array(
                "reference_exposure.npy",
                reference,
                kind="synthetic_reference_exposure",
                axes=(endpoint_input.subject_axis, feature_axis),
                units="V/m",
                space="synthetic_canonical_space",
            )
            return PreparedExposureRecord(
                endpoint=endpoint.key,
                subject_axis=endpoint_input.subject_axis,
                feature_axis=feature_axis,
                exposure=exposure,
                feature_ids=feature_id_ref,
                delta_reference_input_status="not_applicable",
                delta_reference_reason_code="not_applicable",
                auxiliary_readiness=None,
                reference_condition_exposure=None,
                addon_reference_component_exposure=None,
                reference_overlap_mask=None,
                total_exposure=None,
            )

        if reference_dependency is None or reference_dependency.reference_record is None:
            raise AssertionError("add-on preparation requires reference evidence")
        tau = self._reference_tau(reference_dependency.reference_record)
        overlap = reference_component >= tau
        overlap_excluded = np.where(overlap, 0.0, addon)
        axes = (endpoint_input.subject_axis, feature_axis)
        return PreparedExposureRecord(
            endpoint=endpoint.key,
            subject_axis=endpoint_input.subject_axis,
            feature_axis=feature_axis,
            exposure=publisher.array(
                "addon_exposure.npy",
                overlap_excluded,
                kind="synthetic_addon_overlap_excluded_exposure",
                axes=axes,
                units="V/m",
                space="synthetic_canonical_space",
            ),
            feature_ids=feature_id_ref,
            delta_reference_input_status="ready",
            delta_reference_reason_code="ready",
            auxiliary_readiness=publisher.document(
                "auxiliary_readiness.json",
                {"technical_status": "ready"},
                kind="synthetic_auxiliary_readiness",
            ),
            reference_condition_exposure=publisher.array(
                "reference_condition_exposure.npy",
                reference,
                kind="synthetic_reference_condition_exposure",
                axes=axes,
                units="V/m",
                space="synthetic_canonical_space",
            ),
            addon_reference_component_exposure=publisher.array(
                "addon_reference_component_exposure.npy",
                reference_component,
                kind="synthetic_addon_reference_component_exposure",
                axes=axes,
                units="V/m",
                space="synthetic_canonical_space",
            ),
            reference_overlap_mask=publisher.array(
                "reference_overlap_mask.npy",
                overlap,
                kind="synthetic_reference_overlap_mask",
                axes=axes,
                units="binary",
                space="synthetic_canonical_space",
            ),
            total_exposure=publisher.array(
                "total_exposure.npy",
                np.maximum(addon, reference_component),
                kind="raw_addon_component_exposure",
                axes=axes,
                units="V/m",
                space="synthetic_canonical_space",
            ),
        )

    def _source_grid(self, endpoint: EndpointRecord) -> SourceGrid:
        profile = (
            self.configuration.normative_fiber.source
            if endpoint.key.model_family.endswith("fiber")
            else self.configuration.direct_voxel.source
        )
        return SourceGrid(
            profile.pre_specified.tau,
            profile.pre_specified.coverage,
            profile.tau_values,
            profile.coverage_values,
            profile.minimum_adjacent_passing_cells,
        )

    def _hard_limits(self, endpoint: EndpointRecord) -> HardComputabilityLimits:
        if endpoint.key.model_family.endswith("fiber"):
            profile = self.configuration.normative_fiber.hard_computability
            fold_minimum = next(
                item.fold_candidate_fibers_min
                for item in self.configuration.normative_fiber.connectomes
                if item.connectome_id == endpoint.key.connectome_id
            )
            return HardComputabilityLimits(
                profile.n_subjects_min,
                None,
                fold_minimum,
            )
        profile = self.configuration.direct_voxel.hard_computability
        return HardComputabilityLimits(
            profile.n_subjects_min,
            profile.n_features_full_min,
            profile.fold_n_features_min,
        )

    def _score_settings(
        self,
        endpoint: EndpointRecord,
    ) -> NormativeFiberScoreSettings | None:
        if not endpoint.key.model_family.endswith("fiber"):
            return None
        score = self.configuration.normative_fiber.score
        return NormativeFiberScoreSettings(
            score.sweet_fraction,
            score.sour_fraction,
            score.weighted_peak_fraction,
            score.sweet_selected_min_count,
            score.sour_selected_min_count,
            score.weighted_peak_min_count,
        )

    def observed_request(
        self,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        *,
        branch: str,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> ObservedRequest:
        endpoint = self.endpoint(endpoint_input.endpoint.identifier)
        if endpoint_input.subject_axis is None:
            raise AssertionError("ready endpoint input has no subject axis")
        nuisance: tuple[ArtifactRef, ...] = ()
        if branch == "delta_reference_adjusted":
            if delta_reference is None or not delta_reference.valid:
                raise AssertionError("adjusted branch requires valid DeltaReferenceScore")
            if delta_reference.full_scores is None or delta_reference.fold_scores is None:
                raise AssertionError("valid DeltaReferenceScore is incomplete")
            nuisance = (delta_reference.full_scores, delta_reference.fold_scores)
        return ObservedRequest(
            endpoint=endpoint.key,
            branch=branch,
            exposure=prepared.exposure,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            nuisance_inputs=nuisance,
            subject_axis=endpoint_input.subject_axis,
            feature_axis=prepared.feature_axis,
            source_grid=self._source_grid(endpoint),
            exposure_units="V/m",
            exposure_space="synthetic_canonical_space",
            outcome_direction=endpoint.scale_direction,
            hard_computability=self._hard_limits(endpoint),
            connectome_role=endpoint.connectome_role,
            feature_ids=(
                prepared.feature_ids
                if endpoint.key.model_family.endswith("fiber")
                else None
            ),
            fiber_score_settings=self._score_settings(endpoint),
        )

    @staticmethod
    def _selected_source(final_model: FinalModelRecord) -> SourceRecord:
        source = final_model.selected_source
        if source is None and final_model.selected_branch is not None:
            source = final_model.selected_branch.source
        if source is None:
            raise AssertionError("realized final has no selected source")
        return source

    def selected_exposure(
        self,
        final_model: FinalModelRecord,
        prepared: PreparedExposureRecord,
        publisher,
    ) -> tuple[ArtifactRef, ArtifactRef | None]:
        source = self._selected_source(final_model)
        if source.feature_axis is None:
            raise AssertionError("selected source has no feature axis")
        parent_exposure = _artifact_array(prepared.exposure)
        parent_ids = _artifact_array(prepared.feature_ids).astype(np.int64, copy=False)
        if final_model.endpoint.model_family.endswith("voxel"):
            selected = next(
                item
                for item in source.artifacts
                if item.kind == "selected_feature_indices"
            )
            indices = _artifact_array(selected).astype(np.int64, copy=False)
            selected_ids = None
        else:
            selected_ids = next(
                item
                for item in source.artifacts
                if item.kind == "normative_fiber_valid_union_ids"
            )
            values = _artifact_array(selected_ids).astype(np.int64, copy=False)
            indices = np.searchsorted(parent_ids, values)
            if np.any(indices >= parent_ids.size) or not np.array_equal(
                parent_ids[indices], values
            ):
                raise AssertionError("selected fibers are outside the parent axis")
        exposure = publisher.array(
            "selected_exposure.npy",
            parent_exposure[:, indices],
            kind="synthetic_selected_exposure",
            axes=(prepared.subject_axis, source.feature_axis.axis),
            units="V/m",
            space="synthetic_canonical_space",
        )
        return exposure, selected_ids

    def formal_request(
        self,
        final_model: FinalModelRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        publisher,
        *,
        resampling_kind: str,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> FormalRequest:
        endpoint = self.endpoint(final_model.endpoint.identifier)
        if endpoint_input.subject_axis is None:
            raise AssertionError("formal endpoint input has no subject axis")
        exposure, selected_ids = self.selected_exposure(
            final_model,
            prepared,
            publisher,
        )
        adjusted = (
            final_model.final_key is not None
            and final_model.final_key.final_branch == "delta_reference_adjusted"
        )
        if adjusted and (delta_reference is None or not delta_reference.valid):
            raise AssertionError("adjusted formal request has no DeltaReferenceScore")
        profile = (
            self.configuration.normative_fiber.formal_resampling
            if endpoint.key.model_family.endswith("fiber")
            else self.configuration.direct_voxel.formal_resampling
        )
        return FormalRequest(
            final_model=final_model,
            resampling_kind=resampling_kind,
            exposure=exposure,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            delta_reference_full=(
                delta_reference.full_scores
                if adjusted and delta_reference is not None
                else None
            ),
            delta_reference_folds=(
                delta_reference.fold_scores
                if adjusted and delta_reference is not None
                else None
            ),
            subject_axis=endpoint_input.subject_axis,
            feature_axis=final_model.valid_feature_axis.axis,
            exposure_units="V/m",
            exposure_space="synthetic_canonical_space",
            outcome_direction=endpoint.scale_direction,
            hard_computability=self._hard_limits(endpoint),
            connectome_role=endpoint.connectome_role,
            feature_ids=selected_ids,
            fiber_score_settings=self._score_settings(endpoint),
            resamples=(
                profile.permutation_resamples
                if resampling_kind == "permutation"
                else profile.bootstrap_resamples
            ),
            seed=profile.seed,
        )

    def in_sample_request(
        self,
        final_model: FinalModelRecord,
        endpoint_input: EndpointInputRecord,
        prepared: PreparedExposureRecord,
        loocv_formal_result: FormalResult,
        *,
        delta_reference: DeltaReferenceBundle | None = None,
    ) -> InSampleRequest:
        endpoint = self.endpoint(final_model.endpoint.identifier)
        source = self._selected_source(final_model)
        is_fiber = endpoint.key.model_family.endswith("fiber")
        prediction_kind = (
            "normative_fiber_loocv_model_predictions"
            if is_fiber
            else "loocv_model_predictions"
        )
        baseline_kind = (
            "normative_fiber_loocv_baseline_predictions"
            if is_fiber
            else "loocv_baseline_predictions"
        )

        def artifact(artifacts: tuple[ArtifactRef, ...], kind: str) -> ArtifactRef:
            matches = tuple(item for item in artifacts if item.kind == kind)
            if len(matches) != 1:
                raise AssertionError(f"synthetic in-sample request lacks {kind}")
            return matches[0]

        if endpoint_input.subject_axis is None:
            raise AssertionError("in-sample endpoint input has no subject axis")
        adjusted = (
            final_model.final_key is not None
            and final_model.final_key.final_branch == "delta_reference_adjusted"
        )
        if adjusted and (delta_reference is None or not delta_reference.valid):
            raise AssertionError("adjusted in-sample request has no DeltaReferenceScore")
        profile = (
            self.configuration.normative_fiber.formal_resampling
            if is_fiber
            else self.configuration.direct_voxel.formal_resampling
        )
        return InSampleRequest(
            final_model=final_model,
            exposure=prepared.exposure,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            delta_reference_full=(
                delta_reference.full_scores
                if adjusted and delta_reference is not None
                else None
            ),
            subject_axis=endpoint_input.subject_axis,
            feature_axis=prepared.feature_axis,
            feature_ids=prepared.feature_ids,
            loocv_predictions=artifact(source.artifacts, prediction_kind),
            loocv_baseline_predictions=artifact(source.artifacts, baseline_kind),
            loocv_permutation_summary=artifact(
                loocv_formal_result.artifacts,
                "formal_permutation_summary",
            ),
            exposure_units="V/m",
            exposure_space="synthetic_canonical_space",
            outcome_direction=endpoint.scale_direction,
            hard_computability=self._hard_limits(endpoint),
            connectome_role=endpoint.connectome_role,
            fiber_score_settings=self._score_settings(endpoint),
            resamples=profile.permutation_resamples,
            seed=profile.seed,
        )

    def build_bootstrap_nuisance(
        self,
        request: FormalRequest,
        sample_indices: np.ndarray,
    ) -> BootstrapNuisanceEvidence:
        sample = np.asarray(sample_indices, dtype=np.int64)
        count = sample.size
        positions = np.arange(count, dtype=np.float64)
        token = float(np.dot(sample + 1, np.arange(1, count + 1)))
        full = (
            np.linspace(-1.0, 1.0, count)
            + 0.01 * np.sin((positions + 1.0) * (token + 1.0))
        )
        folds = np.vstack(
            [
                full
                + 0.01
                * np.cos((heldout + 1.0) * (positions + 1.0) + token)
                for heldout in range(count)
            ]
        )
        provenance = BootstrapRebuildProvenance.from_rebuild(
            provider_id="project_neutral_synthetic_provider",
            provider_version="1",
            final_model_id=request.final_model.identifier,
            subject_axis=request.subject_axis,
            sample_indices=sample,
            delta_reference_full_scores=full,
            delta_reference_fold_scores=folds,
        )
        return BootstrapNuisanceEvidence(
            sample_indices=sample,
            delta_reference_full_scores=full,
            delta_reference_fold_scores=folds,
            support_status="adequate",
            support_qc=(("median_out_support_fraction", 0.1),),
            rebuild_provenance=provenance,
        )

    def build_replicate(
        self,
        target: FinalSensitivityTarget,
        *,
        replicate_index: int,
        replicate_seed: int,
    ) -> JitterReplicateEvidence:
        original = target.observed_request
        publisher = RunScopedArtifactPublisher(
            self._root
            / "outputs"
            / "jitter_inputs"
            / target.final_model.identifier
            / f"replicate-{replicate_index}",
            "project_neutral_synthetic_jitter",
            "1",
        )
        exposure = _artifact_array(original.exposure)
        perturbation = 0.02 * np.sin(
            np.arange(exposure.size, dtype=np.float64).reshape(exposure.shape)
            + float(replicate_seed % 997)
        )
        jittered_exposure = publisher.array(
            "jittered_exposure.npy",
            exposure + perturbation,
            kind="synthetic_jittered_exposure",
            axes=(original.subject_axis, original.feature_axis),
            units=original.exposure_units,
            space=original.exposure_space,
        )
        rebuilt = replace(original, exposure=jittered_exposure)
        overlap_ref = None
        support_status = "not_applicable"
        support_qc: tuple[tuple[str, float | int | str | bool], ...] = ()
        delta_identity = None
        if target.final_model.endpoint.model_family.startswith("addon_"):
            if target.reference_overlap_mask is None:
                raise AssertionError("add-on jitter target has no overlap mask")
            overlap = _artifact_array(target.reference_overlap_mask).astype(bool, copy=True)
            overlap[replicate_index % overlap.shape[0], -1] = ~overlap[
                replicate_index % overlap.shape[0], -1
            ]
            overlap_ref = publisher.array(
                "jittered_reference_overlap.npy",
                overlap,
                kind="synthetic_jittered_reference_overlap",
                axes=(original.subject_axis, original.feature_axis),
                units="binary",
                space=original.exposure_space,
            )
            support_status = "adequate"
            support_qc = (("median_out_support_fraction", 0.1),)
            if original.branch == "delta_reference_adjusted":
                full = _artifact_array(original.nuisance_inputs[0])
                folds = _artifact_array(original.nuisance_inputs[1])
                nuisance = (
                    publisher.array(
                        "jittered_delta_full.npy",
                        full + 0.01 * np.sin(np.arange(full.size) + replicate_seed),
                        kind="synthetic_jittered_delta_full",
                        axes=(original.subject_axis,),
                        units=original.nuisance_inputs[0].units,
                        space=original.nuisance_inputs[0].space,
                    ),
                    publisher.array(
                        "jittered_delta_folds.npy",
                        folds
                        + 0.01
                        * np.cos(
                            np.arange(folds.size).reshape(folds.shape)
                            + replicate_seed
                        ),
                        kind="synthetic_jittered_delta_folds",
                        axes=(original.subject_axis, original.subject_axis),
                        units=original.nuisance_inputs[1].units,
                        space=original.nuisance_inputs[1].space,
                    ),
                )
                rebuilt = replace(rebuilt, nuisance_inputs=nuisance)
        rebuild_identity = jitter_rebuild_identity(
            target,
            observed_request=rebuilt,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            reference_overlap_mask=overlap_ref,
            support_status=support_status,
            support_qc=support_qc,
        )
        if rebuilt.branch == "delta_reference_adjusted":
            delta_identity = jitter_rebuild_identity(
                target,
                observed_request=rebuilt,
                replicate_index=replicate_index,
                replicate_seed=replicate_seed,
                reference_overlap_mask=overlap_ref,
                support_status=support_status,
                support_qc=support_qc,
                component="delta_reference",
            )
        return JitterReplicateEvidence(
            observed_request=rebuilt,
            replicate_index=replicate_index,
            replicate_seed=replicate_seed,
            rebuild_identity=rebuild_identity,
            reference_overlap_mask=overlap_ref,
            support_status=support_status,
            support_qc=support_qc,
            delta_rebuild_identity=delta_identity,
        )


class _PublicationFixtureRuntimeProvider(_SyntheticRuntimeProvider):
    """Exercise both-sign and single-sign canonical fiber publication."""

    def _exposure_arrays(
        self,
        endpoint: EndpointRecord,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        reference, addon, reference_component = super()._exposure_arrays(endpoint)
        reference[:, 12:24] = 520.0 - reference[:, 12:24]
        reference_component[:, 12:24] = 520.0 - reference_component[:, 12:24]
        addon[:, 36:48] = 520.0 - addon[:, 36:48]
        return reference, addon, reference_component


class _FakeActivationBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, request: TaskExecutionRequest) -> ServiceResult:
        if request.task.service_id == "prepare_ppam_observed_workspace":
            return self._observed_workspace(request)
        selection = next(
            state.record
            for state in request.dependencies.values()
            if isinstance(state.record, FinalSelectionRecord)
        )
        endpoint_input = next(
            state.record
            for state in request.dependencies.values()
            if isinstance(state.record, EndpointInputRecord)
            and state.record.endpoint == selection.endpoint
        )
        if selection.final_model is None or endpoint_input.subject_axis is None:
            raise AssertionError("activation requires a realized final and subject axis")
        final_model = selection.final_model
        feature_axis = final_model.valid_feature_axis.axis
        subject_axis = endpoint_input.subject_axis
        feature = np.arange(feature_axis.count, dtype=np.float32)[None, :]
        subject = np.arange(subject_axis.count, dtype=np.float32)[:, None]
        probability = ((subject + 2.0 * feature) % 10.0) / 10.0
        probability = probability.astype(np.float32, copy=False)
        binary = probability >= 0.5
        publisher = RunScopedArtifactPublisher(
            request.output_dir,
            request.task.task_id,
            "synthetic_activation_v1",
        )
        probability_ref = publisher.array(
            "activation_probability.npy",
            probability,
            kind="synthetic_activation_probability",
            axes=(subject_axis, feature_axis),
            units="probability",
            space="synthetic_canonical_space",
        )
        binary_ref = publisher.array(
            "binary_activation.npy",
            binary,
            kind="synthetic_binary_activation",
            axes=(subject_axis, feature_axis),
            units="binary",
            space="synthetic_canonical_space",
        )
        status = publisher.document(
            "activation_status.json",
            {
                "technical_status": "completed",
                "backend": "project_neutral_fake_activation",
                "classification_feedback": False,
            },
            kind="synthetic_activation_status",
        )
        self.calls.append(request.task.endpoint_id)
        return ServiceResult.from_record(
            ActivationArtifact(
                final_model_id=final_model.identifier,
                feature_axis=feature_axis,
                activation_probability=probability_ref,
                binary_exposure=binary_ref,
                artifacts=(status,),
            )
        )

    @staticmethod
    def _observed_workspace(request: TaskExecutionRequest) -> ServiceResult:
        selection = next(
            state.record
            for state in request.dependencies.values()
            if isinstance(state.record, FinalSelectionRecord)
        )
        endpoint_input = next(
            state.record
            for state in request.dependencies.values()
            if isinstance(state.record, EndpointInputRecord)
            and state.record.endpoint == selection.endpoint
        )
        if selection.final_model is None or endpoint_input.subject_axis is None:
            raise AssertionError("pPAM workspace requires a realized final")
        final_model = selection.final_model
        subject_axis = endpoint_input.subject_axis
        feature_axis = final_model.valid_feature_axis.axis
        publisher = RunScopedArtifactPublisher(
            request.output_dir,
            request.task.task_id,
            "synthetic_ppam_observed_v1",
        )
        probability = publisher.array(
            "activation_probability.npy",
            np.zeros(
                (subject_axis.count, feature_axis.count),
                dtype=np.float32,
            ),
            kind="synthetic_activation_probability",
            axes=(subject_axis, feature_axis),
            units="probability",
            space="right_canonical",
        )
        binary = publisher.array(
            "binary_activation.npy",
            np.zeros(
                (subject_axis.count, feature_axis.count),
                dtype=np.float32,
            ),
            kind="synthetic_binary_activation",
            axes=(subject_axis, feature_axis),
            units="binary",
            space="right_canonical",
        )
        peak = publisher.array(
            "peak_final_score.npy",
            np.zeros(subject_axis.count, dtype=np.float64),
            kind="synthetic_peak_final_score",
            axes=(subject_axis,),
            units="score",
            space=None,
        )
        feature_ids = publisher.array(
            "feature_ids.npy",
            np.arange(feature_axis.count, dtype=np.int64),
            kind="synthetic_fiber_ids",
            axes=(feature_axis,),
            units="fiber_id",
            space="right_canonical",
        )
        overlap = None
        if final_model.endpoint.model_family == "addon_fiber":
            overlap = publisher.array(
                "reference_overlap.npy",
                np.zeros(
                    (subject_axis.count, feature_axis.count),
                    dtype=bool,
                ),
                kind="synthetic_reference_overlap",
                axes=(subject_axis, feature_axis),
                units="binary",
                space="right_canonical",
            )
        nuisance: tuple[ArtifactRef, ...] = ()
        if final_model.final_key.final_branch == "delta_reference_adjusted":
            nuisance = (
                publisher.array(
                    "delta_full.npy",
                    np.zeros(subject_axis.count, dtype=np.float64),
                    kind="synthetic_delta_full",
                    axes=(subject_axis,),
                    units="score",
                    space=None,
                ),
                publisher.array(
                    "delta_folds.npy",
                    np.zeros(
                        (subject_axis.count, subject_axis.count),
                        dtype=np.float64,
                    ),
                    kind="synthetic_delta_folds",
                    axes=(subject_axis, subject_axis),
                    units="score",
                    space=None,
                ),
            )
        activation_request = ActivationRequest(
            final_model=final_model,
            activation_probability=probability,
            reference_overlap_mask=overlap,
            outcome=endpoint_input.outcome,
            baseline=endpoint_input.baseline,
            peak_final_score=peak,
            nuisance_inputs=nuisance,
            subject_axis=subject_axis,
            feature_axis=feature_axis,
            feature_ids=feature_ids,
            activation_feature_ids=feature_ids,
            outcome_direction="lower",
            hard_computability=HardComputabilityLimits(1, None, 1),
            connectome_role="formal",
            fiber_score_settings=NormativeFiberScoreSettings(
                sweet_fraction=0.1,
                sour_fraction=0.1,
                weighted_peak_fraction=0.1,
                sweet_selected_min_count=1,
                sour_selected_min_count=1,
                weighted_peak_min_count=1,
            ),
            fitting_probability_threshold=0.5,
            permutation_resamples=1,
            seed=1,
        )
        observed_artifacts = publish_ppam_nuisance_failure(
            activation_request,
            "synthetic_nuisance_not_estimable",
            "synthetic acceptance bypasses physical OSS fitting",
            publisher,
        )
        record = ppam_observed_workspace_record(
            activation_request,
            binary,
            observed_artifacts,
            "nuisance_not_estimable",
            request.output_dir,
            None,
        )
        if not isinstance(record, PPAMObservedWorkspaceRecord):
            raise AssertionError("synthetic pPAM workspace record is invalid")
        return ServiceResult.from_record(
            record,
            facts={"ppam_permutation_ready": False},
        )


def _registry_with_fake_activation(
    fake_activation: _FakeActivationBackend,
    service_calls: dict[str, int] | None = None,
) -> ServiceRegistry:
    activation_services = {
        "prepare_ppam_observed_workspace",
        "aggregate_ppam_activation",
        "run_reference_fiber_activation",
        "run_addon_fiber_activation",
    }
    registered = []
    for service_id, handler in PRODUCTION_SERVICE_HANDLERS:
        selected = fake_activation if service_id in activation_services else handler
        if service_calls is not None:
            def counted(request, *, _handler=selected, _service_id=service_id):
                service_calls[_service_id] = service_calls.get(_service_id, 0) + 1
                return _handler(request)

            selected = counted
        registered.append(RegisteredService(service_id, selected))
    return ServiceRegistry(registered)


class SyntheticEndToEndTest(unittest.TestCase):
    def test_missing_parent_rebuild_creates_a_new_lineage_before_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            complete_request = _write_profiles(root)
            rebuild_request = WorkflowRequest(
                study_base=complete_request.study_base,
                direct_voxel_model=complete_request.direct_voxel_model,
                normative_fiber_model=complete_request.normative_fiber_model,
                workflow_profile=complete_request.workflow_profile,
                overrides=WorkflowOverrides(all_available=True, through="observed"),
            )
            configuration = load_workflow(
                rebuild_request.workflow_profile,
                rebuild_request.overrides,
            )
            study = load_study_base(rebuild_request.study_base)
            catalog = build_endpoint_catalog(configuration, study)
            service = WorkflowService(
                registry=_registry_with_fake_activation(_FakeActivationBackend()),
                provider=_SyntheticRuntimeProvider(configuration, catalog, root),
            )
            result = service.sensitivity(
                SensitivityExtensionRequest(
                    base_run=root / "runs" / "project_neutral_study" / "deleted-parent",
                    analyses=("jitter",),
                    run_id="rebuilt-jitter-extension",
                    workers=2,
                    rebuild_request=rebuild_request,
                    rebuild_run_id="rebuilt-parent",
                )
            )
            parent_root = root / "runs" / "project_neutral_study" / "rebuilt-parent"
            extension_root = (
                root / "runs" / "project_neutral_study" / "rebuilt-jitter-extension"
            )
            parent_manifest = json.loads(
                (parent_root / "run_manifest.json").read_text(encoding="utf-8")
            )
            extension_manifest = json.loads(
                (extension_root / "run_manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(parent_manifest["final_status"], "completed")
        self.assertEqual(extension_manifest["parent_run_id"], "rebuilt-parent")
        self.assertEqual(extension_manifest["run_type"], "sensitivity_extension")

    def test_observed_parent_runs_jitter_and_oss_as_independent_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            complete_request = _write_profiles(root)
            main_request = WorkflowRequest(
                study_base=complete_request.study_base,
                direct_voxel_model=complete_request.direct_voxel_model,
                normative_fiber_model=complete_request.normative_fiber_model,
                workflow_profile=complete_request.workflow_profile,
                overrides=WorkflowOverrides(all_available=True, through="observed"),
            )
            configuration = load_workflow(main_request.workflow_profile, main_request.overrides)
            study = load_study_base(main_request.study_base)
            catalog = build_endpoint_catalog(configuration, study)
            provider = _SyntheticRuntimeProvider(configuration, catalog, root)
            fake_activation = _FakeActivationBackend()
            service_calls: dict[str, int] = {}
            service = WorkflowService(
                registry=_registry_with_fake_activation(fake_activation, service_calls),
                provider=provider,
            )
            main_result = service.run(main_request, run_id="checkpoint-parent")
            parent_root = root / "runs" / "project_neutral_study" / "checkpoint-parent"
            parent_manifest_before = hashlib.sha256(
                (parent_root / "run_manifest.json").read_bytes()
            ).hexdigest()
            parent_observed_states = {
                path.name: path.read_text(encoding="utf-8")
                for path in (parent_root / "tasks").glob("*.json")
            }

            service_calls.clear()
            jitter = service.sensitivity(
                SensitivityExtensionRequest(
                    base_run=parent_root,
                    analyses=("jitter",),
                    run_id="jitter-extension",
                    workers=2,
                )
            )
            jitter_calls = dict(service_calls)
            calls_after_jitter = len(fake_activation.calls)
            service_calls.clear()
            oss = service.sensitivity(
                SensitivityExtensionRequest(
                    base_run=parent_root,
                    analyses=("oss",),
                    run_id="oss-extension",
                    workers=2,
                    allow_expensive_producers=True,
                )
            )
            oss_calls = dict(service_calls)
            service_calls.clear()
            combined = service.sensitivity(
                SensitivityExtensionRequest(
                    base_run=parent_root,
                    analyses=("jitter", "oss"),
                    run_id="combined-extension",
                    workers=2,
                    allow_expensive_producers=True,
                )
            )
            combined_calls = dict(service_calls)
            parent_manifest_after = hashlib.sha256(
                (parent_root / "run_manifest.json").read_bytes()
            ).hexdigest()
            jitter_root = root / "runs" / "project_neutral_study" / "jitter-extension"
            oss_root = root / "runs" / "project_neutral_study" / "oss-extension"
            combined_root = (
                root / "runs" / "project_neutral_study" / "combined-extension"
            )
            jitter_states = {
                path.name: path.read_text(encoding="utf-8")
                for path in (jitter_root / "tasks").glob("*.json")
            }
            restored_parent_states = {
                name: jitter_states[name]
                for name in parent_observed_states
                if name in jitter_states
            }
            output_flags = {
                "jitter_reference": (jitter_root / "base_run_reference.json").is_file(),
                "jitter_tasks": (jitter_root / "task_status.csv").is_file(),
                "oss_artifacts": (oss_root / "artifact_index.csv").is_file(),
                "jitter_canonical": (
                    root
                    / "outputs"
                    / "direct_voxel"
                    / "project_neutral_synthetic_e2e_v1"
                    / "extensions"
                    / "jitter-extension"
                    / "extension_manifest.json"
                ).is_file(),
                "oss_canonical": (
                    root
                    / "outputs"
                    / "normative_fiber"
                    / "project_neutral_synthetic_e2e_v1"
                    / "extensions"
                    / "oss-extension"
                    / "extension_manifest.json"
                ).is_file(),
                "combined_plan": (combined_root / "sensitivity_plan.json").is_file(),
            }
            extension_plans = {
                name: json.loads((path / "sensitivity_plan.json").read_text())
                for name, path in {
                    "jitter": jitter_root,
                    "oss": oss_root,
                    "combined": combined_root,
                }.items()
            }

        self.assertEqual(main_result.exit_code, 0)
        self.assertEqual(jitter.exit_code, 0)
        self.assertEqual(oss.exit_code, 0)
        self.assertEqual(combined.exit_code, 0)
        self.assertEqual(calls_after_jitter, 0)
        self.assertEqual(len(fake_activation.calls), 4)
        self.assertTrue(jitter_calls)
        self.assertTrue(oss_calls)
        self.assertTrue(combined_calls)
        self.assertTrue(all(service_id.endswith("_jitter") for service_id in jitter_calls))
        self.assertEqual(
            set(oss_calls),
            {
                "prepare_ppam_observed_workspace",
                "aggregate_ppam_activation",
            },
        )
        self.assertEqual(set(combined_calls), set(jitter_calls) | set(oss_calls))
        for document in extension_plans.values():
            tasks = document["plan"]["tasks"]
            self.assertFalse(any(task["phase"] == "formal" for task in tasks))
            checkpoint_roots = [task for task in tasks if task["checkpoint_only"]]
            self.assertTrue(checkpoint_roots)
            self.assertTrue(
                all(not task["dependencies"] and not task["gates"] for task in checkpoint_roots)
            )
            self.assertTrue(
                all(
                    task["phase"] == "sensitivity" or task["checkpoint_only"]
                    for task in tasks
                )
            )
            self.assertFalse(
                any(
                    gate["fact"] == "formal_complete"
                    for task in tasks
                    for gate in task["gates"]
                )
            )
        self.assertEqual(parent_manifest_before, parent_manifest_after)
        self.assertTrue(restored_parent_states)
        self.assertTrue(
            all(
                content == parent_observed_states[name]
                for name, content in restored_parent_states.items()
            )
        )
        self.assertTrue(all(output_flags.values()), output_flags)

    def test_extension_resume_executes_only_the_noncompleted_sensitivity_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            complete_request = _write_profiles(root)
            main_request = WorkflowRequest(
                study_base=complete_request.study_base,
                direct_voxel_model=complete_request.direct_voxel_model,
                normative_fiber_model=complete_request.normative_fiber_model,
                workflow_profile=complete_request.workflow_profile,
                overrides=WorkflowOverrides(all_available=True, through="observed"),
            )
            configuration = load_workflow(
                main_request.workflow_profile,
                main_request.overrides,
            )
            study = load_study_base(main_request.study_base)
            catalog = build_endpoint_catalog(configuration, study)
            service_calls: dict[str, int] = {}
            service = WorkflowService(
                registry=_registry_with_fake_activation(
                    _FakeActivationBackend(),
                    service_calls,
                ),
                provider=_SyntheticRuntimeProvider(configuration, catalog, root),
            )
            main = service.run(main_request, run_id="resume-parent")
            parent_root = root / "runs" / "project_neutral_study" / "resume-parent"
            extension_request = SensitivityExtensionRequest(
                base_run=parent_root,
                analyses=("jitter",),
                run_id="resume-extension",
                workers=2,
            )
            first = service.sensitivity(extension_request)
            extension_root = (
                root / "runs" / "project_neutral_study" / "resume-extension"
            )
            jitter_states = []
            for path in sorted((extension_root / "tasks").glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                if str(payload["service_id"]).endswith("_jitter"):
                    jitter_states.append((path, payload))
            interrupted_path, interrupted = jitter_states[0]
            interrupted["status"] = "running"
            interrupted["reason"] = "interrupted_for_resume_test"
            interrupted_path.write_text(
                json.dumps(interrupted, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            service_calls.clear()
            resumed = service.sensitivity(
                replace(extension_request, workers=3, resume=True)
            )
            final_states = [
                json.loads(path.read_text(encoding="utf-8"))
                for path, _payload in jitter_states
            ]

        self.assertEqual(main.exit_code, 0)
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(
            resumed.exit_code,
            0,
            [outcome.as_dict() for outcome in resumed.outcomes if outcome.status == "failed"],
        )
        self.assertEqual(sum(service_calls.values()), 1)
        self.assertTrue(all(key.endswith("_jitter") for key in service_calls))
        self.assertTrue(all(payload["status"] == "completed" for payload in final_states))

    def test_formal_permutation_resume_reruns_only_one_block_and_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            request = _write_profiles(root)
            direct_profile = yaml.safe_load(
                request.direct_voxel_model.read_text(encoding="utf-8")
            )
            direct_profile["shared"]["formal_resampling"][
                "permutation_resamples"
            ] = 251
            request.direct_voxel_model.write_text(
                yaml.safe_dump(direct_profile, sort_keys=False),
                encoding="utf-8",
            )
            configuration = load_workflow(
                request.workflow_profile,
                request.overrides,
            )
            study = load_study_base(request.study_base)
            catalog = build_endpoint_catalog(configuration, study)
            service_calls: dict[str, int] = {}
            service = WorkflowService(
                registry=_registry_with_fake_activation(
                    _FakeActivationBackend(),
                    service_calls,
                ),
                provider=_SyntheticRuntimeProvider(configuration, catalog, root),
            )
            plan = service.plan(request).plan
            endpoint_id = next(
                task.endpoint_id
                for task in plan.tasks
                if task.model_family == "reference_voxel"
                and task.stage == "formal_permutation"
            )
            blocks = tuple(
                task
                for task in plan.tasks
                if task.endpoint_id == endpoint_id
                and task.stage.startswith("formal_permutation_block_")
            )
            aggregate = next(
                task
                for task in plan.tasks
                if task.endpoint_id == endpoint_id
                and task.stage == "formal_permutation"
            )
            first = service.run(request, run_id="formal-block-resume")
            run_root = (
                root
                / "runs"
                / "project_neutral_study"
                / "formal-block-resume"
            )
            interrupted_block = blocks[0]
            attempt_snapshots: dict[str, dict[str, bytes]] = {}
            first_attempts: dict[str, Path] = {}
            for task in (interrupted_block, aggregate):
                attempts = tuple(
                    sorted((run_root / "work" / task.task_id).glob("attempt-*"))
                )
                self.assertEqual(len(attempts), 1)
                first_attempts[task.task_id] = attempts[0]
                attempt_snapshots[task.task_id] = {
                    path.relative_to(attempts[0]).as_posix(): path.read_bytes()
                    for path in attempts[0].rglob("*")
                    if path.is_file()
                }
                state_path = run_root / "tasks" / f"{task.task_id}.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state.update(
                    {
                        "status": "running",
                        "reason": "interrupted_for_block_resume_test",
                        "finished_at": None,
                        "result": None,
                    }
                )
                state_path.write_text(
                    json.dumps(state, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

            service_calls.clear()
            resumed = service.run(
                replace(
                    request,
                    overrides=replace(request.overrides, resume=True),
                ),
                run_id="formal-block-resume",
            )
            resumed_attempt_counts = {
                task.task_id: len(
                    tuple(
                        (run_root / "work" / task.task_id).glob("attempt-*")
                    )
                )
                for task in (interrupted_block, aggregate)
            }
            retained_snapshots = {
                task_id: {
                    path.relative_to(attempt).as_posix(): path.read_bytes()
                    for path in attempt.rglob("*")
                    if path.is_file()
                }
                for task_id, attempt in first_attempts.items()
            }

        self.assertEqual(len(blocks), 2)
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(
            resumed.exit_code,
            0,
            [
                outcome.as_dict()
                for outcome in resumed.outcomes
                if outcome.status == "failed"
            ],
        )
        self.assertEqual(
            service_calls,
            {
                "run_formal_permutation_block": 1,
                "aggregate_formal_permutation": 1,
            },
        )
        self.assertEqual(
            resumed_attempt_counts,
            {interrupted_block.task_id: 2, aggregate.task_id: 2},
        )
        self.assertEqual(attempt_snapshots, retained_snapshots)

    def test_formal_bootstrap_resume_reruns_only_one_block_and_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            request = _write_profiles(root)
            direct_profile = yaml.safe_load(
                request.direct_voxel_model.read_text(encoding="utf-8")
            )
            direct_profile["shared"]["formal_resampling"][
                "bootstrap_resamples"
            ] = 251
            request.direct_voxel_model.write_text(
                yaml.safe_dump(direct_profile, sort_keys=False),
                encoding="utf-8",
            )
            configuration = load_workflow(
                request.workflow_profile,
                request.overrides,
            )
            study = load_study_base(request.study_base)
            catalog = build_endpoint_catalog(configuration, study)
            service_calls: dict[str, int] = {}
            service = WorkflowService(
                registry=_registry_with_fake_activation(
                    _FakeActivationBackend(),
                    service_calls,
                ),
                provider=_SyntheticRuntimeProvider(configuration, catalog, root),
            )
            plan = service.plan(request).plan
            endpoint_id = next(
                task.endpoint_id
                for task in plan.tasks
                if task.model_family == "reference_voxel"
                and task.stage == "formal_bootstrap"
            )
            blocks = tuple(
                task
                for task in plan.tasks
                if task.endpoint_id == endpoint_id
                and task.stage.startswith("formal_bootstrap_block_")
            )
            aggregate = next(
                task
                for task in plan.tasks
                if task.endpoint_id == endpoint_id
                and task.stage == "formal_bootstrap"
            )
            first = service.run(request, run_id="bootstrap-block-resume")
            run_root = (
                root
                / "runs"
                / "project_neutral_study"
                / "bootstrap-block-resume"
            )
            interrupted_block = blocks[0]
            attempt_snapshots: dict[str, dict[str, bytes]] = {}
            first_attempts: dict[str, Path] = {}
            for task in (interrupted_block, aggregate):
                attempts = tuple(
                    sorted((run_root / "work" / task.task_id).glob("attempt-*"))
                )
                self.assertEqual(len(attempts), 1)
                first_attempts[task.task_id] = attempts[0]
                attempt_snapshots[task.task_id] = {
                    path.relative_to(attempts[0]).as_posix(): path.read_bytes()
                    for path in attempts[0].rglob("*")
                    if path.is_file()
                }
                state_path = run_root / "tasks" / f"{task.task_id}.json"
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state.update(
                    {
                        "status": "running",
                        "reason": "interrupted_for_bootstrap_resume_test",
                        "finished_at": None,
                        "result": None,
                    }
                )
                state_path.write_text(
                    json.dumps(state, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

            service_calls.clear()
            resumed = service.run(
                replace(
                    request,
                    overrides=replace(request.overrides, resume=True),
                ),
                run_id="bootstrap-block-resume",
            )
            resumed_attempt_counts = {
                task.task_id: len(
                    tuple(
                        (run_root / "work" / task.task_id).glob("attempt-*")
                    )
                )
                for task in (interrupted_block, aggregate)
            }
            retained_snapshots = {
                task_id: {
                    path.relative_to(attempt).as_posix(): path.read_bytes()
                    for path in attempt.rglob("*")
                    if path.is_file()
                }
                for task_id, attempt in first_attempts.items()
            }

        self.assertEqual(len(blocks), 2)
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(
            resumed.exit_code,
            0,
            [
                outcome.as_dict()
                for outcome in resumed.outcomes
                if outcome.status == "failed"
            ],
        )
        self.assertEqual(
            service_calls,
            {
                "run_formal_bootstrap_block": 1,
                "aggregate_formal_bootstrap": 1,
            },
        )
        self.assertEqual(
            resumed_attempt_counts,
            {interrupted_block.task_id: 2, aggregate.task_id: 2},
        )
        self.assertEqual(attempt_snapshots, retained_snapshots)

    def test_all_four_families_complete_through_report_without_project_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            request = _write_profiles(root)
            _write_publication_assets(root, request.study_base)
            configuration = load_workflow(request.workflow_profile, request.overrides)
            study = load_study_base(request.study_base)
            catalog = build_endpoint_catalog(configuration, study)
            provider = _PublicationFixtureRuntimeProvider(
                configuration,
                catalog,
                root,
            )
            fake_activation = _FakeActivationBackend()
            service = WorkflowService(
                registry=_registry_with_fake_activation(fake_activation),
                provider=provider,
            )
            planned_model_families = {
                task.model_family for task in service.plan(request).plan.tasks
            }
            run_root = (
                root
                / "runs"
                / "project_neutral_study"
                / "project-neutral-synthetic-e2e"
            )
            with _blocked_project_namespace() as blocker:
                result = service.run(request, run_id="project-neutral-synthetic-e2e")
                publication = CanonicalPublisher().publish(run_root)

            expected_publication = json.loads(
                PUBLICATION_TREE_FIXTURE.read_text(encoding="utf-8")
            )
            direct_files = _publication_files(publication.direct_voxel_root)
            fiber_files = _publication_files(publication.normative_fiber_root)
            direct_index_fields, direct_index_rows = _publication_index(
                publication.direct_voxel_root
            )
            fiber_index_fields, fiber_index_rows = _publication_index(
                publication.normative_fiber_root
            )
            missing_sign_path = (
                publication.normative_fiber_root
                / "response_scale"
                / "addon"
                / "report"
                / "negative_weighted_density.nii.gz"
            )
            missing_sign_values = nib.load(str(missing_sign_path)).get_fdata()
            missing_sign_finite = missing_sign_values[np.isfinite(missing_sign_values)]
            missing_sign_metadata = json.loads(
                Path(f"{missing_sign_path}.metadata.json").read_text(encoding="utf-8")
            )["provenance"]
            final_decisions = json.loads(
                (run_root / "final_decisions.json").read_text(encoding="utf-8")
            )
            endpoint_summary = json.loads(
                (run_root / "endpoint_summary.json").read_text(encoding="utf-8")
            )
            run_report = json.loads(
                (run_root / "run_report.json").read_text(encoding="utf-8")
            )
            run_manifest = json.loads(
                (run_root / "run_manifest.json").read_text(encoding="utf-8")
            )
            resolved_configuration = yaml.safe_load(
                (run_root / "configuration_resolved.yaml").read_text(
                    encoding="utf-8"
                )
            )
            configuration_sources = json.loads(
                (run_root / "configuration_sources.json").read_text(
                    encoding="utf-8"
                )
            )
            artifact_index = json.loads(
                (run_root / "artifact_index.json").read_text(encoding="utf-8")
            )
            sensitivity_index = json.loads(
                (run_root / "sensitivity_bases" / "index.json").read_text(
                    encoding="utf-8"
                )
            )
            sensitivity_bases = tuple(
                json.loads(
                    (
                        run_root
                        / "sensitivity_bases"
                        / item["relative_path"]
                    ).read_text(encoding="utf-8")
                )
                for item in sensitivity_index["bases"]
            )
            task_states = tuple(
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_root / "tasks").glob("*.json"))
            )
            source_hashes_match = True
            for source in configuration_sources["sources"]:
                parsed = urlsplit(source["uri"])
                source_path = Path(unquote(parsed.path))
                source_hashes_match &= (
                    hashlib.sha256(source_path.read_bytes()).hexdigest()
                    == source["sha256"]
                )
            reloaded_configuration = load_workflow(
                request.workflow_profile,
                request.overrides,
            )
            noncompleted_tasks = tuple(
                outcome.as_dict()
                for outcome in result.outcomes
                if outcome.status != "completed"
            )

        self.assertEqual(result.exit_code, 0, noncompleted_tasks)
        self.assertEqual(blocker.attempted_imports, [])
        self.assertEqual(planned_model_families, MODEL_FAMILIES)
        self.assertEqual(len(fake_activation.calls), 2)
        self.assertEqual(run_manifest["final_status"], "completed")
        self.assertEqual(
            publication.direct_voxel_artifact_count,
            expected_publication["direct_voxel"]["artifact_count"],
        )
        self.assertEqual(
            publication.normative_fiber_artifact_count,
            expected_publication["normative_fiber"]["artifact_count"],
        )
        self.assertEqual(
            len(direct_files),
            expected_publication["direct_voxel"]["file_count"],
        )
        self.assertEqual(
            len(fiber_files),
            expected_publication["normative_fiber"]["file_count"],
        )
        self.assertEqual(
            _publication_tree_sha256(direct_files),
            expected_publication["direct_voxel"]["file_tree_sha256"],
        )
        self.assertEqual(
            _publication_tree_sha256(fiber_files),
            expected_publication["normative_fiber"]["file_tree_sha256"],
        )
        self.assertEqual(
            direct_index_fields,
            tuple(expected_publication["direct_voxel"]["index_fields"]),
        )
        self.assertEqual(
            fiber_index_fields,
            tuple(expected_publication["normative_fiber"]["index_fields"]),
        )
        self.assertEqual(
            len(direct_index_rows),
            publication.direct_voxel_artifact_count,
        )
        self.assertEqual(
            len(fiber_index_rows),
            publication.normative_fiber_artifact_count,
        )
        self.assertTrue(
            all(
                row["relative_path"]
                and row["sha256"]
                and row["size_bytes"]
                and row["stage"]
                and "model_family" in row
                and "branch_id" in row
                and row["status"] == "completed"
                for row in (*direct_index_rows, *fiber_index_rows)
            )
        )
        self.assertGreater(missing_sign_finite.size, 0)
        np.testing.assert_array_equal(
            missing_sign_finite,
            np.zeros_like(missing_sign_finite),
        )
        self.assertEqual(missing_sign_metadata["sour_selected_fiber_count"], 0)
        self.assertIsNone(missing_sign_metadata["sour_selected_ids_sha256"])
        self.assertGreater(missing_sign_metadata["sweet_selected_fiber_count"], 0)
        self.assertEqual(
            run_manifest["configuration_hash"],
            configuration.configuration_hash,
        )
        self.assertEqual(
            run_manifest["scientific_configuration_hash"],
            configuration.scientific_configuration_hash,
        )
        self.assertEqual(
            resolved_configuration["configuration_hash"],
            configuration.configuration_hash,
        )
        self.assertEqual(
            resolved_configuration["scientific_configuration_hash"],
            configuration.scientific_configuration_hash,
        )
        self.assertEqual(
            reloaded_configuration.configuration_hash,
            configuration.configuration_hash,
        )
        self.assertEqual(
            reloaded_configuration.scientific_configuration_hash,
            configuration.scientific_configuration_hash,
        )
        self.assertEqual(len(configuration_sources["sources"]), 4)
        self.assertTrue(source_hashes_match)
        self.assertGreater(len(sensitivity_bases), 1)
        self.assertTrue(
            all(
                base["configuration_source_identities"]
                == configuration_sources["sources"]
                for base in sensitivity_bases
            )
        )
        self.assertEqual(len(task_states), len(result.outcomes))
        self.assertTrue(task_states)
        self.assertTrue(
            all(
                row["status"] == "completed"
                or (
                    row["status"] == "skipped"
                    and row["service_id"]
                    in {
                        "prepare_ppam_permutation_schedule",
                        "run_ppam_permutation_block",
                    }
                    and row["reason"] == "not_run_ppam_permutation_not_ready"
                )
                for row in task_states
            )
        )
        self.assertEqual(run_report["technical_status"], "completed")
        self.assertTrue(artifact_index["artifacts"])
        self.assertEqual(
            len(endpoint_summary["endpoints"]),
            len(catalog),
        )

        catalog_by_id = {endpoint.endpoint_id: endpoint for endpoint in catalog}
        decisions = final_decisions["decisions"]
        self.assertEqual(len(decisions), len(catalog))
        self.assertEqual(
            len({decision["endpoint_id"] for decision in decisions}),
            len(decisions),
        )
        for decision in decisions:
            endpoint = catalog_by_id[decision["endpoint_id"]]
            self.assertIn(decision["decision_status"], FINAL_DECISION_STATUSES)
            if endpoint.connectome_role == "sensitive":
                self.assertEqual(decision["decision_status"], "no_final_model")
                self.assertIsNone(decision["final_model_id"])
                self.assertIsNone(decision["final_model_record_id"])
                continue
            if (
                endpoint.key.model_family.endswith("voxel")
                or endpoint.connectome_role == "formal"
            ):
                has_final = decision["final_model_id"] is not None
                is_closed = decision["decision_status"] in {
                    "no_final_model",
                    "dependency_failure",
                    "execution_failure",
                }
                self.assertNotEqual(has_final, is_closed)
                if has_final:
                    self.assertIn(
                        decision["decision_status"],
                        {"realized_primary", "realized_fallback"},
                    )


if __name__ == "__main__":
    unittest.main()
