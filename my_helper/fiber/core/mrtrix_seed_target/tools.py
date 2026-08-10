"""External executable resolution, normalized versions, and process execution."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import threading
from typing import Callable, Mapping, Sequence

import psutil

from .errors import ExecutionInterrupted, ToolError, ValidationError
from .identity import file_sha256
from .models import BatchConfig, ToolIdentity


MRTRIX_TOOLS = ("mrconvert", "dwi2response", "dwi2fod", "tckgen", "tckinfo")
_STOP_REQUESTED = threading.Event()
_ACTIVE_PROCESSES: set[subprocess.Popen[str]] = set()
_ACTIVE_LOCK = threading.Lock()


def reset_stop_request() -> None:
    """Clear a prior batch stop request before admitting new producers."""

    _STOP_REQUESTED.clear()


def request_stop() -> None:
    """Stop new producers and terminate all currently registered process groups."""

    _STOP_REQUESTED.set()
    with _ACTIVE_LOCK:
        processes = tuple(_ACTIVE_PROCESSES)
    for process in processes:
        _terminate_process_group(process)


def _process_tree_rss_gb(process: subprocess.Popen[str]) -> float:
    """Return current RSS for one producer and all recursively spawned children."""

    try:
        root = psutil.Process(process.pid)
        members = [root, *root.children(recursive=True)]
    except (psutil.Error, OSError):
        return 0.0
    rss = 0
    for member in members:
        try:
            rss += int(member.memory_info().rss)
        except (psutil.Error, OSError):
            continue
    return rss / (1024.0**3)


def _terminate_process_group(
    process: subprocess.Popen[str], *, grace_seconds: float = 5.0
) -> None:
    """Terminate and reap a producer's complete POSIX process group."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.terminate()
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        pass


def _resolve_executable(name: str, prefix: Path | None) -> Path:
    candidate = prefix / name if prefix is not None else None
    if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate.resolve()
    located = shutil.which(name)
    if located:
        return Path(located).resolve()
    detail = f" below {prefix}" if prefix is not None else " on PATH"
    raise ValidationError(f"required executable {name!r} was not found{detail}")


def _normalize_version(output: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)
    text = text.replace("\b", "")
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValidationError("external tool returned an empty version response")
    return " | ".join(lines[:4])


def _version(executable: Path, arguments: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            [str(executable), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=180,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(f"cannot query version from {executable}: {exc}") from exc
    if result.returncode != 0:
        raise ValidationError(
            f"version query failed for {executable} with exit {result.returncode}: "
            f"{result.stdout.strip()}"
        )
    return _normalize_version(result.stdout)


def resolve_tool_identities(config: BatchConfig) -> Mapping[str, ToolIdentity]:
    """Resolve all external tools and their normalized version identities."""

    identities: dict[str, ToolIdentity] = {}
    for name in MRTRIX_TOOLS:
        executable = _resolve_executable(name, config.execution.mrtrix_path_prefix)
        identities[name] = ToolIdentity(
            name=name,
            executable=executable,
            version=_version(executable, ("-version",)),
        )
    matlab = config.execution.matlab_executable
    if not matlab.is_file() or not os.access(matlab, os.X_OK):
        raise ValidationError(f"MATLAB executable is not executable: {matlab}")
    matlab_version = _version(
        matlab,
        (
            "-batch",
            "fprintf('MATLAB %s release %s\\n', version, version('-release'));",
        ),
    )
    identities["matlab"] = ToolIdentity(
        name="matlab",
        executable=matlab.resolve(),
        version=matlab_version,
    )
    repo_root = Path(__file__).resolve().parents[4]
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        suffix = "maca64" if machine in {"arm64", "aarch64"} else "maci64"
    elif system == "Linux":
        suffix = "glnxa64"
    elif system == "Windows":
        suffix = "exe"
    else:
        raise ValidationError(
            f"unsupported platform for antsApplyTransformsToPoints: {system} {machine}"
        )
    ants = repo_root / "ext_libs" / "ANTs" / f"antsApplyTransformsToPoints.{suffix}"
    if not ants.is_file() or not os.access(ants, os.X_OK):
        raise ValidationError(
            f"bundled antsApplyTransformsToPoints is not executable: {ants}"
        )
    identities["antsApplyTransformsToPoints"] = ToolIdentity(
        name="antsApplyTransformsToPoints",
        executable=ants.resolve(),
        version=f"sha256:{file_sha256(ants)}",
    )
    return identities


def run_command(
    command: Sequence[str | Path],
    *,
    log_path: Path,
    environment: Mapping[str, str] | None = None,
    memory_observer: Callable[[float], None] | None = None,
    sample_interval_seconds: float = 0.25,
) -> subprocess.CompletedProcess[str]:
    """Run, monitor, log, and safely interrupt one external producer tree."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_command = [str(item) for item in command]
    env = os.environ.copy()
    if environment:
        env.update({str(key): str(value) for key, value in environment.items()})
    if _STOP_REQUESTED.is_set():
        raise ExecutionInterrupted("execution was interrupted before producer launch")
    process: subprocess.Popen[str]
    try:
        process = subprocess.Popen(
            resolved_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,
        )
    except OSError as exc:
        raise ToolError(f"failed to launch {resolved_command[0]}: {exc}") from exc
    with _ACTIVE_LOCK:
        _ACTIVE_PROCESSES.add(process)
    output = ""
    interrupted: BaseException | None = None
    try:
        while True:
            try:
                output, _ = process.communicate(timeout=sample_interval_seconds)
                break
            except subprocess.TimeoutExpired:
                if memory_observer is not None:
                    memory_observer(_process_tree_rss_gb(process))
                if _STOP_REQUESTED.is_set():
                    raise ExecutionInterrupted(
                        "execution was interrupted while an external producer was active"
                    )
        if memory_observer is not None:
            memory_observer(_process_tree_rss_gb(process))
        if _STOP_REQUESTED.is_set():
            raise ExecutionInterrupted(
                "execution was interrupted while an external producer was active"
            )
    except BaseException as exc:
        interrupted = exc
        _terminate_process_group(process)
        try:
            output, _ = process.communicate(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            output = output or ""
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_PROCESSES.discard(process)
    result = subprocess.CompletedProcess(
        resolved_command,
        process.returncode if process.returncode is not None else -1,
        output,
        None,
    )
    log_path.write_text(
        "$ "
        + " ".join(resolved_command)
        + "\n\n"
        + result.stdout
        + (f"\n[interrupted: {type(interrupted).__name__}: {interrupted}]\n" if interrupted else ""),
        encoding="utf-8",
    )
    if interrupted is not None:
        raise interrupted
    if result.returncode != 0:
        raise ToolError(
            f"external command failed with exit {result.returncode}; see {log_path}"
        )
    return result
