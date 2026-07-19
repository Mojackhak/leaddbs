"""Generic direct-voxel scientific backends."""

from .addon import (
    AddonDirectVoxelBackend,
    AddonDirectVoxelBackendError,
    AddonDirectVoxelDesignError,
    build_addon_nuisance_plan,
    evaluate_addon_grid,
)
from .kernel import (
    DirectVoxelGridWorkspace,
    DirectVoxelKernelError,
    GridCellArrays,
    GridCellComputation,
    GridCellMetrics,
    NuisancePlan,
    classify_prediction_status,
    evaluate_grid,
    evaluate_grid_cell,
    evaluate_grid_cell_with_nuisance_plan,
)
from .reference import ReferenceDirectVoxelBackend, ReferenceDirectVoxelBackendError
from .source_resolver import SourceResolution, SourceResolverError, resolve_source

__all__ = [
    "AddonDirectVoxelBackend",
    "AddonDirectVoxelBackendError",
    "AddonDirectVoxelDesignError",
    "DirectVoxelGridWorkspace",
    "DirectVoxelKernelError",
    "GridCellArrays",
    "GridCellComputation",
    "GridCellMetrics",
    "NuisancePlan",
    "ReferenceDirectVoxelBackend",
    "ReferenceDirectVoxelBackendError",
    "SourceResolution",
    "SourceResolverError",
    "build_addon_nuisance_plan",
    "classify_prediction_status",
    "evaluate_addon_grid",
    "evaluate_grid",
    "evaluate_grid_cell",
    "evaluate_grid_cell_with_nuisance_plan",
    "resolve_source",
]
