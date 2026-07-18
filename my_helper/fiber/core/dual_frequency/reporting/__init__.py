"""Record-driven reporting primitives for generic dual-frequency runs."""

from .artifact_index import (
    ArtifactIndexError,
    ReportingError,
    build_artifact_index,
    record_artifact_closure,
)
from .endpoint_summary import (
    DECISION_STATUSES,
    FinalDecisionRecord,
    aggregate_final_decisions,
    build_endpoint_summary,
    build_final_decisions,
    final_decisions_document,
)
from .formal_in_sample import (
    FormalInSampleReportingError,
    build_formal_in_sample_results,
    formal_in_sample_results_csv,
)
from .run_report import (
    build_report_documents,
    build_reporting_documents,
    build_run_report,
)

__all__ = [
    "ArtifactIndexError",
    "DECISION_STATUSES",
    "FinalDecisionRecord",
    "FormalInSampleReportingError",
    "ReportingError",
    "aggregate_final_decisions",
    "build_artifact_index",
    "build_endpoint_summary",
    "build_final_decisions",
    "build_formal_in_sample_results",
    "build_report_documents",
    "build_reporting_documents",
    "build_run_report",
    "final_decisions_document",
    "formal_in_sample_results_csv",
    "record_artifact_closure",
]
