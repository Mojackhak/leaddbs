"""Subprocess bridge from canonical Python tasks to MATLAB."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Callable, Mapping, TextIO

from .planner import VtaTask
from .process_monitor import ProcessTreeMemoryMonitor
from .telemetry import EVENT_PREFIX, EventStreamParser, ProcessObservation


@dataclass(frozen=True)
class TaskRunContext:
    run_id: str
    output_leaves: Mapping[str, Path]
    missing_artifacts: Mapping[str, tuple[str, ...]]


class MatlabBridge:
    """Invoke `mh_vta_run_canonical_task` for one resolved task."""

    def __init__(
        self,
        *,
        repo_root: Path | str,
        matlab_executable: str = "matlab",
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        memory_monitor: ProcessTreeMemoryMonitor | None = None,
        diagnostic_sink: Callable[[str], None] | None = None,
        terminate_timeout_seconds: float = 10.0,
    ) -> None:
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.matlab_executable = matlab_executable
        self._popen_factory = popen_factory
        self._memory_monitor = memory_monitor
        self._diagnostic_sink = diagnostic_sink or _write_diagnostic
        self._terminate_timeout_seconds = terminate_timeout_seconds

    def run_task(
        self,
        task: VtaTask,
        context: TaskRunContext,
    ) -> ProcessObservation:
        payload = {
            **task.to_payload(),
            "run_id": context.run_id,
            "output_leaves": {
                space: str(path) for space, path in context.output_leaves.items()
            },
            "missing_artifacts": {
                space: list(names)
                for space, names in context.missing_artifacts.items()
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
            process = self._popen_factory(
                [self.matlab_executable, "-batch", batch],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            parser = EventStreamParser(
                context.run_id,
                task.subject_id,
                (task.task_id,),
            )
            registered = False
            try:
                if self._memory_monitor is not None:
                    self._memory_monitor.register(task.subject_id, process.pid)
                    registered = True
                stdout = _require_stdout(process.stdout)
                for line in stdout:
                    if line.startswith(EVENT_PREFIX):
                        parser.feed_line(line)
                    else:
                        self._diagnostic_sink(line)
                returncode = process.wait()
            except BaseException:
                _terminate_and_reap(
                    process,
                    timeout_seconds=self._terminate_timeout_seconds,
                )
                raise
            finally:
                if registered and self._memory_monitor is not None:
                    self._memory_monitor.unregister(task.subject_id, process.pid)
            return parser.finish(returncode)


def _require_stdout(stdout: TextIO | None) -> TextIO:
    if stdout is None:
        raise RuntimeError("MATLAB stdout pipe was not created")
    return stdout


def _terminate_and_reap(
    process: subprocess.Popen[str],
    *,
    timeout_seconds: float,
) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _write_diagnostic(line: str) -> None:
    sys.stdout.write(line)
    sys.stdout.flush()


def _matlab_double_quote(value: Path) -> str:
    return str(value).replace('"', '""')


def _matlab_single_quote(value: Path) -> str:
    return str(value).replace("'", "''")
