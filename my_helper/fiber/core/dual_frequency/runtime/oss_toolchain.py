"""Project-neutral Lead-DBS/OSS-DBSv2 producer for authorized row misses."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
from threading import RLock
import time
from typing import Any, Callable, Mapping, Protocol, runtime_checkable
from urllib.parse import unquote, urlsplit

import numpy as np
import yaml

from .connectome_subset import (
    ConnectomeSubsetError,
    aggregate_activation_probabilities,
    write_filtered_connectome,
)
from ..backends.activation.canonical_mapping import activation_universe
from ..backends.activation.ossdbs import OSSRowProduct
from ..cache import ArtifactStore
from ..cache.identity import sha256_file
from ..contracts.identity import canonical_hash
from .activation_provider import OSSProducerRequest


class OSSProducerExecutionError(RuntimeError):
    """Raised when a verified OSS producer request cannot complete exactly."""


PAM_DIAMETERS_UM = tuple(float(value) for value in np.linspace(1.0, 4.0, 10))
FIXED_AXON_MODEL = "McNeal1976"
FIXED_AXON_LENGTH_MM = 10.0
FIXED_CONDUCTIVITY_MODEL = "ColeCole4"
FILTERED_CONNECTOME_LABEL = "final-axis-filtered"
MATLAB_PREP_TIMEOUT_SECONDS = 15 * 60
AXON_PREP_TIMEOUT_SECONDS = 30 * 60
CONVERTER_TIMEOUT_SECONDS = 5 * 60
OSS_SOLVER_TIMEOUT_SECONDS = 6 * 60 * 60
PATHWAY_ACTIVATION_TIMEOUT_SECONDS = 2 * 60 * 60
PROCESS_TERMINATION_GRACE_SECONDS = 10.0

OSS_PRODUCER_IMPLEMENTATION_PATHS = (
    Path("classes/conda_utils/environments/OSS-DBSv2.yml"),
    Path("my_helper/fiber/core/stimulation/model/mh_oss_prepare_canonical_row.m"),
    Path("my_helper/fiber/core/stimulation/model/mh_oss_assemble_boundary.m"),
    Path(
        "my_helper/fiber/core/stimulation/model/"
        "mh_oss_map_left_coordinates_to_right.m"
    ),
    Path("templates/electrode_models/ea_resolve_elspec.m"),
)
OSS_PRODUCER_IMPLEMENTATION_ROOTS = (
    Path("my_helper/fiber/core/dual_frequency"),
)


def _token(value: object, field: str) -> str:
    token = str(value).strip()
    if not token:
        raise OSSProducerExecutionError(f"{field} must be nonempty")
    return token


def _finite_positive(value: object, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OSSProducerExecutionError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise OSSProducerExecutionError(f"{field} must be positive and finite")
    return number


def _sha256(value: object, field: str) -> str:
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise OSSProducerExecutionError(f"{field} must be a full SHA-256 digest")
    return digest


def _git_commit(value: object, field: str) -> str:
    commit = str(value).strip().lower()
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise OSSProducerExecutionError(f"{field} must be a full Git commit")
    return commit


def _hash_oss_source_tree(site_packages: Path) -> str:
    digest = hashlib.sha256()
    count = 0
    for package in ("ossdbs", "leaddbsinterface"):
        package_root = site_packages / package
        if not package_root.is_dir():
            raise OSSProducerExecutionError(f"installed OSS package is missing: {package}")
        for path in sorted(package_root.rglob("*")):
            relative_parts = path.relative_to(package_root).parts
            if (
                not path.is_file()
                or "__pycache__" in relative_parts
                or path.suffix.lower() in {".pyc", ".pyo"}
            ):
                continue
            relative = f"{package}/{path.relative_to(package_root).as_posix()}"
            digest.update(relative.encode("utf-8") + b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
            count += 1
    if count == 0:
        raise OSSProducerExecutionError("installed OSS source tree is empty")
    return digest.hexdigest()


def _hash_oss_entrypoints(paths: Mapping[str, Path]) -> str:
    digest = hashlib.sha256()
    for name in sorted(paths):
        lines = paths[name].read_bytes().splitlines(keepends=True)
        if not lines or not lines[0].startswith(b"#!"):
            raise OSSProducerExecutionError(f"OSS entrypoint lacks a shebang: {name}")
        normalized = b"#!python\n" + b"".join(lines[1:])
        digest.update(name.encode("utf-8") + b"\0" + normalized + b"\0")
    return digest.hexdigest()


def _exact_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise OSSProducerExecutionError(
            f"{label} fields differ: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _file_signature(path: Path) -> tuple[int, int, int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise OSSProducerExecutionError(f"producer input is unavailable: {path}") from exc
    return (int(stat.st_dev), int(stat.st_ino), int(stat.st_size), int(stat.st_mtime_ns))


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise OSSProducerExecutionError(f"{field} must be a positive integer")
    try:
        integer = int(str(value))
    except (TypeError, ValueError) as exc:
        raise OSSProducerExecutionError(f"{field} must be a positive integer") from exc
    if integer < 1 or str(integer) != str(value).strip():
        raise OSSProducerExecutionError(f"{field} must be a positive integer")
    return integer


def _stable_file_hash(path: Path) -> str:
    resolved = Path(path).resolve(strict=True)
    signature = _file_signature(resolved)
    digest = sha256_file(resolved)
    if _file_signature(resolved) != signature:
        raise OSSProducerExecutionError(
            f"producer implementation changed while it was hashed: {resolved}"
        )
    return digest


def oss_backend_version(
    repository_root: Path,
    *,
    file_hasher: Callable[[Path], str] | None = None,
) -> str:
    """Attest the complete local implementation represented by a row cache key."""

    root = Path(repository_root).expanduser().resolve(strict=True)
    hasher = file_hasher or _stable_file_hash
    implementation_files = set(OSS_PRODUCER_IMPLEMENTATION_PATHS)
    for relative_root in OSS_PRODUCER_IMPLEMENTATION_ROOTS:
        implementation_root = root / relative_root
        if not implementation_root.is_dir():
            raise OSSProducerExecutionError(
                f"producer implementation root is unavailable: {implementation_root}"
            )
        implementation_files.update(
            path.relative_to(root)
            for path in implementation_root.rglob("*.py")
            if "tests" not in path.relative_to(implementation_root).parts
            and "__pycache__" not in path.parts
        )
    implementation_hashes = {
        str(relative): _sha256(hasher(root / relative), str(relative))
        for relative in sorted(implementation_files)
    }
    return "definition-sha256-" + canonical_hash(
        {
            "contract": "dual_frequency_oss_producer_v1",
            "implementation_sha256": implementation_hashes,
        }
    )


def _normalized_inventory(text: str, *, ignore_comments: bool) -> tuple[int, str]:
    lines = tuple(
        sorted(
            line.strip()
            for line in str(text).splitlines()
            if line.strip() and not (ignore_comments and line.lstrip().startswith("#"))
        )
    )
    if not lines:
        raise OSSProducerExecutionError("installed environment inventory is empty")
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    return len(lines), hashlib.sha256(payload).hexdigest()


def _terminate_process_group(
    process: subprocess.Popen[Any],
    *,
    process_group_id: int | None = None,
    grace_seconds: float = PROCESS_TERMINATION_GRACE_SECONDS,
) -> None:
    if os.name == "posix":
        process_group_id = process.pid if process_group_id is None else process_group_id
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.killpg(process_group_id, 0)
            except ProcessLookupError:
                try:
                    process.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    pass
                return
            except PermissionError as exc:
                if _posix_process_group_has_live_members(process_group_id):
                    raise OSSProducerExecutionError(
                        "cannot signal the live external OSS process group"
                    ) from exc
                process.wait(timeout=grace_seconds)
                return
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            try:
                process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass
            return
        except PermissionError as exc:
            if _posix_process_group_has_live_members(process_group_id):
                raise OSSProducerExecutionError(
                    "cannot kill the live external OSS process group"
                ) from exc
            process.wait(timeout=grace_seconds)
            return
    else:
        if process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired as exc:
        raise OSSProducerExecutionError(
            "external OSS process group did not terminate"
        ) from exc


def _posix_process_group_has_live_members(process_group_id: int) -> bool:
    inventory = subprocess.run(
        ("ps", "-axo", "pgid=,stat="),
        capture_output=True,
        text=True,
        check=False,
    )
    if inventory.returncode != 0:
        raise OSSProducerExecutionError(
            "cannot inspect the external OSS process group"
        )
    for line in inventory.stdout.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            continue
        try:
            group_id = int(fields[0])
        except ValueError:
            continue
        if group_id == process_group_id and not fields[1].startswith("Z"):
            return True
    return False


def _capture_process(
    command: tuple[str, ...],
    *,
    timeout_seconds: float,
    label: str,
) -> tuple[int, str, str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    process_group_id = process.pid if os.name == "posix" else None
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(
            process,
            process_group_id=process_group_id,
        )
        stdout, stderr = process.communicate()
        raise OSSProducerExecutionError(f"{label} timed out") from exc
    return int(process.returncode), stdout, stderr


@dataclass(frozen=True, slots=True)
class OSSInputSnapshot:
    """Verified producer input whose filesystem identity must remain stable."""

    path: Path
    sha256: str
    signature: tuple[int, int, int, int]
    label: str

    def __post_init__(self) -> None:
        path = Path(self.path).resolve(strict=True)
        if not path.is_file():
            raise OSSProducerExecutionError(f"snapshot input must be a file: {path}")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "sha256", _sha256(self.sha256, f"{self.label}_sha256"))
        if self.signature != _file_signature(path):
            raise OSSProducerExecutionError(f"{self.label} changed while it was verified")
        object.__setattr__(self, "label", _token(self.label, "snapshot label"))

    def assert_unchanged(self) -> None:
        if _file_signature(self.path) != self.signature:
            raise OSSProducerExecutionError(
                f"{self.label} changed during OSS row production"
            )


def _file_uri_path(
    uri: object,
    field: str,
    *,
    directory: bool = False,
    allowed_roots: tuple[Path, ...] | None = None,
) -> Path:
    parsed = urlsplit(str(uri))
    if (
        parsed.scheme != "file"
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise OSSProducerExecutionError(f"{field} must be a local absolute file URI")
    try:
        path = Path(unquote(parsed.path)).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise OSSProducerExecutionError(f"{field} does not resolve") from exc
    if directory and not path.is_dir():
        raise OSSProducerExecutionError(f"{field} must resolve to a directory")
    if not directory and not path.is_file():
        raise OSSProducerExecutionError(f"{field} must resolve to a file")
    if allowed_roots is not None and not any(
        _is_within(path, root) for root in allowed_roots
    ):
        raise OSSProducerExecutionError(f"{field} is outside its configured roots")
    return path


@dataclass(frozen=True, slots=True)
class OSSBoundaryContact:
    """One side-local contact allocation in a canonical source."""

    contact: int | str
    polarity: str
    fraction: float

    def __post_init__(self) -> None:
        contact = self.contact
        if isinstance(contact, bool):
            raise OSSProducerExecutionError("contact cannot be boolean")
        if isinstance(contact, int):
            if contact < 1:
                raise OSSProducerExecutionError("numeric contacts must be one-based")
        elif str(contact).strip().lower() == "case":
            contact = "case"
        else:
            raise OSSProducerExecutionError("contact must be a positive integer or case")
        polarity = str(self.polarity).strip().lower()
        if polarity not in {"cathode", "anode"}:
            raise OSSProducerExecutionError("contact polarity must be cathode or anode")
        fraction = _finite_positive(self.fraction, "contact fraction")
        if fraction > 1.0:
            raise OSSProducerExecutionError("contact fraction cannot exceed one")
        object.__setattr__(self, "contact", contact)
        object.__setattr__(self, "polarity", polarity)
        object.__setattr__(self, "fraction", fraction)


@dataclass(frozen=True, slots=True)
class OSSBoundarySource:
    """One fully validated source participating in a producer row."""

    source_id: str
    control_mode: str
    amplitude: float
    pulse_width_us: float
    frequency_hz: float
    contacts: tuple[OSSBoundaryContact, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _token(self.source_id, "source_id"))
        mode = str(self.control_mode).strip().lower()
        if mode not in {"voltage", "current"}:
            raise OSSProducerExecutionError("control_mode must be voltage or current")
        object.__setattr__(self, "control_mode", mode)
        object.__setattr__(self, "amplitude", _finite_positive(self.amplitude, "amplitude"))
        object.__setattr__(
            self,
            "pulse_width_us",
            _finite_positive(self.pulse_width_us, "pulse_width_us"),
        )
        object.__setattr__(
            self,
            "frequency_hz",
            _finite_positive(self.frequency_hz, "frequency_hz"),
        )
        contacts = tuple(self.contacts)
        if not contacts or not all(isinstance(item, OSSBoundaryContact) for item in contacts):
            raise OSSProducerExecutionError("sources require typed contacts")
        identities = tuple(item.contact for item in contacts)
        if len(set(identities)) != len(identities):
            raise OSSProducerExecutionError("a source cannot reuse a contact")
        polarities = {item.polarity for item in contacts}
        if polarities != {"cathode", "anode"}:
            raise OSSProducerExecutionError("sources require at least one cathode and one anode")
        case_contacts = tuple(item for item in contacts if item.contact == "case")
        if case_contacts:
            if case_contacts[0].polarity != "anode" or any(
                item.polarity == "anode" and item.contact != "case" for item in contacts
            ):
                raise OSSProducerExecutionError("case must be the sole anode")
        if mode == "voltage":
            if any(item.fraction != 1.0 for item in contacts):
                raise OSSProducerExecutionError(
                    "every active voltage contact must have fraction 1.0"
                )
        else:
            for polarity in ("cathode", "anode"):
                total = math.fsum(
                    item.fraction for item in contacts if item.polarity == polarity
                )
                if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
                    raise OSSProducerExecutionError(
                        f"source {self.source_id!r} {polarity} fractions must sum to one"
                    )
        object.__setattr__(self, "contacts", contacts)

    @property
    def return_topology(self) -> str:
        return "case" if any(item.contact == "case" for item in self.contacts) else "electrode"

    @property
    def numeric_contacts(self) -> frozenset[int]:
        return frozenset(
            int(item.contact) for item in self.contacts if isinstance(item.contact, int)
        )


@dataclass(frozen=True, slots=True)
class PreparedOSSRow:
    """Verified external-execution request independent of endpoint labels."""

    scientific_identity: str
    subject_id: str
    side: str
    frequency_group_id: str
    delivery_mode: str
    subject_dir: Path
    reconstruction_path: Path
    transform_path: Path | None
    template_segmask_path: Path
    electrode_model: str
    reconstruction_lead_id: int
    contact_count: int
    sources: tuple[OSSBoundarySource, ...]
    connectome_path: Path
    connectome_label: str
    feature_ids: np.ndarray
    input_snapshots: tuple[OSSInputSnapshot, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scientific_identity",
            _sha256(self.scientific_identity, "scientific_identity"),
        )
        object.__setattr__(self, "subject_id", _token(self.subject_id, "subject_id"))
        side = str(self.side).strip().upper()
        if side not in {"L", "R"}:
            raise OSSProducerExecutionError("side must be L or R")
        object.__setattr__(self, "side", side)
        object.__setattr__(
            self,
            "frequency_group_id",
            _token(self.frequency_group_id, "frequency_group_id"),
        )
        delivery_mode = str(self.delivery_mode).strip().lower()
        if delivery_mode not in {"continuous", "alternating"}:
            raise OSSProducerExecutionError("delivery_mode is invalid")
        object.__setattr__(self, "delivery_mode", delivery_mode)
        for field in ("subject_dir", "reconstruction_path", "template_segmask_path", "connectome_path"):
            path = Path(getattr(self, field)).expanduser().resolve()
            expected_directory = field == "subject_dir"
            if (expected_directory and not path.is_dir()) or (
                not expected_directory and not path.is_file()
            ):
                raise OSSProducerExecutionError(f"{field} is unavailable: {path}")
            object.__setattr__(self, field, path)
        if side == "L":
            if self.transform_path is None or not Path(self.transform_path).is_file():
                raise OSSProducerExecutionError("left rows require the exact transform")
            object.__setattr__(self, "transform_path", Path(self.transform_path).resolve())
        elif self.transform_path is not None:
            raise OSSProducerExecutionError("right rows cannot declare a transform path")
        object.__setattr__(self, "electrode_model", _token(self.electrode_model, "electrode_model"))
        if type(self.reconstruction_lead_id) is not int or self.reconstruction_lead_id not in {1, 2}:
            raise OSSProducerExecutionError("reconstruction_lead_id must be 1 or 2")
        if (side == "R" and self.reconstruction_lead_id != 1) or (
            side == "L" and self.reconstruction_lead_id != 2
        ):
            raise OSSProducerExecutionError("side and reconstruction lead are inconsistent")
        if type(self.contact_count) is not int or self.contact_count < 1:
            raise OSSProducerExecutionError("contact_count must be positive")
        sources = tuple(self.sources)
        if not sources or not all(isinstance(item, OSSBoundarySource) for item in sources):
            raise OSSProducerExecutionError("sources must contain typed boundary sources")
        if delivery_mode == "alternating" and len(sources) != 1:
            raise OSSProducerExecutionError("alternating rows require exactly one source")
        if len({item.source_id for item in sources}) != len(sources):
            raise OSSProducerExecutionError("source IDs must be unique")
        if len({item.control_mode for item in sources}) != 1:
            raise OSSProducerExecutionError("one row cannot mix control modes")
        if len({item.frequency_hz for item in sources}) != 1:
            raise OSSProducerExecutionError("one row cannot mix frequencies")
        if len({item.pulse_width_us for item in sources}) != 1:
            raise OSSProducerExecutionError("one row cannot mix pulse widths")
        used: set[int] = set()
        for source in sources:
            if any(value > self.contact_count for value in source.numeric_contacts):
                raise OSSProducerExecutionError("source contact exceeds electrode contact count")
            overlap = used.intersection(source.numeric_contacts)
            if overlap:
                raise OSSProducerExecutionError(
                    f"continuous sources reuse contacts: {sorted(overlap)}"
                )
            used.update(source.numeric_contacts)
        if sources[0].control_mode == "voltage" and len(
            {item.return_topology for item in sources}
        ) != 1:
            raise OSSProducerExecutionError(
                "continuous voltage sources cannot mix return topologies"
            )
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "connectome_label", _token(self.connectome_label, "connectome_label"))
        feature_ids = activation_universe(self.feature_ids)
        if np.any(feature_ids < 1):
            raise OSSProducerExecutionError("feature_ids must contain positive fiber IDs")
        object.__setattr__(self, "feature_ids", feature_ids)
        snapshots = tuple(self.input_snapshots)
        if not snapshots or not all(isinstance(item, OSSInputSnapshot) for item in snapshots):
            raise OSSProducerExecutionError("input_snapshots must contain verified OSS inputs")
        expected_paths = {
            self.reconstruction_path,
            self.template_segmask_path,
            self.connectome_path,
        }
        if self.transform_path is not None:
            expected_paths.add(self.transform_path)
        if {item.path for item in snapshots} != expected_paths:
            raise OSSProducerExecutionError("input snapshots do not cover exact producer files")
        object.__setattr__(self, "input_snapshots", snapshots)

    @property
    def control_mode(self) -> str:
        return self.sources[0].control_mode

    @property
    def frequency_hz(self) -> float:
        return self.sources[0].frequency_hz

    @property
    def pulse_width_us(self) -> float:
        return self.sources[0].pulse_width_us


@runtime_checkable
class OSSRowExecutor(Protocol):
    """External row executor injected for deterministic testing."""

    def execute(self, row: PreparedOSSRow) -> OSSRowProduct: ...


class LeadDBSOSSProducerToolchain:
    """Restore verified source documents and execute one exact OSS row."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        connectome_path: Path,
        connectome_label: str,
        work_root: Path,
        repository_root: Path,
        environment_file: Path,
        subject_roots: Mapping[str, Path],
        executor: OSSRowExecutor | None = None,
        backend_version_resolver: Callable[[Path], str] | None = None,
    ) -> None:
        if not isinstance(artifact_store, ArtifactStore):
            raise TypeError("artifact_store must be an ArtifactStore")
        self.artifact_store = artifact_store
        self.connectome_path = Path(connectome_path).expanduser().resolve()
        self.connectome_label = _token(connectome_label, "connectome_label")
        self.work_root = Path(work_root).expanduser().resolve()
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.environment_file = Path(environment_file).expanduser().resolve()
        if not isinstance(subject_roots, Mapping):
            raise TypeError("subject_roots must be a mapping")
        self.subject_roots = {
            _token(subject_id, "subject root ID"): Path(path).expanduser().resolve()
            for subject_id, path in subject_roots.items()
        }
        if not self.connectome_path.is_file():
            raise OSSProducerExecutionError("formal connectome is unavailable")
        if not self.repository_root.is_dir() or not self.environment_file.is_file():
            raise OSSProducerExecutionError("Lead-DBS repository/environment definition is unavailable")
        canonical_environment = (
            self.repository_root
            / "classes"
            / "conda_utils"
            / "environments"
            / "OSS-DBSv2.yml"
        ).resolve()
        if self.environment_file != canonical_environment:
            raise OSSProducerExecutionError(
                "environment_file must be the repository OSS-DBSv2.yml lock"
            )
        if not self.subject_roots or any(
            not path.is_dir() for path in self.subject_roots.values()
        ):
            raise OSSProducerExecutionError(
                "subject_roots must map study subject IDs to existing directories"
            )
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._snapshot_cache: dict[Path, OSSInputSnapshot] = {}
        self._snapshot_lock = RLock()
        if backend_version_resolver is not None and executor is None:
            raise OSSProducerExecutionError(
                "a custom backend_version_resolver requires an injected test executor"
            )
        self._backend_version_resolver = backend_version_resolver or oss_backend_version
        self.executor = executor or SubprocessOSSRowExecutor(
            work_root=self.work_root,
            repository_root=self.repository_root,
            environment_file=self.environment_file,
        )
        if not isinstance(self.executor, OSSRowExecutor):
            raise TypeError("executor must implement OSSRowExecutor")

    def produce(self, request: OSSProducerRequest) -> OSSRowProduct:
        if not isinstance(request, OSSProducerRequest):
            raise TypeError("request must be an OSSProducerRequest")
        attestation = self._backend_version_resolver(self.repository_root)
        if attestation != request.settings.backend_version:
            raise OSSProducerExecutionError(
                "producer implementation differs from the row cache backend version"
            )
        row = self._prepare(request)
        product = self.executor.execute(row)
        if not isinstance(product, OSSRowProduct):
            raise OSSProducerExecutionError("OSS executor returned an invalid product")
        if not np.array_equal(product.feature_ids, row.feature_ids):
            raise OSSProducerExecutionError("OSS executor changed the exact final fiber axis")
        for snapshot in row.input_snapshots:
            snapshot.assert_unchanged()
        if self._backend_version_resolver(self.repository_root) != attestation:
            raise OSSProducerExecutionError(
                "producer implementation changed during OSS row production"
            )
        return product

    def _snapshot(self, path: Path, expected_digest: object, label: str) -> OSSInputSnapshot:
        resolved = Path(path).resolve(strict=True)
        expected = _sha256(expected_digest, f"{label}_sha256")
        signature = _file_signature(resolved)
        with self._snapshot_lock:
            cached = self._snapshot_cache.get(resolved)
            if cached is not None and cached.signature == signature:
                if cached.sha256 != expected:
                    raise OSSProducerExecutionError(
                        f"{label} content differs from its declared hash"
                    )
                return cached
        digest = sha256_file(resolved)
        if _file_signature(resolved) != signature:
            raise OSSProducerExecutionError(f"{label} changed while it was hashed")
        if digest != expected:
            raise OSSProducerExecutionError(
                f"{label} content differs from its declared hash"
            )
        snapshot = OSSInputSnapshot(resolved, digest, signature, label)
        with self._snapshot_lock:
            self._snapshot_cache[resolved] = snapshot
        return snapshot

    def _prepare(self, request: OSSProducerRequest) -> PreparedOSSRow:
        connectome_snapshot = self._snapshot(
            self.connectome_path,
            request.row.connectome_feature_hash,
            "formal_connectome",
        )

        geometries: list[dict[str, Any]] = []
        parameters: list[dict[str, Any]] = []
        locators: list[dict[str, Any]] = []
        boundary_sources: list[OSSBoundarySource] = []
        for typed_source in request.sources:
            geometries.append(
                self.artifact_store.materialize_document(
                    typed_source.geometry,
                    expected_kind="oss_stimulation_geometry_recipe",
                )
            )
            if len(typed_source.input_artifacts) != 2:
                raise OSSProducerExecutionError(
                    "each OSS source requires exactly parameter and locator documents"
                )
            parameter_refs = tuple(
                item
                for item in typed_source.input_artifacts
                if item.kind == "oss_stimulation_source_parameters"
            )
            locator_refs = tuple(
                item
                for item in typed_source.input_artifacts
                if item.kind == "oss_stimulation_source_locator"
            )
            if len(parameter_refs) != 1 or len(locator_refs) != 1:
                raise OSSProducerExecutionError(
                    "each OSS source requires one parameter and one locator document"
                )
            parameter = self.artifact_store.materialize_document(
                parameter_refs[0], expected_kind="oss_stimulation_source_parameters"
            )
            locator = self.artifact_store.materialize_document(
                locator_refs[0], expected_kind="oss_stimulation_source_locator"
            )
            parameters.append(parameter)
            locators.append(locator)
            if parameter_refs[0].sha256 != typed_source.stimulation_hash:
                raise OSSProducerExecutionError(
                    "source parameter artifact differs from stimulation_hash"
                )
            boundary_source = self._boundary_source(
                parameter,
                typed_source.source_id,
            )
            expected_frequency_hash = canonical_hash(
                {"frequency_hz": boundary_source.frequency_hz}
            )
            if expected_frequency_hash != typed_source.component_frequency_hash:
                raise OSSProducerExecutionError(
                    "source parameter frequency differs from component_frequency_hash"
                )
            boundary_sources.append(boundary_source)

        geometry = self._shared_geometry(geometries)
        locator = self._shared_locator(locators, request)
        try:
            expected_subject_root = self.subject_roots[request.row.subject_id]
        except KeyError as exc:
            raise OSSProducerExecutionError(
                "producer request subject has no configured subject root"
            ) from exc
        subject_dir = _file_uri_path(
            locator["subject_dir_uri"],
            "subject_dir",
            directory=True,
            allowed_roots=(expected_subject_root,),
        )
        if subject_dir != expected_subject_root:
            raise OSSProducerExecutionError(
                "subject_dir must equal the root configured for the request subject"
            )
        reconstruction_path = _file_uri_path(
            locator["reconstruction_uri"],
            "reconstruction",
            allowed_roots=(subject_dir,),
        )
        reconstruction = self._snapshot(
            reconstruction_path,
            locator["reconstruction_sha256"],
            "reconstruction",
        )
        if _sha256(
            locator["reconstruction_sha256"],
            "locator reconstruction_sha256",
        ) != _sha256(
            geometry["reconstruction_sha256"],
            "geometry reconstruction_sha256",
        ):
            raise OSSProducerExecutionError("geometry and locator reconstruction hashes differ")
        template_segmask_path = _file_uri_path(
            geometry["template_segmask_uri"],
            "template_segmask",
            allowed_roots=(self.repository_root,),
        )
        template_segmask = self._snapshot(
            template_segmask_path,
            geometry["template_segmask_sha256"],
            "template_segmask",
        )
        transform: OSSInputSnapshot | None
        if request.row.side == "L":
            transform_path = _file_uri_path(
                locator["transform_uri"],
                "transform",
                allowed_roots=(self.repository_root,),
            )
            transform = self._snapshot(
                transform_path,
                locator["transform_sha256"],
                "transform",
            )
        else:
            if locator["transform_uri"] is not None:
                raise OSSProducerExecutionError("right locator cannot declare a transform URI")
            transform = None

        return PreparedOSSRow(
            scientific_identity=request.scientific_identity,
            subject_id=request.row.subject_id,
            side=request.row.side,
            frequency_group_id=request.frequency_group_id,
            delivery_mode=request.delivery_mode,
            subject_dir=subject_dir,
            reconstruction_path=reconstruction.path,
            transform_path=None if transform is None else transform.path,
            template_segmask_path=template_segmask.path,
            electrode_model=str(geometry["electrode_model"]),
            reconstruction_lead_id=int(geometry["reconstruction_lead_id"]),
            contact_count=int(geometry["contact_count"]),
            sources=tuple(boundary_sources),
            connectome_path=connectome_snapshot.path,
            connectome_label=self.connectome_label,
            feature_ids=request.row.feature_ids,
            input_snapshots=(
                reconstruction,
                template_segmask,
                connectome_snapshot,
                *((transform,) if transform is not None else ()),
            ),
        )

    @staticmethod
    def _boundary_source(payload: Mapping[str, Any], expected_source_id: str) -> OSSBoundarySource:
        _exact_fields(
            payload,
            {
                "schema_version",
                "source_id",
                "control_mode",
                "amplitude",
                "pulse_width_us",
                "frequency_hz",
                "contacts",
            },
            "source parameter document",
        )
        if payload["schema_version"] != "dual_frequency_oss_source_parameters_v1":
            raise OSSProducerExecutionError("unsupported source parameter schema")
        if str(payload["source_id"]) != expected_source_id:
            raise OSSProducerExecutionError("source parameter ID differs from typed source")
        contacts_payload = payload["contacts"]
        if not isinstance(contacts_payload, list):
            raise OSSProducerExecutionError("source contacts must be a JSON array")
        contacts: list[OSSBoundaryContact] = []
        for item in contacts_payload:
            if not isinstance(item, Mapping):
                raise OSSProducerExecutionError("source contact must be an object")
            _exact_fields(item, {"contact", "polarity", "fraction"}, "source contact")
            contacts.append(
                OSSBoundaryContact(
                    contact=item["contact"],
                    polarity=str(item["polarity"]),
                    fraction=float(item["fraction"]),
                )
            )
        return OSSBoundarySource(
            source_id=str(payload["source_id"]),
            control_mode=str(payload["control_mode"]),
            amplitude=float(payload["amplitude"]),
            pulse_width_us=float(payload["pulse_width_us"]),
            frequency_hz=float(payload["frequency_hz"]),
            contacts=tuple(contacts),
        )

    @staticmethod
    def _shared_geometry(values: list[dict[str, Any]]) -> dict[str, Any]:
        expected = {
            "schema_version",
            "electrode_model",
            "reconstruction_lead_id",
            "contact_count",
            "reconstruction_sha256",
            "template_segmask_uri",
            "template_segmask_sha256",
        }
        for value in values:
            _exact_fields(value, expected, "geometry document")
            if value["schema_version"] != "dual_frequency_oss_geometry_recipe_v1":
                raise OSSProducerExecutionError("unsupported geometry recipe schema")
        first = values[0]
        if any(value != first for value in values[1:]):
            raise OSSProducerExecutionError("continuous sources do not share exact geometry")
        return first

    @staticmethod
    def _shared_locator(
        values: list[dict[str, Any]], request: OSSProducerRequest
    ) -> dict[str, Any]:
        expected = {
            "schema_version",
            "subject_id",
            "phase_id",
            "program_id",
            "electrode_id",
            "frequency_group_id",
            "source_id",
            "subject_dir_uri",
            "reconstruction_uri",
            "reconstruction_sha256",
            "transform_uri",
            "transform_sha256",
            "canonicalization",
        }
        normalized: list[dict[str, Any]] = []
        for value, source in zip(values, request.sources, strict=True):
            _exact_fields(value, expected, "source locator document")
            if value["schema_version"] != "dual_frequency_oss_source_locator_v1":
                raise OSSProducerExecutionError("unsupported source locator schema")
            if (
                str(value["subject_id"]) != request.row.subject_id
                or str(value["frequency_group_id"]) != request.frequency_group_id
                or str(value["source_id"]) != source.source_id
                or str(value["canonicalization"]) != source.canonicalization
                or str(value["transform_sha256"]) != source.transform_hash
            ):
                raise OSSProducerExecutionError("source locator differs from typed producer row")
            shared = dict(value)
            shared.pop("source_id")
            normalized.append(shared)
        first = normalized[0]
        if any(value != first for value in normalized[1:]):
            raise OSSProducerExecutionError("continuous sources do not share one exact locator")
        return values[0]


@dataclass(frozen=True, slots=True)
class OSSExecutableSet:
    matlab: Path
    environment_root: Path
    python: Path
    prepareaxonmodel: Path
    leaddbs2ossdbs: Path
    ossdbs: Path
    run_pathway_activation: Path

    def entrypoint_command(self, executable: Path, *arguments: str) -> tuple[str, ...]:
        allowed = {
            self.prepareaxonmodel,
            self.leaddbs2ossdbs,
            self.ossdbs,
            self.run_pathway_activation,
        }
        if executable not in allowed:
            raise OSSProducerExecutionError("OSS entrypoint is outside the validated set")
        if self.python != self.environment_root / "bin" / "python":
            raise OSSProducerExecutionError(
                "OSS entrypoint interpreter differs from the validated environment"
            )
        return (str(self.python), str(executable), *arguments)


class SubprocessOSSRowExecutor:
    """Execute MATLAB preparation and ten OSS-DBSv2 pPAM samples."""

    def __init__(self, *, work_root: Path, repository_root: Path, environment_file: Path) -> None:
        self.work_root = Path(work_root).expanduser().resolve()
        self.repository_root = Path(repository_root).expanduser().resolve()
        self.environment_file = Path(environment_file).expanduser().resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self._commands: OSSExecutableSet | None = None
        self._command_lock = RLock()

    def execute(self, row: PreparedOSSRow) -> OSSRowProduct:
        if not isinstance(row, PreparedOSSRow):
            raise TypeError("row must be a PreparedOSSRow")
        commands = self._resolve_commands()
        row_parent = self.work_root / row.scientific_identity[:2]
        row_parent.mkdir(parents=True, exist_ok=True)
        work = Path(
            tempfile.mkdtemp(prefix=f".{row.scientific_identity}.tmp-", dir=row_parent)
        )
        completed = False
        try:
            stimulation_root = work / "stimulation"
            connectome_dir = stimulation_root / "connectome"
            filtered = write_filtered_connectome(
                row.connectome_path,
                connectome_dir / "data1.mat",
                row.feature_ids,
            )
            mapping_path = work / "local_to_final_fiber_mapping.json"
            self._write_json(
                mapping_path,
                {
                    "schema_version": "dual_frequency_oss_local_mapping_v1",
                    "parent_connectome_label": row.connectome_label,
                    "parent_fiber_count": filtered.parent_fiber_count,
                    "rows": [
                        {
                            "local_fiber_id": int(local_id),
                            "final_fiber_id": int(feature_id),
                            "final_column_index": int(index),
                        }
                        for index, (local_id, feature_id) in enumerate(
                            zip(
                                filtered.local_fiber_ids.tolist(),
                                filtered.feature_ids.tolist(),
                                strict=True,
                            )
                        )
                    ],
                },
            )
            matlab_manifest = self._prepare_matlab_row(
                row=row,
                work=work,
                stimulation_root=stimulation_root,
                connectome_dir=connectome_dir,
                commands=commands,
            )
            state_paths = self._run_samples(
                row=row,
                work=work,
                parameter_files=matlab_manifest["parameter_files"],
                active_contact_locations=matlab_manifest["active_contact_locations_mm"],
                segmask_path=Path(matlab_manifest["segmask_path"]),
                commands=commands,
                filtered_connectome=filtered.path,
            )
            probabilities = aggregate_activation_probabilities(state_paths, row.feature_ids)
            commands_after = self._resolve_commands()
            if commands_after != commands:
                raise OSSProducerExecutionError(
                    "installed OSS command paths changed during row production"
                )
            completed = True
            return OSSRowProduct(row.feature_ids, probabilities)
        except (ConnectomeSubsetError, OSError, ValueError) as exc:
            raise OSSProducerExecutionError(f"OSS row production failed: {exc}") from exc
        finally:
            if completed:
                shutil.rmtree(work, ignore_errors=True)
            else:
                try:
                    self._write_json(
                        work / "failed.json",
                        {
                            "schema_version": "dual_frequency_oss_failed_work_v1",
                            "scientific_identity": row.scientific_identity,
                            "status": "failed",
                        },
                    )
                except OSError:
                    pass

    def _prepare_matlab_row(
        self,
        *,
        row: PreparedOSSRow,
        work: Path,
        stimulation_root: Path,
        connectome_dir: Path,
        commands: OSSExecutableSet,
    ) -> dict[str, Any]:
        request_path = work / "matlab_request.json"
        manifest_path = work / "matlab_manifest.json"
        payload = {
            "schema_version": "dual_frequency_oss_matlab_request_v1",
            "subject_dir": str(row.subject_dir),
            "reconstruction_path": str(row.reconstruction_path),
            "transform_path": "" if row.transform_path is None else str(row.transform_path),
            "template_segmask_path": str(row.template_segmask_path),
            "stimulation_root": str(stimulation_root),
            "connectome_dir": str(connectome_dir),
            "connectome_label": row.connectome_label,
            "electrode_model": row.electrode_model,
            "reconstruction_lead_id": row.reconstruction_lead_id,
            "contact_count": row.contact_count,
            "side": row.side,
            "frequency_hz": row.frequency_hz,
            "pulse_width_us": row.pulse_width_us,
            "control_mode": row.control_mode,
            "delivery_mode": row.delivery_mode,
            "environment_path": str(commands.environment_root),
            "diameters_um": list(PAM_DIAMETERS_UM),
            "sources": [
                {
                    "source_id": source.source_id,
                    "control_mode": source.control_mode,
                    "amplitude": source.amplitude,
                    "frequency_hz": source.frequency_hz,
                    "pulse_width_us": source.pulse_width_us,
                    "contacts": [
                        {
                            "contact": contact.contact,
                            "polarity": contact.polarity,
                            "fraction": contact.fraction,
                        }
                        for contact in source.contacts
                    ],
                }
                for source in row.sources
            ],
        }
        self._write_json(request_path, payload)
        expression = (
            f"addpath(genpath('{self._matlab_quote(self.repository_root)}'));"
            f"mh_oss_prepare_canonical_row('{self._matlab_quote(request_path)}',"
            f"'{self._matlab_quote(manifest_path)}');"
        )
        self._run(
            (str(commands.matlab), "-batch", expression),
            cwd=work,
            log_prefix=work / "matlab_preflight",
            timeout_seconds=MATLAB_PREP_TIMEOUT_SECONDS,
        )
        manifest = self._read_json(manifest_path)
        expected = {
            "schema_version",
            "parameter_files",
            "stimulation_folder",
            "active_contact_locations_mm",
            "frequency_hz",
            "pulse_width_us",
            "control_mode",
            "segmask_path",
        }
        _exact_fields(manifest, expected, "MATLAB OSS manifest")
        if manifest["schema_version"] != "dual_frequency_oss_matlab_manifest_v1":
            raise OSSProducerExecutionError("unsupported MATLAB OSS manifest")
        if not isinstance(manifest["parameter_files"], list):
            raise OSSProducerExecutionError("MATLAB preflight parameter_files must be an array")
        parameter_files = tuple(Path(value).resolve() for value in manifest["parameter_files"])
        if len(parameter_files) != 10 or len(set(parameter_files)) != 10:
            raise OSSProducerExecutionError("MATLAB preflight must create ten parameter files")
        if not all(path.is_file() and path.is_relative_to(work) for path in parameter_files):
            raise OSSProducerExecutionError("MATLAB preflight parameter files are incomplete")
        if Path(manifest["stimulation_folder"]).resolve() != stimulation_root.resolve():
            raise OSSProducerExecutionError("MATLAB preflight changed the stimulation root")
        segmask_path = Path(manifest["segmask_path"]).resolve()
        if (
            not segmask_path.is_file()
            or not segmask_path.is_relative_to(work)
            or sha256_file(segmask_path) != sha256_file(row.template_segmask_path)
        ):
            raise OSSProducerExecutionError(
                "MATLAB preflight did not preserve the exact template segmentation"
            )
        if float(manifest["frequency_hz"]) != row.frequency_hz:
            raise OSSProducerExecutionError("MATLAB preflight changed source frequency")
        if float(manifest["pulse_width_us"]) != row.pulse_width_us:
            raise OSSProducerExecutionError("MATLAB preflight changed pulse width")
        if str(manifest["control_mode"]).lower() != row.control_mode:
            raise OSSProducerExecutionError("MATLAB preflight changed control mode")
        locations = np.asarray(manifest["active_contact_locations_mm"], dtype=np.float64)
        if locations.ndim != 2 or locations.shape[1] != 3 or not np.all(np.isfinite(locations)):
            raise OSSProducerExecutionError("MATLAB preflight contact locations are invalid")
        return {**manifest, "parameter_files": parameter_files}

    def _run_samples(
        self,
        *,
        row: PreparedOSSRow,
        work: Path,
        parameter_files: tuple[Path, ...],
        active_contact_locations: object,
        segmask_path: Path,
        commands: OSSExecutableSet,
        filtered_connectome: Path,
    ) -> tuple[Path, ...]:
        locations = np.asarray(active_contact_locations, dtype=np.float64).tolist()
        state_paths: list[Path] = []
        for sample_index, (diameter, parameter_file) in enumerate(
            zip(PAM_DIAMETERS_UM, parameter_files, strict=True), start=1
        ):
            sample = work / "samples" / f"sample_{sample_index:02d}"
            hemi = sample / "OSS_sim_files_rh"
            results = hemi / "Results"
            hemi.mkdir(parents=True, exist_ok=True)
            axon_description = sample / "axon_description.json"
            self._write_json(
                axon_description,
                {
                    "pathway_mat_file": [str(filtered_connectome)],
                    "axon_diams_all": [diameter],
                    "axon_lengths_all": [FIXED_AXON_LENGTH_MM],
                    "centering_coordinates": locations,
                    "axon_model": FIXED_AXON_MODEL,
                    "combined_h5_file": str(hemi / "Allocated_axons.h5"),
                    "projection_names": ["default"],
                    "connectome_name": FILTERED_CONNECTOME_LABEL,
                },
            )
            self._run(
                commands.entrypoint_command(
                    commands.prepareaxonmodel,
                    str(sample),
                    "--hemi_side",
                    "0",
                    "--description_file",
                    str(axon_description),
                ),
                cwd=sample,
                log_prefix=sample / "prepareaxonmodel",
                timeout_seconds=AXON_PREP_TIMEOUT_SECONDS,
            )
            pathway_h5 = hemi / "Allocated_axons.h5"
            pathway_json = hemi / "Allocated_axons_parameters.json"
            if not pathway_h5.is_file() or not pathway_json.is_file():
                raise OSSProducerExecutionError(
                    f"sample {sample_index} axon allocation is incomplete"
                )
            self._run(
                commands.entrypoint_command(
                    commands.leaddbs2ossdbs,
                    "--hemi_side",
                    "0",
                    str(parameter_file),
                    "--output_path",
                    str(hemi),
                ),
                cwd=sample,
                log_prefix=sample / "leaddbs2ossdbs",
                timeout_seconds=CONVERTER_TIMEOUT_SECONDS,
            )
            converter_json = self._converter_json(hemi, parameter_file)
            converter = self._read_json(converter_json)
            converter["StimulationFolder"] = str(sample)
            converter["OutputPath"] = str(results)
            converter["ModelSide"] = 0
            converter["FailFlag"] = "rh"
            converter["PathwayFile"] = str(pathway_json)
            converter.setdefault("PointModel", {}).setdefault("Pathway", {})[
                "FileName"
            ] = str(pathway_h5)
            converter.setdefault("StimulationSignal", {})["Frequency[Hz]"] = row.frequency_hz
            self._validate_converter_contract(
                converter,
                row=row,
                segmask_path=segmask_path,
                pathway_h5=pathway_h5,
                pathway_json=pathway_json,
                output_path=results,
            )
            self._write_json(converter_json, converter)
            if float(self._read_json(converter_json)["StimulationSignal"]["Frequency[Hz]"]) != row.frequency_hz:
                raise OSSProducerExecutionError("converter frequency patch did not persist")
            self._run(
                commands.entrypoint_command(
                    commands.ossdbs,
                    str(converter_json),
                ),
                cwd=sample,
                log_prefix=sample / "ossdbs",
                timeout_seconds=OSS_SOLVER_TIMEOUT_SECONDS,
            )
            if not (results / "oss_time_result_PAM.h5").is_file():
                raise OSSProducerExecutionError(
                    f"sample {sample_index} OSS field result is missing"
                )
            self._run(
                commands.entrypoint_command(
                    commands.run_pathway_activation,
                    str(converter_json),
                    "--scaling_index",
                    str(sample_index),
                    "--scaling",
                    "1.0",
                ),
                cwd=sample,
                log_prefix=sample / "run_pathway_activation",
                timeout_seconds=PATHWAY_ACTIVATION_TIMEOUT_SECONDS,
            )
            state_paths.append(self._axon_state(results, sample_index))
        return tuple(state_paths)

    @staticmethod
    def _validate_converter_contract(
        converter: Mapping[str, Any],
        *,
        row: PreparedOSSRow,
        segmask_path: Path,
        pathway_h5: Path,
        pathway_json: Path,
        output_path: Path,
    ) -> None:
        try:
            material = converter["MaterialDistribution"]
            dielectric = converter["DielectricModel"]
            signal = converter["StimulationSignal"]
            pathway = converter["PointModel"]["Pathway"]
        except (KeyError, TypeError) as exc:
            raise OSSProducerExecutionError(
                "converter JSON lacks required scientific settings"
            ) from exc
        if not all(isinstance(value, Mapping) for value in (material, dielectric, signal, pathway)):
            raise OSSProducerExecutionError(
                "converter scientific settings must be JSON objects"
            )
        try:
            mri_path = Path(str(material["MRIPath"])).resolve(strict=True)
        except (KeyError, OSError, RuntimeError) as exc:
            raise OSSProducerExecutionError(
                "converter MRIPath is unavailable"
            ) from exc
        expected_segmask = Path(segmask_path).resolve(strict=True)
        if mri_path != expected_segmask or sha256_file(mri_path) != sha256_file(
            row.template_segmask_path
        ):
            raise OSSProducerExecutionError(
                "converter did not preserve the exact template segmentation"
            )
        expected_mapping = {"Unknown": 0, "CSF": 3, "White matter": 2, "Gray matter": 1, "Blood": 4}
        if (
            material.get("MRIMapping") != expected_mapping
            or material.get("DiffusionTensorActive") is not False
            or material.get("DTIPath") != ""
            or dielectric.get("Type") != FIXED_CONDUCTIVITY_MODEL
            or dielectric.get("CustomParameters") is not None
        ):
            raise OSSProducerExecutionError(
                "converter changed the fixed isotropic tissue contract"
            )
        if (
            signal.get("Type") != "Rectangle"
            or signal.get("CurrentControlled") is not (row.control_mode == "current")
            or float(signal.get("Frequency[Hz]", math.nan)) != row.frequency_hz
            or float(signal.get("PulseWidth[us]", math.nan)) != row.pulse_width_us
            or float(signal.get("PulseTopWidth[us]", math.nan)) != 0.0
            or float(signal.get("CounterPulseWidth[us]", math.nan)) != 0.0
            or float(signal.get("InterPulseWidth[us]", math.nan)) != 0.0
        ):
            raise OSSProducerExecutionError(
                "converter changed the fixed stimulation waveform"
            )
        if (
            converter.get("CalcAxonActivation") is not True
            or pathway.get("Active") is not True
            or Path(str(pathway.get("FileName", ""))).resolve() != pathway_h5.resolve()
            or Path(str(converter.get("PathwayFile", ""))).resolve() != pathway_json.resolve()
            or Path(str(converter.get("OutputPath", ""))).resolve() != output_path.resolve()
            or converter.get("ModelSide") != 0
        ):
            raise OSSProducerExecutionError(
                "converter changed the fixed pathway execution contract"
            )

    def _resolve_commands(self) -> OSSExecutableSet:
        with self._command_lock:
            try:
                environment = yaml.safe_load(self.environment_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
                raise OSSProducerExecutionError("OSS environment definition is unreadable") from exc
            if not isinstance(environment, dict):
                raise OSSProducerExecutionError("OSS environment definition must be an object")
            env_name = _token(environment.get("name", ""), "OSS env name")
            variables = environment.get("variables")
            if not isinstance(variables, Mapping):
                raise OSSProducerExecutionError("OSS environment lock variables are missing")
            expected_commit = _git_commit(variables.get("ossdbs_commit"), "ossdbs_commit")
            expected_source_hash = _sha256(
                variables.get("ossdbs_source_tree_sha256"),
                "ossdbs_source_tree_sha256",
            )
            expected_entrypoint_hash = _sha256(
                variables.get("ossdbs_entrypoints_sha256"),
                "ossdbs_entrypoints_sha256",
            )
            expected_conda_hash = _sha256(
                variables.get("ossdbs_conda_explicit_sha256"),
                "ossdbs_conda_explicit_sha256",
            )
            expected_conda_count = _positive_integer(
                variables.get("ossdbs_conda_explicit_count"),
                "ossdbs_conda_explicit_count",
            )
            expected_pip_hash = _sha256(
                variables.get("ossdbs_pip_freeze_sha256"),
                "ossdbs_pip_freeze_sha256",
            )
            expected_pip_count = _positive_integer(
                variables.get("ossdbs_pip_freeze_count"),
                "ossdbs_pip_freeze_count",
            )
            expected_matlab = {
                "version": _token(variables.get("matlab_version"), "matlab_version"),
                "release": _token(variables.get("matlab_release"), "matlab_release"),
                "computer": _token(variables.get("matlab_computer"), "matlab_computer"),
            }
            expected_ants_hash = _sha256(
                variables.get("ants_apply_transforms_to_points_sha256"),
                "ants_apply_transforms_to_points_sha256",
            )
            pip_entries = tuple(
                str(item)
                for dependency in environment.get("dependencies", ())
                if isinstance(dependency, Mapping)
                for item in dependency.get("pip", ())
            )
            expected_pin = f"git+https://github.com/SFB-ELAINE/OSS-DBSv2.git@{expected_commit}"
            if pip_entries.count(expected_pin) != 1:
                raise OSSProducerExecutionError(
                    "OSS environment definition must pin exactly the locked commit"
                )
            conda = shutil.which("conda")
            if conda is None:
                raise OSSProducerExecutionError("conda is required for an authorized OSS miss")
            if self._commands is None:
                return_code, stdout, _stderr = _capture_process(
                    (conda, "env", "list", "--json"),
                    timeout_seconds=60.0,
                    label="Conda environment inventory",
                )
                if return_code != 0:
                    raise OSSProducerExecutionError("cannot enumerate Conda environments")
                try:
                    roots = tuple(Path(value).resolve() for value in json.loads(stdout)["envs"])
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise OSSProducerExecutionError("Conda environment inventory is invalid") from exc
                matches = tuple(path for path in roots if path.name.lower() == env_name.lower())
                if len(matches) != 1:
                    raise OSSProducerExecutionError(
                        f"expected one installed {env_name!r} environment; found {len(matches)}"
                    )
                env_root = matches[0]
                matlab_value = shutil.which("matlab")
                if matlab_value is None:
                    candidates = sorted(Path("/Applications").glob("MATLAB_R*.app/bin/matlab"))
                    if not candidates:
                        raise OSSProducerExecutionError("MATLAB executable is unavailable")
                    matlab = candidates[-1].resolve()
                else:
                    matlab = Path(matlab_value).resolve()
                executable_paths = {
                    name: env_root / "bin" / name
                    for name in (
                        "prepareaxonmodel",
                        "leaddbs2ossdbs",
                        "ossdbs",
                        "run_pathway_activation",
                    )
                }
                self._commands = OSSExecutableSet(
                    matlab=matlab,
                    environment_root=env_root,
                    python=env_root / "bin" / "python",
                    prepareaxonmodel=executable_paths["prepareaxonmodel"],
                    leaddbs2ossdbs=executable_paths["leaddbs2ossdbs"],
                    ossdbs=executable_paths["ossdbs"],
                    run_pathway_activation=executable_paths["run_pathway_activation"],
                )
            commands = self._commands
            env_root = commands.environment_root
            matlab = commands.matlab
            environment_python = commands.python
            executable_paths = {
                "prepareaxonmodel": commands.prepareaxonmodel,
                "leaddbs2ossdbs": commands.leaddbs2ossdbs,
                "ossdbs": commands.ossdbs,
                "run_pathway_activation": commands.run_pathway_activation,
            }
            if not matlab.is_file() or any(not path.is_file() for path in executable_paths.values()):
                raise OSSProducerExecutionError("installed OSS toolchain is incomplete")
            if (
                environment_python != env_root / "bin" / "python"
                or not environment_python.is_file()
            ):
                raise OSSProducerExecutionError("installed OSS Python executable is unavailable")
            site_candidates = tuple(
                sorted(
                    {
                        path.resolve()
                        for path in (
                            *sorted(
                                (env_root / "lib").glob("python*/site-packages")
                            ),
                            env_root / "Lib" / "site-packages",
                        )
                        if path.is_dir()
                    }
                )
            )
            if len(site_candidates) != 1:
                raise OSSProducerExecutionError(
                    "installed OSS environment must expose one site-packages directory"
                )
            site_packages = site_candidates[0]
            direct_urls = tuple(
                sorted(site_packages.glob("ossdbs-*.dist-info/direct_url.json"))
            )
            if len(direct_urls) != 1:
                raise OSSProducerExecutionError(
                    "installed OSS distribution lacks one direct_url lock"
                )
            direct_url = self._read_json(direct_urls[0])
            try:
                installed_commit = _git_commit(
                    direct_url["vcs_info"]["commit_id"],
                    "installed OSS commit",
                )
            except (KeyError, TypeError) as exc:
                raise OSSProducerExecutionError(
                    "installed OSS distribution lacks Git commit provenance"
                ) from exc
            if installed_commit != expected_commit:
                raise OSSProducerExecutionError(
                    "installed OSS commit differs from OSS-DBSv2.yml"
                )
            try:
                installed_source_hash = _hash_oss_source_tree(site_packages)
                installed_entrypoint_hash = _hash_oss_entrypoints(executable_paths)
            except OSError as exc:
                raise OSSProducerExecutionError(
                    "installed OSS implementation cannot be hashed"
                ) from exc
            if installed_source_hash != expected_source_hash:
                raise OSSProducerExecutionError(
                    "installed OSS source tree differs from OSS-DBSv2.yml"
                )
            if installed_entrypoint_hash != expected_entrypoint_hash:
                raise OSSProducerExecutionError(
                    "installed OSS entrypoints differ from OSS-DBSv2.yml"
                )
            conda_code, conda_stdout, _conda_stderr = _capture_process(
                (conda, "list", "--prefix", str(env_root), "--explicit"),
                timeout_seconds=120.0,
                label="Conda explicit environment lock",
            )
            if conda_code != 0:
                raise OSSProducerExecutionError("cannot inspect the installed Conda lock")
            conda_count, conda_hash = _normalized_inventory(
                conda_stdout,
                ignore_comments=True,
            )
            if conda_count != expected_conda_count or conda_hash != expected_conda_hash:
                raise OSSProducerExecutionError(
                    "installed Conda package set differs from OSS-DBSv2.yml"
                )
            pip_code, pip_stdout, _pip_stderr = _capture_process(
                (str(environment_python), "-m", "pip", "freeze", "--all"),
                timeout_seconds=120.0,
                label="Python distribution lock",
            )
            if pip_code != 0:
                raise OSSProducerExecutionError("cannot inspect the installed Python lock")
            pip_count, pip_hash = _normalized_inventory(
                pip_stdout,
                ignore_comments=False,
            )
            if pip_count != expected_pip_count or pip_hash != expected_pip_hash:
                raise OSSProducerExecutionError(
                    "installed Python distribution set differs from OSS-DBSv2.yml"
                )
            matlab_expression = (
                "fprintf('OSS_MATLAB_VERSION=%s\\n',version);"
                "fprintf('OSS_MATLAB_RELEASE=%s\\n',version('-release'));"
                "fprintf('OSS_MATLAB_COMPUTER=%s\\n',computer);"
            )
            matlab_code, matlab_stdout, _matlab_stderr = _capture_process(
                (str(matlab), "-batch", matlab_expression),
                timeout_seconds=180.0,
                label="MATLAB runtime identity",
            )
            if matlab_code != 0:
                raise OSSProducerExecutionError("cannot inspect the MATLAB runtime")
            matlab_identity: dict[str, str] = {}
            for line in matlab_stdout.splitlines():
                if line.startswith("OSS_MATLAB_") and "=" in line:
                    key, value = line.split("=", 1)
                    matlab_identity[key.removeprefix("OSS_MATLAB_").lower()] = value.strip()
            if matlab_identity != expected_matlab:
                raise OSSProducerExecutionError(
                    "installed MATLAB runtime differs from OSS-DBSv2.yml"
                )
            ants_suffix = {
                "MACA64": "maca64",
                "MACI64": "maci64",
                "GLNXA64": "glnxa64",
                "PCWIN64": "exe",
            }.get(expected_matlab["computer"])
            if ants_suffix is None:
                raise OSSProducerExecutionError("MATLAB platform lacks a locked ANTs binary")
            ants_path = (
                self.repository_root
                / "ext_libs"
                / "ANTs"
                / f"antsApplyTransformsToPoints.{ants_suffix}"
            )
            if not ants_path.is_file() or _stable_file_hash(ants_path) != expected_ants_hash:
                raise OSSProducerExecutionError(
                    "installed ANTs point-transform binary differs from OSS-DBSv2.yml"
                )
            return commands

    @staticmethod
    def _converter_json(hemi: Path, parameter_file: Path) -> Path:
        expected = hemi / f"{parameter_file.stem}.json"
        if expected.is_file():
            return expected
        candidates = tuple(
            path for path in sorted(hemi.glob("*.json")) if "parameter" in path.stem.lower()
        )
        if len(candidates) != 1:
            raise OSSProducerExecutionError("converter did not create one parameter JSON")
        return candidates[0]

    @staticmethod
    def _axon_state(results: Path, sample_index: int) -> Path:
        candidates = tuple(sorted(results.glob(f"Axon_state_*_{sample_index}.mat"))) + tuple(
            sorted(results.glob(f"Axon_state_*_{sample_index}.csv"))
        )
        stems = {path.stem for path in candidates}
        if len(stems) != 1:
            raise OSSProducerExecutionError(
                f"sample {sample_index} did not produce one Axon_state result"
            )
        mats = tuple(path for path in candidates if path.suffix.lower() == ".mat")
        return mats[0] if mats else candidates[0]

    @staticmethod
    def _run(
        command: tuple[str, ...],
        *,
        cwd: Path,
        log_prefix: Path,
        timeout_seconds: float,
    ) -> None:
        log_prefix.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = log_prefix.with_suffix(".stdout.log")
        stderr_path = log_prefix.with_suffix(".stderr.log")
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
            process_group_id = process.pid if os.name == "posix" else None
            try:
                return_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                _terminate_process_group(
                    process,
                    process_group_id=process_group_id,
                )
                raise OSSProducerExecutionError(
                    f"external OSS command timed out ({Path(command[0]).name})"
                ) from exc
        if return_code != 0:
            raise OSSProducerExecutionError(
                f"external OSS command failed ({Path(command[0]).name}, "
                f"returncode={return_code})"
            )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OSSProducerExecutionError(f"JSON document is unreadable: {path}") from exc
        if not isinstance(payload, dict):
            raise OSSProducerExecutionError(f"JSON document must contain an object: {path}")
        return payload

    @staticmethod
    def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        os.close(temporary_descriptor)
        temporary = Path(temporary_name)
        try:
            temporary.write_text(
                json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _matlab_quote(path: Path) -> str:
        return str(Path(path).resolve()).replace("'", "''")


__all__ = [
    "FIXED_AXON_LENGTH_MM",
    "FIXED_AXON_MODEL",
    "FIXED_CONDUCTIVITY_MODEL",
    "FILTERED_CONNECTOME_LABEL",
    "LeadDBSOSSProducerToolchain",
    "OSSBoundaryContact",
    "OSSBoundarySource",
    "OSSExecutableSet",
    "OSSProducerExecutionError",
    "OSSRowExecutor",
    "PAM_DIAMETERS_UM",
    "PreparedOSSRow",
    "SubprocessOSSRowExecutor",
]
