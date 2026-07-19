"""Frozen configuration models for approved public YAML fields."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkflowOverrides:
    """Explicit CLI selection and execution overrides."""

    scales: tuple[str, ...] = ()
    all_available: bool = False
    models: tuple[str, ...] = ()
    connectomes: tuple[str, ...] = ()
    through: str | None = None
    resume: bool | None = None
    force: bool | None = None
    allow_expensive_producers: bool | None = None
    workers: int | None = None


@dataclass(frozen=True)
class OutputProfile:
    root: Path


@dataclass(frozen=True)
class EndpointBinding:
    phase_id: str
    program_id: int

    @property
    def identifier(self) -> str:
        return f"phase-{self.phase_id}_program-{self.program_id}"


@dataclass(frozen=True)
class EndpointPair:
    baseline: EndpointBinding
    reference: EndpointBinding
    addon: EndpointBinding


@dataclass(frozen=True)
class FrequencyInterval:
    lower: float | None
    lower_inclusive: bool
    upper: float | None
    upper_inclusive: bool

    def contains(self, frequency_hz: float) -> bool:
        lower_ok = self.lower is None or (
            frequency_hz >= self.lower if self.lower_inclusive else frequency_hz > self.lower
        )
        upper_ok = self.upper is None or (
            frequency_hz <= self.upper if self.upper_inclusive else frequency_hz < self.upper
        )
        return lower_ok and upper_ok


@dataclass(frozen=True)
class FrequencyClasses:
    reference: FrequencyInterval
    addon: FrequencyInterval

    def classify(self, frequency_hz: float) -> str:
        if self.reference.contains(frequency_hz):
            return "reference"
        if self.addon.contains(frequency_hz):
            return "addon"
        return "unclassified"


@dataclass(frozen=True)
class SourceCell:
    tau: float
    coverage: int


@dataclass(frozen=True)
class SourceResolverProfile:
    pre_specified: SourceCell
    tau_values: tuple[float, ...]
    coverage_values: tuple[int, ...]
    minimum_adjacent_passing_cells: int


@dataclass(frozen=True)
class HardComputabilityProfile:
    n_subjects_min: int
    n_features_full_min: int | None = None
    fold_n_features_min: int | None = None


@dataclass(frozen=True)
class FormalResamplingProfile:
    seed: int
    permutation_resamples: int
    bootstrap_resamples: int
    jitter_resamples: int
    jitter_translation_fwhm_mm: float


@dataclass(frozen=True)
class AdequateSupportProfile:
    cohort_median_out_support_max: float
    subject_out_support_threshold: float
    subject_fraction_max: float


@dataclass(frozen=True)
class InvalidSupportProfile:
    cohort_median_out_support_min_exclusive: float
    subject_out_support_threshold: float
    subject_fraction_min_exclusive: float
    individual_out_support_min_exclusive: float


@dataclass(frozen=True)
class DeltaReferenceSupportProfile:
    adequate: AdequateSupportProfile
    invalid: InvalidSupportProfile


@dataclass(frozen=True)
class DirectVoxelModelProfile:
    schema_version: str
    model_set_id: str
    output: OutputProfile
    scales: tuple[str, ...]
    endpoint_pair: EndpointPair
    frequency_classes: FrequencyClasses
    source: SourceResolverProfile
    hard_computability: HardComputabilityProfile
    formal_resampling: FormalResamplingProfile
    selected_source_tau_multipliers: tuple[float, ...]
    delta_reference_support: DeltaReferenceSupportProfile

    @property
    def direct_candidate_threshold_v_per_m(self) -> float:
        return min(self.source.tau_values)


@dataclass(frozen=True)
class ConnectomeProfile:
    connectome_id: str
    label: str
    path: Path
    role: str
    fold_candidate_fibers_min: int


@dataclass(frozen=True)
class FiberScoreProfile:
    sweet_fraction: float
    sour_fraction: float
    weighted_peak_fraction: float
    sweet_selected_min_count: int
    sour_selected_min_count: int
    weighted_peak_min_count: int


@dataclass(frozen=True)
class FixedOuterLibraryProfile:
    sweet_count: int
    sour_count: int


@dataclass(frozen=True)
class FiberSensitivityProfile:
    selected_source_tau_multipliers: tuple[float, ...]
    high_threshold: SourceCell
    fixed_outer_library: FixedOuterLibraryProfile


@dataclass(frozen=True)
class FiberDiameterProfile:
    minimum: float
    maximum: float
    samples: int
    sampling: str


@dataclass(frozen=True)
class OssProfile:
    model: str
    activation_model: str
    fiber_diameter_um: FiberDiameterProfile
    fitting_probability_threshold: float
    permutation_resamples: int


@dataclass(frozen=True)
class NormativeFiberModelProfile:
    schema_version: str
    model_set_id: str
    output: OutputProfile
    scales: tuple[str, ...]
    endpoint_pair: EndpointPair
    frequency_classes: FrequencyClasses
    connectomes: tuple[ConnectomeProfile, ...]
    source: SourceResolverProfile
    hard_computability: HardComputabilityProfile
    score: FiberScoreProfile
    formal_resampling: FormalResamplingProfile
    sensitivity: FiberSensitivityProfile
    oss: OssProfile
    delta_reference_support: DeltaReferenceSupportProfile

    @property
    def formal_connectome(self) -> ConnectomeProfile:
        return next(item for item in self.connectomes if item.role == "formal")


@dataclass(frozen=True)
class WorkflowSelection:
    models: tuple[str, ...]
    connectomes: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionProfile:
    through: str
    resume: bool
    force: bool
    continue_on_endpoint_failure: bool
    allow_expensive_producers: bool
    workers: int


@dataclass(frozen=True)
class StorageProfile:
    cache_root: Path
    run_root: Path
    delete_run_cache_on_success: bool


@dataclass(frozen=True)
class WorkflowProfile:
    direct_voxel_model_path: Path
    normative_fiber_model_path: Path
    selection: WorkflowSelection
    execution: ExecutionProfile
    storage: StorageProfile


@dataclass(frozen=True)
class ResolvedWorkflow:
    direct_voxel: DirectVoxelModelProfile
    normative_fiber: NormativeFiberModelProfile
    workflow: WorkflowProfile
    selected_scales: tuple[str, ...]
    selected_models: tuple[str, ...]
    selected_connectomes: tuple[str, ...]
    configuration_hash: str
    scientific_configuration_hash: str
    source_paths: tuple[Path, ...]
