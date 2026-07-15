"""WorkflowService and public CLI tests with synthetic observed-only services."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np
import yaml

from dual_frequency.application.cli import main
from dual_frequency.application.service import WorkflowRequest, WorkflowService
from dual_frequency.contracts import ArtifactRef, AxisRef
from dual_frequency.config import WorkflowOverrides
from dual_frequency.workflow import RegisteredService, ServiceRegistry, ServiceResult

from test_study_base import _subject, study_payload


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CONFIG_ROOT = REPOSITORY_ROOT / "my_helper" / "stnsnr" / "config" / "four_model_v1"
ENTRYPOINT = REPOSITORY_ROOT / "my_helper" / "fiber" / "pipelines" / "run_dual_frequency_models.py"


def _write_fixture(root: Path) -> WorkflowRequest:
    payload = study_payload()
    payload["study"]["subjects"] = [_subject(f"subject-{index:02d}") for index in range(1, 13)]
    study_path = root / "study_base.json"
    study_path.write_text(json.dumps(payload), encoding="utf-8")

    direct = yaml.safe_load((CONFIG_ROOT / "direct_voxel_model_test.yaml").read_text(encoding="utf-8"))
    fiber = yaml.safe_load((CONFIG_ROOT / "normative_fiber_model_test.yaml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load((CONFIG_ROOT / "workflow.yaml").read_text(encoding="utf-8"))
    scales = ["scale_a", "scale_b"]
    for profile in (direct, fiber):
        profile["model_set_id"] = "synthetic_dual_frequency_v1"
        profile["output"]["root"] = str(root / "outputs")
        profile["scales"] = scales
    fiber["connectomes"]["entries"] = [
        {
            "connectome_id": "connectome_a",
            "label": "Synthetic formal connectome",
            "path": "/tmp/data.mat",
            "role": "formal",
            "fold_candidate_fibers_min": 20,
        }
    ]
    direct_path = root / "direct_voxel_model.yaml"
    fiber_path = root / "normative_fiber_model.yaml"
    workflow_path = root / "workflow.yaml"
    direct_path.write_text(yaml.safe_dump(direct, sort_keys=False), encoding="utf-8")
    fiber_path.write_text(yaml.safe_dump(fiber, sort_keys=False), encoding="utf-8")
    workflow["model_profiles"] = {
        "direct_voxel": direct_path.name,
        "normative_fiber": fiber_path.name,
    }
    workflow["selection"] = {"models": ["all"], "connectomes": ["all"]}
    workflow["execution"]["through"] = "observed"
    workflow["execution"]["allow_expensive_producers"] = False
    workflow["execution"]["workers"] = 2
    workflow["storage"] = {
        "cache_root": str(root / "cache"),
        "run_root": str(root / "runs"),
    }
    workflow_path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")
    return WorkflowRequest(
        study_base=study_path,
        direct_voxel_model=direct_path,
        normative_fiber_model=fiber_path,
        workflow_profile=workflow_path,
        overrides=WorkflowOverrides(all_available=True, through="observed"),
    )


def _service_result(request, calls: list[str]) -> ServiceResult:
    calls.append(request.task.task_id)
    facts: dict[str, bool] = {}
    if request.task.stage == "source_resolver":
        facts.update(
            source_accepted=True,
            reference_source_accepted=True,
            formal_source_available=True,
        )
    if request.task.stage == "reference_dependency":
        facts["reference_dependency_ready"] = True
    if request.task.stage == "delta_reference_input":
        facts["delta_inputs_valid"] = True
    if request.task.stage == "formal_source_evaluation":
        facts.update(
            reference_source_accepted=True,
            delta_inputs_valid=True,
            formal_source_available=True,
        )
    if request.task.stage == "final_realization":
        facts["final_model_realized"] = True

    artifacts: tuple[ArtifactRef, ...] = ()
    if request.task.output_record_type in {"ArtifactRef", "ObservedResult"}:
        path = request.output_dir / "synthetic.npy"
        np.save(path, np.arange(4, dtype=np.float64))
        axis = AxisRef("synthetic_features", 4, "e" * 64)
        artifacts = (
            ArtifactRef(
                kind="synthetic_array",
                schema_version="array_v1",
                uri=path.resolve().as_uri(),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                dtype="float64",
                shape=(4,),
                axis_refs=(axis,),
                axis_hashes=(axis.sha256,),
                units="arbitrary",
                space="synthetic",
                producer_id="application_test",
                producer_version="1",
            ),
        )
    return ServiceResult.create(
        request.task.output_record_type,
        f"record:{request.task.task_id}",
        {"stage": request.task.stage},
        artifacts=artifacts,
        facts=facts,
    )


def _registry_for_plan(plan, calls: list[str]) -> ServiceRegistry:
    registry = ServiceRegistry()
    for service_id in sorted({task.service_id for task in plan.tasks}):
        registry.register(
            service_id,
            lambda request, calls=calls: _service_result(request, calls),
        )
    return registry


class ApplicationCliTest(unittest.TestCase):
    def test_validate_and_plan_build_two_scale_four_model_dag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            request = _write_fixture(Path(temporary_directory))
            service = WorkflowService()
            summary = service.validate(request)
            bundle = service.plan(request)
        self.assertEqual(summary.selected_scales, ("scale_a", "scale_b"))
        self.assertEqual(summary.endpoint_count, 8)
        self.assertEqual(summary.available_endpoint_count, 8)
        self.assertTrue(bundle.plan.tasks)
        self.assertTrue(all(task.phase == "observed" for task in bundle.plan.tasks))
        self.assertEqual(
            {task.model_family for task in bundle.plan.tasks},
            {"reference_voxel", "reference_fiber", "addon_voxel", "addon_fiber"},
        )

    def test_observed_only_run_resume_force_status_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            request = _write_fixture(root)
            planning_service = WorkflowService()
            plan = planning_service.plan(request).plan
            calls: list[str] = []
            service = WorkflowService(registry=_registry_for_plan(plan, calls))
            first = service.run(request, run_id="synthetic-run")
            first_call_count = len(calls)
            run_root = root / "runs" / "synthetic" / "synthetic-run"
            status = service.status(run_root)
            artifacts = service.artifacts(run_root)

            resumed_request = WorkflowRequest(
                study_base=request.study_base,
                direct_voxel_model=request.direct_voxel_model,
                normative_fiber_model=request.normative_fiber_model,
                workflow_profile=request.workflow_profile,
                overrides=WorkflowOverrides(
                    all_available=True,
                    through="observed",
                    resume=True,
                ),
            )
            resumed = service.run(resumed_request, run_id="synthetic-run")

            forced_request = WorkflowRequest(
                study_base=request.study_base,
                direct_voxel_model=request.direct_voxel_model,
                normative_fiber_model=request.normative_fiber_model,
                workflow_profile=request.workflow_profile,
                overrides=WorkflowOverrides(
                    all_available=True,
                    through="observed",
                    force=True,
                ),
            )
            forced = service.run(forced_request, run_id="synthetic-run")
            forced_root = root / "runs" / "synthetic" / forced.run_id
            forced_manifest = json.loads(
                (forced_root / "run_manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(first.exit_code, 0)
        self.assertEqual(resumed.exit_code, 0)
        self.assertEqual(len(calls), first_call_count * 2)
        self.assertEqual(status["run_manifest"]["final_status"], "completed")
        self.assertTrue(artifacts["artifacts"])
        self.assertNotEqual(forced.run_id, "synthetic-run")
        self.assertEqual(forced_manifest["parent_run_id"], "synthetic-run")

    def test_cli_requires_explicit_profiles_and_scale_selection(self) -> None:
        parser_errors = (
            ["validate"],
            ["validate", "--all-available"],
        )
        for arguments in parser_errors:
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(arguments)

        with tempfile.TemporaryDirectory() as temporary_directory:
            request = _write_fixture(Path(temporary_directory))
            arguments = [
                "validate",
                "--study-base", str(request.study_base),
                "--direct-voxel-model", str(request.direct_voxel_model),
                "--normative-fiber-model", str(request.normative_fiber_model),
                "--workflow-profile", str(request.workflow_profile),
                "--scale", "scale_b",
                "--scale", "scale_a",
            ]
            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(arguments)
            payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["selected_scales"], ["scale_b", "scale_a"])

    def test_public_entrypoint_imports_without_pythonpath(self) -> None:
        environment = copy.deepcopy(os.environ)
        environment.pop("PYTHONPATH", None)
        help_result = subprocess.run(
            [sys.executable, str(ENTRYPOINT), "--help"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("validate", help_result.stdout)

        with tempfile.TemporaryDirectory() as temporary_directory:
            request = _write_fixture(Path(temporary_directory))
            validate_result = subprocess.run(
                [
                    sys.executable,
                    str(ENTRYPOINT),
                    "validate",
                    "--study-base", str(request.study_base),
                    "--direct-voxel-model", str(request.direct_voxel_model),
                    "--normative-fiber-model", str(request.normative_fiber_model),
                    "--workflow-profile", str(request.workflow_profile),
                    "--all-available",
                    "--through", "observed",
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(validate_result.returncode, 0, validate_result.stderr)
        self.assertEqual(json.loads(validate_result.stdout)["endpoint_count"], 8)


if __name__ == "__main__":
    unittest.main()
