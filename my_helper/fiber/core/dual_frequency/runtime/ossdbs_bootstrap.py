"""Run the locked OSS-DBSv2 CLI with a bounded NGSolve task manager."""

from __future__ import annotations

import sys
from typing import Sequence


NGSOLVE_THREADS = 1
TASKMANAGER_SMOKE_ARGUMENT = "--taskmanager-smoke"


def _configure_ngsolve():
    import ngsolve

    ngsolve.SetNumThreads(NGSOLVE_THREADS)
    return ngsolve


def main(arguments: Sequence[str] | None = None) -> int:
    """Configure NGSolve before delegating to the installed OSS-DBSv2 CLI."""

    configured_arguments = tuple(sys.argv[1:] if arguments is None else arguments)
    ngsolve = _configure_ngsolve()
    if configured_arguments == (TASKMANAGER_SMOKE_ARGUMENT,):
        with ngsolve.TaskManager():
            pass
        return 0

    from ossdbs.main import main as ossdbs_main

    previous_argv = sys.argv
    sys.argv = [previous_argv[0], *configured_arguments]
    try:
        result = ossdbs_main()
    finally:
        sys.argv = previous_argv
    return 0 if result is None else int(result)


if __name__ == "__main__":
    raise SystemExit(main())
