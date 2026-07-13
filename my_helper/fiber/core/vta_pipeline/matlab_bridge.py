"""Subprocess bridge from canonical Python tasks to MATLAB."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Callable, Mapping

from .planner import VtaTask


@dataclass(frozen=True)
class TaskRunContext:
    run_id: str
    input_hash: str
    study_base_sha256: str
    vta_model_sha256: str
    implementation_sha256: str
    code_commit: str | None
    resume: bool
    force: bool
    output_leaves: Mapping[str, Path]


class MatlabBridge:
    """Invoke `mh_vta_run_canonical_task` for one resolved task."""

    def __init__(
        self,
        *,
        repo_root: Path | str,
        matlab_executable: str = "matlab",
        runner: Callable[..., object] = subprocess.run,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.matlab_executable = matlab_executable
        self._runner = runner

    def run_task(self, task: VtaTask, context: TaskRunContext) -> None:
        payload = {
            **task.to_payload(),
            "run_id": context.run_id,
            "input_hash": context.input_hash,
            "study_base_sha256": context.study_base_sha256,
            "vta_model_sha256": context.vta_model_sha256,
            "implementation_sha256": context.implementation_sha256,
            "code_commit": context.code_commit,
            "resume": context.resume,
            "force": context.force,
            "output_leaves": {
                space: str(path) for space, path in context.output_leaves.items()
            },
        }
        with tempfile.TemporaryDirectory(prefix="vta-model-") as directory:
            task_path = Path(directory) / "task.json"
            temporary = task_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(task_path)
            batch = (
                f'addpath(genpath("{_matlab_double_quote(self.repo_root)}")); '
                f"mh_vta_run_canonical_task('{_matlab_single_quote(task_path)}');"
            )
            self._runner(
                [self.matlab_executable, "-batch", batch],
                check=True,
                text=True,
            )


def _matlab_double_quote(value: Path) -> str:
    return str(value).replace('"', '""')


def _matlab_single_quote(value: Path) -> str:
    return str(value).replace("'", "''")
