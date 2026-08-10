"""Lightweight MDS-UPDRS III/IV smoke test for the generic runtime."""

from __future__ import annotations

import importlib.abc
import copy
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import yaml

from dual_frequency.application.service import WorkflowRequest, WorkflowService
from dual_frequency.cache import ArtifactStore, RunScopedArtifactPublisher
from dual_frequency.config import WorkflowOverrides
from dual_frequency.contracts import EndpointInputRecord
from dual_frequency.runtime.input_provider import MatlabLeftToCanonicalTransformer
from dual_frequency.runtime.oss_toolchain import LeadDBSOSSProducerToolchain


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CONFIG_ROOT = REPOSITORY_ROOT / "my_helper" / "stnsnr" / "config" / "four_model_v1"
STUDY_BASE = Path("/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json")
DIRECT_PROFILE = CONFIG_ROOT / "direct_voxel_model_test.yaml"
FIBER_PROFILE = CONFIG_ROOT / "normative_fiber_model_test.yaml"
INDIVIDUALIZED_PROFILE = CONFIG_ROOT / "individualized_seed_target_model.yaml"
WORKFLOW_PROFILE = CONFIG_ROOT / "workflow.yaml"
EXPECTED_SCALES = ("mds_updrs_iii_score", "mds_updrs_iv")


def _is_project_namespace(module_name: str) -> bool:
    normalized = str(module_name).lower()
    return normalized == "projects.stnsnr" or normalized.startswith(
        ("projects.stnsnr.", "my_helper.fiber.projects.stnsnr")
    )


class _ProjectNamespaceBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if _is_project_namespace(fullname):
            raise ImportError(f"blocked project namespace import: {fullname}")
        return None


@contextmanager
def _blocked_project_namespace():
    preserved = {
        name: module
        for name, module in tuple(sys.modules.items())
        if _is_project_namespace(name)
    }
    for name in preserved:
        del sys.modules[name]
    blocker = _ProjectNamespaceBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)
        for name in tuple(sys.modules):
            if _is_project_namespace(name):
                del sys.modules[name]
        sys.modules.update(preserved)


def _workflow_request(root: Path) -> WorkflowRequest:
    workflow = yaml.safe_load(WORKFLOW_PROFILE.read_text(encoding="utf-8"))
    direct = yaml.safe_load(DIRECT_PROFILE.read_text(encoding="utf-8"))
    individualized = yaml.safe_load(
        INDIVIDUALIZED_PROFILE.read_text(encoding="utf-8")
    )
    individualized["scales"] = direct["scales"]
    individualized["endpoint_pair"] = copy.deepcopy(direct["endpoint_pair"])
    individualized_path = root / "individualized.yaml"
    individualized_path.write_text(
        yaml.safe_dump(individualized, sort_keys=False),
        encoding="utf-8",
    )
    workflow["model_profiles"] = {
        "direct_voxel": str(DIRECT_PROFILE),
        "normative_fiber": str(FIBER_PROFILE),
        "individualized_seed_target": str(individualized_path),
    }
    workflow["execution"]["through"] = "report"
    workflow["execution"]["allow_expensive_producers"] = False
    workflow["execution"]["workers"] = 1
    workflow["storage"]["run_root"] = str(root / "runs")
    workflow_path = root / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(workflow, sort_keys=False),
        encoding="utf-8",
    )
    return WorkflowRequest(
        study_base=STUDY_BASE,
        direct_voxel_model=DIRECT_PROFILE,
        normative_fiber_model=FIBER_PROFILE,
        workflow_profile=workflow_path,
        overrides=WorkflowOverrides(
            all_available=True,
            through="report",
            allow_expensive_producers=False,
            workers=1,
        ),
    )


def _task_signature(task, task_index):
    dependencies = tuple(
        sorted(
            (
                task_index[dependency].model_family,
                task_index[dependency].connectome_role,
                task_index[dependency].stage,
            )
            for dependency in task.dependencies
        )
    )
    return (
        task.model_family,
        task.connectome_role,
        task.stage,
        task.round_id,
        task.phase,
        task.service_id,
        task.key.branch,
        task.output_record_type,
        tuple((gate.fact, gate.false_status) for gate in task.gates),
        dependencies,
        task.expensive_producer,
        task.cache_first_expensive,
    )


class TwoScaleSmokeTest(unittest.TestCase):
    def test_mds_updrs_iii_and_iv_use_the_same_catalog_and_dag_path(self) -> None:
        required_inputs = (
            STUDY_BASE,
            DIRECT_PROFILE,
            FIBER_PROFILE,
            INDIVIDUALIZED_PROFILE,
            WORKFLOW_PROFILE,
        )
        missing = tuple(path for path in required_inputs if not path.is_file())
        if missing:
            self.skipTest(f"STNSNr smoke inputs are unavailable: {missing}")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory).resolve()
            request = _workflow_request(root)
            with (
                _blocked_project_namespace(),
                patch.object(
                    LeadDBSOSSProducerToolchain,
                    "produce",
                    side_effect=AssertionError(
                        "two-scale smoke must not run an expensive OSS producer"
                    ),
                ) as producer,
                patch.object(
                    MatlabLeftToCanonicalTransformer,
                    "transform",
                    side_effect=AssertionError(
                        "two-scale smoke must not generate transformed E-field caches"
                    ),
                ) as transformer,
            ):
                service = WorkflowService()
                bundle = service.plan(request)
                validated = bundle.validated
                configuration = validated.configuration

                self.assertEqual(configuration.selected_scales, EXPECTED_SCALES)
                self.assertEqual(validated.request.study_base, STUDY_BASE.resolve())
                self.assertEqual(
                    validated.request.direct_voxel_model,
                    DIRECT_PROFILE.resolve(),
                )
                self.assertEqual(
                    validated.request.normative_fiber_model,
                    FIBER_PROFILE.resolve(),
                )
                self.assertFalse(
                    configuration.workflow.execution.allow_expensive_producers
                )

                direct_resampling = configuration.direct_voxel.formal_resampling
                fiber_resampling = configuration.normative_fiber.formal_resampling
                self.assertEqual(
                    (
                        direct_resampling.permutation_resamples,
                        direct_resampling.bootstrap_resamples,
                        direct_resampling.jitter_resamples,
                    ),
                    (5, 5, 2),
                )
                self.assertEqual(
                    (
                        fiber_resampling.permutation_resamples,
                        fiber_resampling.bootstrap_resamples,
                        fiber_resampling.jitter_resamples,
                    ),
                    (5, 5, 2),
                )

                study_subject_ids = tuple(
                    subject.subject_id for subject in validated.study.subjects
                )
                study_subject_set = set(study_subject_ids)
                catalog_by_scale = {
                    scale_id: tuple(
                        endpoint
                        for endpoint in validated.catalog
                        if endpoint.key.scale_id == scale_id
                    )
                    for scale_id in EXPECTED_SCALES
                }
                self.assertTrue(study_subject_ids)
                self.assertTrue(all(catalog_by_scale.values()))
                for endpoints in catalog_by_scale.values():
                    for endpoint in endpoints:
                        self.assertTrue(set(endpoint.subject_ids) <= study_subject_set)

                def catalog_signature(endpoint):
                    return (
                        endpoint.key.model_family,
                        endpoint.key.connectome_id,
                        endpoint.baseline_binding_id,
                        endpoint.outcome_binding_id,
                        endpoint.connectome_role,
                        endpoint.final_eligible,
                        endpoint.requested,
                        endpoint.minimum_subjects,
                        endpoint.status.value,
                        endpoint.matched_reference_endpoint_id is not None,
                    )

                catalog_signatures = {
                    scale_id: tuple(
                        sorted(catalog_signature(endpoint) for endpoint in endpoints)
                    )
                    for scale_id, endpoints in catalog_by_scale.items()
                }
                self.assertEqual(
                    catalog_signatures[EXPECTED_SCALES[0]],
                    catalog_signatures[EXPECTED_SCALES[1]],
                )

                task_index = {task.task_id: task for task in bundle.plan.tasks}
                task_signatures = {}
                for scale_id, endpoints in catalog_by_scale.items():
                    endpoint_ids = {endpoint.endpoint_id for endpoint in endpoints}
                    task_signatures[scale_id] = tuple(
                        sorted(
                            _task_signature(task, task_index)
                            for task in bundle.plan.tasks
                            if task.endpoint_id in endpoint_ids
                        )
                    )
                self.assertEqual(
                    task_signatures[EXPECTED_SCALES[0]],
                    task_signatures[EXPECTED_SCALES[1]],
                )

                expensive_tasks = tuple(
                    task for task in bundle.plan.tasks if task.expensive_producer
                )
                self.assertTrue(expensive_tasks)
                self.assertTrue(
                    all(task.cache_first_expensive for task in expensive_tasks)
                )

                artifacts = ArtifactStore((root,))
                provider = service._default_provider(
                    validated,
                    work_root=root / "runtime_work",
                    artifact_store=artifacts,
                )
                readiness_by_scale: dict[str, dict[tuple[str, str], EndpointInputRecord]] = {
                    scale_id: {} for scale_id in EXPECTED_SCALES
                }
                for endpoint in validated.catalog:
                    publisher = RunScopedArtifactPublisher(
                        root / "readiness" / endpoint.endpoint_id,
                        f"smoke_readiness_{endpoint.endpoint_id}",
                        "1",
                    )
                    readiness = provider.publish_endpoint_input(
                        endpoint.endpoint_id,
                        publisher,
                    )
                    self.assertEqual(
                        readiness.candidate_subject_ids,
                        endpoint.subject_ids,
                    )
                    self.assertTrue(
                        set(readiness.included_subject_ids) <= set(endpoint.subject_ids)
                    )
                    self.assertEqual(
                        {
                            *readiness.included_subject_ids,
                            *(item.subject_id for item in readiness.exclusions),
                        },
                        set(readiness.candidate_subject_ids),
                    )
                    readiness_by_scale[endpoint.key.scale_id][
                        (endpoint.key.model_family, endpoint.key.connectome_id)
                    ] = readiness

                self.assertEqual(
                    set(readiness_by_scale[EXPECTED_SCALES[0]]),
                    set(readiness_by_scale[EXPECTED_SCALES[1]]),
                )
                producer.assert_not_called()
                transformer.assert_not_called()
                self.assertFalse(
                    any(_is_project_namespace(name) for name in sys.modules)
                )


if __name__ == "__main__":
    unittest.main()
