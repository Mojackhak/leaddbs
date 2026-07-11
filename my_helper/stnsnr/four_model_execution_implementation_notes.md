# Four-Model Execution Implementation Notes

This note records executable implementation layers for `four_model_execution_plan.md`.

## YAML Core Refactor: Implementation In Progress

The future configuration and orchestration contract is documented in:

```text
my_helper/stnsnr/four_model_yaml_core_refactor_plan.md
my_helper/stnsnr/four_model_yaml_core_refactor_implementation_plan.md
my_helper/stnsnr/normative_fiber_minimum_count_scoring_design.md
my_helper/stnsnr/normative_fiber_minimum_count_scoring_implementation_plan.md
```

Current status:

```text
design_documented
implementation_in_progress
current_outputs_unchanged
current_legacy_entrypoints_remain_active
```

The legacy/current production drivers and consolidated status/formal layers
still contain single-scale defaults, total/axial default lists, chronic-total
path assumptions, or global A/B status rows. The configured YAML pipeline now
isolates those compatibility entrypoints behind an endpoint catalog, composite
task identities, matched A-to-C and connectome-specific B-to-D dependencies,
and endpoint-aware final/formal/reporting artifacts. All configured scales use
the same task factories and status fields; no clinical reporting hierarchy
changes execution.

The configured public YAML and CLI do not accept
`candidate_threshold_v_per_m`. Direct-voxel preprocessing will derive it as
`min(tau_grid_v_per_m)` and record the value as internal-derived technical
metadata. Normative fiber will not define a global candidate threshold.
Optimized-versus-brute-force equivalence and smoke
permutation/bootstrap/jitter remain internal-test parameters rather than public
workflow inputs.

Implemented layers now include strict JSON Schemas and typed YAML loading,
immutable endpoint/task/final identities, the profile-driven endpoint catalog,
pure HF-derived ULF branch/final transitions, the namespaced run store,
Round-aware planner, generic CLI/executor, all four configured scientific model
services, final-model realization, formal and sensitivity adapters, the
final-record-bound OSS producer/consumer, and endpoint-aware numeric reporting.
They include typed dependency gates, endpoint-local continuation, resume/force
lineage, artifact identity checks, and legacy-root write protection. Legacy
wrappers remain explicit compatibility entrypoints; output migration is not
performed. The real two-scale acceptance run remains pending. ROI/VTA
postprocessing and GUI remain outside this core refactor.

The configured DAG interface uses operation-specific task stages, logical workflow
phases, typed dependency requirements (`terminal`, `success`,
`accepted_final`, and `formal_complete`), and explicit runtime gates. This is
required so an absent/failed HF dependency can release `no_delta_hf`, while
adjusted, formal, OSS, and jitter tasks retain stricter input/final-state
requirements without changing task identity.

Final implementation acceptance is now required to run the ordinary generic
pipeline with both `mds_updrs_iii_score` (`MDS-UPDRS III score`) and
`mds_updrs_iv` (`MDS-UPDRS IV`) in one profile. This pair is an acceptance
fixture, not a default or privileged scale list. The current clinical source has
chronic rows for both scales and immediate rows for MDS-UPDRS III only; the
endpoint catalog represents the missing MDS-UPDRS IV immediate family explicitly
without cross-scale substitution. The read-only catalog acceptance for the
frozen clinical workbook is implemented and confirms 16 chronic subjects for
both scales, 16 immediate pairs for MDS-UPDRS III, and no configured MDS-UPDRS
IV immediate endpoint. The full two-scale model execution and report acceptance
remain pending.

The first real report-through attempt, run
`20260710T143933Z_6b8054589fd9e59b`, exposed an acceptance-only interface gap:
direct-voxel qualification attempted to read normative-fiber `scores_csv`
instead of `DirectVoxelTarget.subjects_csv`. Endpoint isolation worked and
later endpoint work continued, but that run is not acceptance evidence. The
reader now supports both explicit target contracts and rejects conflicting
dual paths. Its focused RED/GREEN test, all 301 configured-core tests, the
direct formal-permutation selftest, compilation, and `git diff --check` pass. A
new clean-provenance acceptance run is still required.

The second real attempt, run `20260710T151202Z_8d4e5419ee4ba1c2`, completed the
repaired HF direct-voxel path and the first dTOR HF-fiber observed/resolver,
smoke, and formal tasks. Its OSS producer then failed because it tried to read
legacy `outputs.mapping_qc_json` from a configured selected manifest. In the
configured pipeline, stimulation source rows are owned by the exact endpoint-
local sidecar QC artifact and are registered in the run artifact index. The
producer must consume and hash-validate that artifact rather than infer a legacy
path from the final manifest.

This repair is implemented for both model families. HF resolves the unique
completed `sidecar_equivalence` QC artifact; ULF resolves the unique completed
`preprocessing_sidecars` QC artifact. The run-local path and SHA-256 must match
the artifact index before source rows are accepted. Focused HF/ULF/tamper tests,
all 304 configured-core tests, Python compilation, and `git diff --check` pass.

The third real attempt, run `20260710T155953Z_b57d513ff60da8e0`, confirmed the
source-row repair and entered actual MATLAB OSS parameter preparation. It
failed because current `ea_get_oss_outputPaths` does not create the later-stage
`HemiSimFolder` field before `ea_updatePAM_parameter` needs it. Configured OSS
is always right-canonical, so preflight must bind the sample workspace to
`fullfile(outputPaths.outputDir, 'OSS_sim_files_rh')` explicitly before the
fixed ten-sample loop.

The explicit right-canonical workspace repair passes the generated-script
contract and all 304 configured-core tests. A separate real SNr003 left-source
diagnostic also completed parameter preflight, converter frequency correction,
candidate filtering, all ten OSS/pathway samples, and pPAM aggregation on the
3,990-fiber valid axis with zero invalid mapping columns. This diagnostic proves
the toolchain boundary but does not replace the required namespaced III/IV run.

The committed profiles under `my_helper/stnsnr/config/four_model_v1/` enumerate
all 28 scales currently present in the frozen clinical workbook. The workflow
selects MDS-UPDRS III/IV only as the required acceptance pair; this does not
create a code default or alter any task factory.

Subagents are permitted during implementation when each delegated task
has a bounded responsibility and disjoint file ownership. The main thread must
review and integrate all delegated work and remains solely responsible for the
full regression suite, two-scale acceptance workflow, and final `/goal`
completion audit.

The full four-model program is intentionally gated. The current codebase now
includes readiness, observed A/B/C/D branches, C/D source resolvers,
consolidated status reporting, final-model worklist/readiness auditing, formal
permutation/bootstrap/jitter layers for available final targets, dTOR
normative-fiber FDR/enrichment caches for the formal final targets, final
reporting/readiness summaries, and shared resolver utilities. Optional
observed-robustness-row FDR/enrichment display outputs remain deferred until
those rows are explicitly promoted and their required caches exist.

## Pause Checkpoint

2026-07-07 post-pause refresh: final-reporting readiness now requires separate
FDR and enrichment caches before a normative-fiber row can be reported as full
fiber figure-output ready. This is a figure-output/display requirement, not a
source-resolver, prediction-status, final-model, OSS, or jitter gate. Density
plus connected-region labels remains `ready_for_density_label_outputs` only.
Final reporting, all-endpoint reporting, manifest schema audit, and completion
audit were regenerated from clean commit `1d34cb9f3`.
Here, `ready_for_full_fiber_figure_outputs` is limited to the
density/label/FDR/enrichment figure-cache layer. OSS activation sensitivity is
tracked separately and can remain `not_run_missing_oss_inputs` for the same row.

Exact input/cache searches after that refresh found no `X_oss_float32_fiber_major.npy`,
`oss_parameter_manifest.json`, `oss_activation_sidecar_metadata.json`, fiber
jitter sidecar/cache files, FDR cache files, or enrichment cache files under the
then-current `/Volumes/VAL/STNSNr` summary tree. Later 2026-07-08 runs generated
formal jitter QC and FDR/enrichment caches for B_DTOR and D_DTOR. Their current
normative-fiber execution-completion blocker is OSS missing input only, not
branch-selection ambiguity, not FDR/enrichment cache availability, and not
jitter QC.

The OSS / pPAM sidecar generation contract is now documented in
`my_helper/stnsnr/normative_fiber_oss_ppam_generation_plan.md`. The configured
producer binds float32 p(A) `X_oss_float32_fiber_major.npy` to the immutable
realized-final valid fiber axis. It transforms left electrode/stimulation
geometry and reconstruction coordinates into right-canonical space with
`ea_flip_lr_nonlinear`, runs both sides on the same ordered axis, and merges
probabilities with `max_probability_union`; it never assumes local left/right
fiber-ID homology. Ten complete equidistant Fiber Diameter samples over
`[1, 4]` micrometers produce exact `activated_count / 10` probabilities, and
fitting uses `I[p(A) >= 0.5]`. A parent raw `fiber_ids.npy` is not the OSS column
contract. The downstream sensitivity recomputes weights and the shared
`200/100/20` score within every training fold without changing the peak-E-field
final model.

2026-07-07 density/label-cache update: the normative-fiber density and
connected-region label caches now default to all `analysis_family =
normative_fiber` rows in the final report. The density/label-cache, final
reporting, schema audit, and completion audit outputs have been regenerated
from this all-row behavior.

Execution has resumed through the 2026-07-07 status, formal-target, and
formal-readiness refresh. The latest observed branches and status files were
regenerated from the single retained worktree:

```text
/Users/mojackhu/Github/leaddbs
```

Current refreshed outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/gate_status/four_model_gate_status.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/status/four_model_execution_status.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/status/four_model_execution_status.md
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/four_model_formal_target_worklist.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/four_model_formal_target_worklist.md
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/four_model_formal_readiness.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/four_model_formal_readiness.md
/Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_permutation/direct_voxel_formal_permutation_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_bootstrap/direct_voxel_formal_bootstrap_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_jitter/direct_voxel_formal_jitter_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_smoke_permutation/normative_fiber_smoke_permutation_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_formal_permutation/normative_fiber_formal_permutation_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_formal_bootstrap/normative_fiber_formal_bootstrap_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_sensitivity_readiness/normative_fiber_sensitivity_readiness_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_figure_output_readiness.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_missing_work.csv
```

Current state:

```text
A direct voxel: SOURCE_ACCEPTED_ERROR_NONPREDICTIVE
B PPMI/MGH/dTOR normative fiber: SOURCE_ACCEPTED_ERROR_NONPREDICTIVE
C direct voxel: OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE
D PPMI normative fiber: OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE
D dTOR normative fiber: OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE
formal target worklist: 4/7 READY_FOR_FORMAL_RESAMPLING; 3/7 OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING
formal readiness audit: 4/4 formal targets READY_FOR_FORMAL_DRIVER
ULF component e-fields: 64/64 available
direct-voxel formal permutation: A and C complete at B=10000, seed=42
direct-voxel formal bootstrap: A and C complete at B=10000, seed=42
direct-voxel formal jitter: A and C complete at B=1000, seed=42, FWHM=2 mm
dTOR normative-fiber smoke permutation: B_DTOR and D_DTOR complete at B=1000, seed=42
dTOR normative-fiber formal permutation: B_DTOR and D_DTOR complete at B=10000, seed=42
dTOR normative-fiber formal bootstrap: B_DTOR and D_DTOR complete at B=10000, seed=42
dTOR normative-fiber formal jitter: B_DTOR and D_DTOR complete at B=1000, seed=42, FWHM=2 mm
dTOR normative-fiber OSS sensitivity readiness: ready_for_oss_sensitivity
dTOR normative-fiber OSS sidecar input audit: B_DTOR and D_DTOR ready_for_true_oss_sidecar_generation; D_DTOR has 6 recovered derivatives ULF source-path rows for SNr003/SNr006/SNr007
dTOR normative-fiber OSS parameter preflight: 64/64 rows parameter_preflight_passed; B_DTOR 32 rows and D_DTOR 32 rows; MATLAB parameter dictionaries and leaddbs2ossdbs converter smoke return code 0; converter JSON frequency patched from source S frequency where needed
dTOR normative-fiber OSS row-level activation: 64/64 B_DTOR/D_DTOR rows pathway_activation_complete
dTOR normative-fiber OSS sidecar merge: B_DTOR and D_DTOR complete from clean commit da38d35c1; B_DTOR X_oss shape 16x3990 with 34450 nonzero entries; D_DTOR X_oss shape 16x2321 with 23816 nonzero entries
dTOR normative-fiber OSS sensitivity fitting: B_DTOR and D_DTOR complete from clean commit 219bba028 at B=1000, seed=42; both passed_activation_consistent
normative-fiber basic density and connected-region label caches: B_PPMI, B_MGH, B_DTOR, D_PPMI, and D_DTOR complete
normative-fiber FDR/enrichment caches: B_DTOR and D_DTOR complete at B=10000; observed robustness rows remain definition_documented_cache_not_generated
normative-fiber OSS sensitivity results: B_DTOR observed rho -0.3304, Q2 -0.5381, p=0.3976; D_DTOR observed rho 0.9234, Q2 -0.4087, p=0.1658
final reporting/readiness: 7 rows; n=16 hypothesis-generating; A/C direct maps ready; all normative-fiber rows have density+label outputs ready
C gain/total-ULF observed sensitivity outputs: complete; resampling_status = not_run_observed_only
C same-day immediate endpoint-family observed outputs: complete for 2 endpoint rows; resampling_status = not_run_observed_only
D same-day immediate endpoint-family observed outputs: complete for 4 endpoint/connectome rows; resampling_status = not_run_observed_only
D gain/total-ULF observed sensitivity outputs: complete for 4 endpoint/connectome rows; resampling_status = not_run_observed_only
all-endpoint reporting: 79 rows; A all-endpoint source-resolver rows = 30; discovered branch manifests = 35; missing-work audit rows = 6, with all C/D observed sensitivity and same-day immediate work items detected
all-endpoint manifest audit: 73 rows missing_git_or_patch_provenance / missing_code_provenance; 6 rows have provenance from a different commit
all-endpoint reporting manifest records manifest_provenance_counts and manifest_stale_counts
manifest schema audit: 36 unique manifest references; 6 schema_complete; 30 schema_missing_recommended_fields
completion/blocker audit: 7 rows; 4 complete_to_current_spec; 3 observed_robustness_no_formal_target with no blockers; 0 blocked rows
fiber connected-region label caches: complete for B_PPMI, B_MGH, B_DTOR, D_PPMI, and D_DTOR
density/label/FDR/enrichment figure-cache outputs: complete for B_DTOR and D_DTOR
```

Current direct-voxel formal permutation results:

```text
A direct voxel:
  observed rho = -0.0265487881
  p_plus_one_two_sided = 0.9455054495
  B = 10000

C ULF direct voxel no_delta_hf final model:
  observed rho = 0.9189995239
  p_plus_one_two_sided = 0.2324767523
  B = 10000
```

Current dTOR normative-fiber smoke permutation results:

```text
B_DTOR HF normative fiber:
  observed rho = -0.1828916512
  p_plus_one_two_sided = 0.6343656344
  B = 1000

D_DTOR ULF normative fiber no_delta_hf final model:
  observed rho = 0.9410908586
  p_plus_one_two_sided = 0.0879120879
  B = 1000
```

No additional observed-robustness-row FDR/enrichment drivers should be
interpreted as complete until the required FDR and enrichment caches are created
or supplied. OSS-DBS activation should remain an explicit missing-input status
until the required sidecars exist. Formal jitter QC is complete for B_DTOR and
D_DTOR.

The dTOR normative-fiber sensitivity-readiness summary records `oss_missing_inputs`,
`jitter_qc_status`, and `jitter_existing_inputs`. Final reporting and
figure-output readiness preserve these fields so downstream reports can inspect
which OSS inputs remain absent without reopening branch-level JSON files.
Sensitivity-readiness branch-local helper outputs must use readiness-specific
filenames and must not overwrite canonical formal jitter summaries or manifests.

The dTOR normative-fiber OSS sidecar input audit/worklist layer is a read-only
preflight for the remaining OSS blocker. It consumes the final-model formal
target worklist, generation manifests, mapping QC, branch score subject order,
and selected-source candidate fiber id order. It writes branch-level input-audit rows and
subject/side/source-path worklist rows under
`/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_oss_sidecar_worklist/`.
For ULF alternating-program rows, it can recover empty manifest ULF source paths
from existing derivatives folders matching
`stnsnr_vta_<subject>_3m_STNplusSNr_alt_<side>_SNr_*`, and records that recovery
in `path_mode`.
It must not create `X_oss_float32_fiber_major.npy`, alter
`oss_sensitivity_status`, or substitute for the true OSS/pPAM activation
runner.

An OSS converter smoke test found that existing
`sub-*_desc-stimparameters.mat` files cannot be passed directly to
`leaddbs2ossdbs`: the files are classic MAT files containing `S`, while
OSS-DBSv2 expects an HDF5/v7.3 dictionary with top-level `settings`. The next
implementation layer therefore needs a MATLAB-side Lead-DBS OSS preparation
wrapper that writes the expected parameter dictionary before the OSS-DBSv2
command-line tools can run.

The next OSS implementation layer is a parameter-dictionary preflight, not the
full sidecar generator. It consumes the sidecar worklist, runs the Lead-DBS
MATLAB preparation chain through `ea_check_stimSources`,
`ea_get_stimProtocol`, `ea_prepare_fibers`, and `ea_save_ossdbs_settings`, and
then runs a bounded `leaddbs2ossdbs` converter smoke on the generated parameter
file. Its outputs live under
`/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_oss_parameter_preflight/`.
It must not write final branch `X_oss_float32_fiber_major.npy`, must not write
`oss_parameter_manifest.json` or `oss_activation_sidecar_metadata.json`, and
must not change `oss_sensitivity_status`.

The full preflight now passes for all 64 B_DTOR/D_DTOR worklist rows when the
wrapper locks OSS to `dTOR-985 Full (Elias 2024)`, initializes
`settings.reuse_warped_connectome = 0`, and checks the generated converter JSON
under the generated Lead-DBS OSS output directory. The OSS-DBSv2 converter writes
130 Hz by default, so the preflight patches the generated JSON from source `S`
frequency when needed and records the original/final frequency fields. The
current full summary records 45 rows as `frequency_patched_from_source_S` and 19
rows as `frequency_validated`.

The converter output path must stay in the same Lead-DBS OSS output directory
as `oss-dbs_parameters.mat` and the filtered dTOR `data*.mat` files. A separate
converter-output folder makes downstream `prepareaxonmodel` look for
`data*.mat` in the wrong location.

The generated converter JSON should also use that same directory as
`StimulationFolder` for path consistency. OSS-DBSv2 CLI then overwrites
`StimulationFolder` with the parent directory of the input JSON file before it
writes success/failure marker files. The row-level runner must therefore keep
the copied converter JSON inside the row sandbox and accept success markers in
either the JSON parent directory or the filtered stimulation folder, while
requiring `oss_time_result_PAM.h5` under the filtered `Results` directory.

A manual B_DTOR `prepareaxonmodel` activation smoke using the corrected
parameter directory found no path or frequency error, but remained CPU-bound in
OSS-DBSv2 fiber-to-streamline conversion for more than 17 minutes and was
interrupted before completion. A later no-timeout B_DTOR row-level run remained
CPU-bound for about 50 minutes while reading the dTOR `data2.mat`, generated no
`Allocated_axons` output, and was interrupted for implementation triage. This
confirms that full OSS sidecar generation should remain resumable and
row-status driven, with explicit long-running/interrupted states, rather than
being treated as an interactive smoke command.

The 2026-07-09 candidate-universe audit found that B_DTOR has 3,990
selected-source candidate fibers and D_DTOR has 2,321, while the parent dTOR
exposure `fiber_ids.npy` has 11,820,000 IDs. The OSS worklist must therefore
propagate `oss_fiber_ids` from the selected-source weights table, not from the
parent exposure id universe. Row-level filtered OSS inputs must be generated in
a copied stimulation folder and must not overwrite the parent dTOR connectome
files. The row-level filter may reduce the active local OSS connectome to rows
whose stored fiber IDs intersect the selected-source `oss_fiber_ids`, but the
branch-level merge remains responsible for writing the final right-canonical
selected-source column order and for recording the homologous left-to-right
mapping status.

A row-local filtered-pathway probe then confirmed the safe implementation
boundary: do not overwrite the preflight stimulation folder. Instead, create a
per-row filtered stimulation folder under the activation-row output directory,
copy the OSS parameter file and non-connectome inputs, write filtered
`data{hemi}.mat` for the active hemisphere by matching the Lead-DBS local
connectome's original fiber-id row against `oss_fiber_ids`, and patch a copied
converter JSON so all OSS paths point at the filtered folder. In the B_DTOR
SNr003-left probe, 17 local candidate fibers intersected the 3,990
right-canonical selected-source candidates, and `prepareaxonmodel` completed in
about one second after the filtered folder included `OSS_sim_files_lh`.

The row-level activation runner now implements that filtered-folder behavior by
default. Early bounded probes showed that B_DTOR could filter 298,142 local
fibers down to 17 local candidate fibers, and D_DTOR could filter 345,628 local
fibers down to 5 local candidate fibers for the first probe rows. A later full
run completed `pathway_activation_complete` for all 64 B_DTOR/D_DTOR rows. This
still does not create branch-level `X_oss_float32_fiber_major.npy`; it proves
row-level OSS/pPAM execution is complete, while the branch merge layer remains
pending.

The merge layer must project each row's OSS output back onto the selected-source
candidate fiber id order. The filtered connectome `idx` vector is insufficient
for that projection because it stores filtered local fiber point counts rather
than selected-source candidate fiber ids. The row runner now persists a complete
local-axon/status-index to selected-candidate-fiber mapping as
`oss_local_to_candidate_fiber_mapping.csv` and carries the mapping path, row
count, and invalid-candidate-column count into the row status JSON and summary
CSV. The official B_DTOR/D_DTOR row-level activation outputs were rerun from
clean commit `7d9b312eb` after this runner change: 64/64 rows reached
`pathway_activation_complete`, 64/64 rows have mapping CSV files,
`mapping_total_rows = 101247`, and invalid candidate-column mappings = 0.
Branch-level `X_oss_float32_fiber_major.npy` was then generated by the branch
merge runner from clean commit `da38d35c1`. The merge wrote B_DTOR and D_DTOR
canonical sidecars plus `oss_parameter_manifest.json`,
`oss_activation_sidecar_metadata.json`, and `oss_activation_sidecar_qc.csv`;
the refreshed sensitivity-readiness summary now records both formal dTOR
targets as `ready_for_oss_sensitivity`.

The OSS worklist and sensitivity-readiness layers must resolve ULF
selected-source output locations from the actual shared exposure preprocess
directory. D_DTOR selected-source manifests do not always include
`outputs.preprocess_dir`; in that case the correct sidecar directory is the
parent directory of the selected `X_ULF_only_fiber...` matrix, not
`<branch_dir>/preprocess`.

The resumable OSS row-level activation runner is the row-execution layer after
parameter preflight. It consumes successful preflight rows and runs
`prepareaxonmodel`, `ossdbs`, and `run_pathway_activation` with per-step stdout,
stderr, return code, start/end timestamps, and expected-output checks. A row
may be resumed from the first incomplete step. The current full run completed
all required B_DTOR/D_DTOR rows. This runner still does not write branch-level
`X_oss_float32_fiber_major.npy`, `oss_parameter_manifest.json`, or
`oss_activation_sidecar_metadata.json`; those are reserved for the branch-merge
layer after row-level outputs have complete local-to-candidate mapping and p(A)
semantics are locked. Row-level summaries after the mapping update include
`local_to_candidate_mapping_path`, `local_to_candidate_mapping_n_rows`, and
`local_to_candidate_mapping_invalid_candidate_column_count`.

A bounded B_DTOR runner test with `--stop-after-step prepareaxonmodel` and a
5-second `prepareaxonmodel` timeout produced
`row_status = timeout_or_interrupted`, wrote per-step logs and
`oss_activation_row_status.json`, and left no residual OSS process. This
confirms the resume/status harness without claiming row or branch activation
completion.

The consolidated status manifest records git provenance for the worktree that
generated the status refresh, including branch, HEAD commit, and dirty files.
Each status CSV row also records whether its referenced `latest_manifest`
contains git or local-patch provenance. Existing branch manifests generated
before this policy may be marked `missing_git_or_patch_provenance`; that marker
means provenance is incomplete and does not by itself rerun or invalidate the
observed outputs.

The consolidated status CSV also records `latest_manifest_stale_status`. This is
a manifest-level audit field derived from the referenced branch manifest's code
provenance and the current worktree HEAD. It is intended to identify branch
manifests that are missing provenance or were generated from a different commit.
It must not change source status, prediction status, branch-role assignment, or
final-model selection by itself.

Downstream layers preserve the same manifest audit pair where their rows are
derived from consolidated execution status. Formal target worklist, formal
readiness, final report, and figure-readiness rows carry both
`latest_manifest_provenance_status` and `latest_manifest_stale_status`;
all-endpoint final-report rows carry them through from the final report.
Non-status-derived all-endpoint rows compute these fields from their own
`manifest_path` when one exists; rows without a manifest path leave the fields
blank.

The consolidated status report also resolves final-model fields from the current
source/endpoint classifiers. HF rows record `hf_final_model_source`,
`hf_final_model_role`, and `hf_final_model_status`. ULF rows record
`ulf_final_model_branch`, `ulf_final_model_role`, and
`ulf_final_model_status`; formal, jitter, OSS, and display-layer work attach to
that final model rather than to a manually selected reporting branch.

## Shared IO / Provenance Helper

The first reusable architecture layer centralizes lightweight file IO and
manifest provenance behavior in:

```text
my_helper/fiber/core/analysis/stnsnr_io.py
```

The helper owns timestamp generation, CSV read/write, JSON write, and optional
`code_provenance` injection for manifest-like JSON outputs. The legacy
gate-status summary, consolidated execution status layer, formal target
worklist, formal readiness audit, final reporting layer, all-endpoint reporting
layer, C same-day immediate driver, and C/D gain/total-ULF sensitivity drivers
use this helper. Migration should remain incremental and behavior-preserving. It
must not change model formulas, source resolver rules, branch-role assignment,
or output paths.

The final reporting layer consumes the consolidated status, formal worklist,
formal readiness audit, formal summary CSVs, and fiber sensitivity-readiness
CSV. It writes:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_report.md
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_figure_output_readiness.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_reporting_manifest.json
```

This layer does not fit models, rerun resampling, or fabricate unavailable
fiber density/FDR/enrichment outputs. It records `ready_from_existing_maps` for
A/C direct-voxel display sources, `ready_for_full_fiber_figure_outputs` for
formal dTOR normative-fiber rows with density, labels, FDR, and enrichment
caches, and `ready_for_density_label_outputs` for observed-robustness
normative-fiber rows with density plus connected-region label caches but no
generated FDR/enrichment caches. It also preserves per-row FDR and enrichment
component status, fiber OSS missing-input details, formal jitter QC status, and
the manifest audit pair from the consolidated status input.

The all-endpoint reporting layer consumes the existing A all-scale
source-resolver scan, observed branch summary, final report, and discovered
branch manifests. It writes:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_report.md
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_missing_work.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_reporting_manifest.json
```

This layer does not fit gain, same-day immediate, or total-ULF sensitivity
models. It records those C/D outputs as `observed_outputs_detected` when output
files exist and `not_run_missing_observed_outputs` when they are absent, so
downstream reporting can distinguish "not run" from "failed model". Rows sourced
from the final report preserve the manifest audit pair; other row sources
compute the pair from their own `manifest_path` when one exists. The
all-endpoint reporting manifest stores `manifest_provenance_counts` and
`manifest_stale_counts` so downstream checks can audit the report without
rescanning the CSV.

The completion/blocker audit layer consumes the final report, figure-output
readiness table, all-endpoint missing-work audit, and manifest schema audit. It
writes:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/completion_audit/four_model_completion_audit.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/completion_audit/four_model_completion_audit.md
/Volumes/VAL/STNSNr/summary/four_model_execution/completion_audit/four_model_completion_audit_manifest.json
```

This layer is reporting-only. It does not fit models, rerun formal resampling,
select branches, or generate missing OSS, jitter, or density inputs. Its purpose is
to summarize what is complete, what is blocked by absent inputs, and what is
observed-only or provenance-incomplete at the current execution checkpoint.

The normative-fiber density/label cache layer consumes the final report,
normative-fiber branch manifests, connectome
`data.mat` streamline coordinates, and the existing final-model fiber weights.
It writes branch-local streamline voxel density and weighted-density NIfTI maps
plus a compact cache `.npz`, connected-region label-overlap CSV/manifest, and
a density-cache manifest. This layer does not run OSS-DBS, does not perform
spatial jitter, and does not compute FDR maps or anatomical/pathway enrichment. It is a
display-cache construction step only; enrichment, OSS sensitivity, and jitter QC
remain separate layers.
The final reporting layer therefore records this output as
`ready_from_existing_density_label_cache_missing_fdr_enrichment` and
`ready_for_density_label_outputs`, not as full FDR/enrichment readiness.

The connected-region label cache summarizes overlap between each normative-fiber
density cache and the registered `STN-connected regions`, `SNr-connected
regions`, and `STNSNr-connected regions` ROI manifests. This is a QC/display
summary only. It upgrades figure readiness to `ready_for_density_label_outputs`,
but it must not be reported as full FDR/enrichment readiness until both
separate FDR and enrichment caches exist.

Final reporting keeps the historical combined
`fiber_density_label_cache_status` field for downstream compatibility, but the
final report CSV and the figure-readiness CSV also record separate component
statuses for basic density, connected-region labels, FDR, and enrichment.
Completion audit uses those component statuses to record distinct `fdr_cache`
and `enrichment_cache` blockers.

The manifest schema audit layer consumes consolidated status, final reporting,
and all-endpoint reporting tables. It deduplicates referenced manifest paths,
checks whether each manifest exists and parses as JSON, records the shared
manifest provenance/stale audit pair, and marks missing recommended schema
fields such as `outputs`, `code_provenance`, and `generated_at`. It is
reporting-only and must not change model classification or final-target
selection.

The D same-day immediate endpoint-family layer should mirror the C immediate
wrapper, but call the ULF normative-fiber observed driver for each available
STN+SNr immediate endpoint row and connectome. The underlying D observed driver
must select ULF component e-field readiness rows from the endpoint phase parsed
from `post_scale`; it must not hard-code chronic `3m` rows for immediate
endpoints. These outputs are observed-only family outputs and do not replace the
unique chronic D final model unless the model specification is revised before
formal resampling.

Because D endpoint rows that share a connectome and phase also share the same
HF/ULF component e-fields, the observed driver may reuse a complete component
preprocess cache from another endpoint row only when the phase token and ordered
subject IDs match. This avoids rebuilding identical left-to-right flipped
component fields and fiber exposure sidecars across total and axial immediate
endpoint rows. It must not reuse chronic `3m` caches for immediate endpoints or
reuse a cache with a different subject order.

The D same-day immediate wrapper should be idempotent. When both branch
generation manifests and the source-resolver manifest already exist for an
endpoint/connectome row, it should add that row to the family summary without
rerunning the observed branch or source-resolver scan unless explicitly forced.

## Execution Root Availability

The canonical execution documents use `/Volumes/VAL/STNSNr` as the STNSNr VAL
root. During this resumed Codex run, `/Volumes/VAL` was initially unavailable,
so one M0 readiness check was run against the local mirror
`/Users/mojackhu/Research/STNSNr` and reported failures because that mirror does
not contain the complete external-drive project structure.

After the external drive was mounted, the canonical root was available again:

```text
/Volumes/VAL/STNSNr
```

Subsequent execution should use the canonical `/Volumes/VAL/STNSNr` defaults
unless the drive is unavailable again. The temporary local-root readiness output
is an environment diagnostic only and is not the authoritative four-model status.

## Backend / Workflow Separation

Implementation must distinguish reusable backend code from STN/SNr project
workflow code.

Reusable backend code belongs under:

```text
my_helper/fiber/core/
```

It should expose parameterized functions for statistics, feature matrices,
NIfTI/connectome IO, scoring, QC, and manifest writing. Backend code must not
make project paths, atlas selections, endpoint defaults, subject IDs, or
connectome choices part of the algorithm. Any convenience defaults must be
overridable by the caller.

Generic NIfTI writers must accept an explicit support mask. Continuous or
statistical maps write `NaN` outside support, not `0`; coverage/count maps and
binary masks are the only exception.

Project workflow code belongs under:

```text
my_helper/fiber/stnsnr/
```

Workflow scripts resolve STN/SNr-specific paths, endpoints, connectomes, atlas
registries, and branch names, then pass an explicit config into backend
functions. The `stnsnr/` directory remains an orchestration layer rather than a
helper-function directory.

## Implemented Layer

The M0 readiness entry point is:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py
```

Reusable implementation lives in:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_readiness.py
```

The pipeline script only resolves the repository path and calls the reusable core function. This preserves the rule that `my_helper/fiber/stnsnr` contains only orchestration scripts.

## M0 Scope

The readiness run verifies and records:

- Python execution environment, including the Conda `leaddbs` package versions needed for statistical post-processing.
- MATLAB executable availability and optional `ea_flip_lr_nonlinear` callability.
- `/Volumes/VAL/STNSNr` mount, `reference/`, `summary/`, and output-root writability.
- Raw clinical score workbook availability, required columns, subject count, default HF endpoint availability, ULF chronic delta/reconstructibility status, and immediate endpoint availability.
- `followup_stimulation.xlsx` `Contact Parameters` availability, required columns, subject count, target/frequency sanity, and expected MNI raw `sim-efield` path availability. Continuous stimulation uses the condition-level VTA folder. Alternating stimulation is discovered at subprogram/contact level with `alt_<side>_<target>_c<contact>_row*` folder names.
- Public connectome `data.mat` availability under the asset root.
- Connected-region atlas availability under the asset root.
- Scale direction table generation with `SE-ADL` marked higher-is-better and the current score scales marked lower-is-better.

Historical Codex worktrees may not contain gitignored heavy assets such as
`templates/` and `connectomes/`. The M0 tool therefore accepts an explicit
`--asset-root` and otherwise falls back to `/Users/mojackhu/Github/leaddbs`
when the current worktree lacks those assets.

## Outputs

Default output root:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/m0_readiness/
```

Each run writes a timestamped directory:

```text
run-YYYYMMDD-HHMMSS/
  four_model_m0_readiness_manifest.json
  four_model_m0_readiness_checks.csv
  four_model_m0_endpoint_availability.csv
  four_model_m0_efield_availability.csv
  scale_direction_table.csv
  environment/
    conda_leaddbs_explicit.txt
    pip_freeze.txt
```

The manifest records the overall status. Missing data are not silently ignored. The default run is report-only and exits `0`; `--strict` makes any `FAIL` check exit non-zero.

## M1 Shared Statistical Kernel

The first M1 code layer adds reusable statistical primitives only. It does not read real E-field matrices and does not write model outputs. The kernel is designed so the four model drivers can share the same exact baseline-adjusted partial Spearman, fold coverage, scoring, prediction, and permutation utilities.

Reusable implementation lives in:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_stats.py
```

The smoke/equivalence self-test entry point is:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py
```

The self-test verifies:

- vectorized partial Spearman matches a brute-force per-feature reference;
- LOOCV fold coverage by held-out subtraction matches a brute-force training-only coverage calculation;
- `HFScore_mean_main` style mean map scoring matches the manual formula;
- fiber `NetFiberScore = SweetPeak5 - SourPeak5` uses deterministic top-k selection and produces finite scores;
- Freedman-Lane permuted outcomes preserve the nuisance fitted component and are reproducible with seed `42`;
- plus-one two-sided permutation p values use the documented formula.

This layer is intentionally model-agnostic. It does not define HF/ULF paths, does not create sidecars, does not perform image/fiber sampling, and does not run formal `B=10000` loops.

## Shared Resolver Utilities

The shared resolver layer is:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_resolver.py
```

It now contains reusable helpers for:

```text
pre-specified versus scan-fallback source resolution
adjacent-grid support counting
MAE/RMSE prediction-status classification
safe Pearson/Spearman reporting metrics
branch-specific nuisance design validation
```

Direct voxel and normative fiber ULF observed drivers import these helpers
instead of maintaining separate copies. Model-specific hard computability
predicates remain in the model drivers because voxel and fiber support
quantities differ.

Self-test:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/core/analysis/stnsnr_four_model_resolver_selftest.py
```

## ULF Dependency Identifiers

ULF readiness and status code use explicit HF dependency IDs from the current
status CSV:

```text
C direct voxel depends on A
D PPMI normative fiber depends on B_PPMI
D dTOR normative fiber depends on B_DTOR
```

There is no generic `B` status row. Additional D connectome variants must
bind to their matching `B_<connectome>` dependency explicitly.

## HF Direct Voxel Smoke Driver

This executable layer implements the primary HF direct voxel observed branch:

```text
model = HF direct voxel
scale = MDS-UPDRS III score (STN, 3 m) by default
branch = tau200 / partial_spearman
validation = observed LOOCV
resampling = not run
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_smoke.py
```

This driver reads existing raw `sim-efield` files. It does not create missing e-fields. Alternating same-side subprograms are max-combined in the common right-canonical sampled feature space, which also handles the real case where subprogram local e-field grids differ. Left-side subprogram e-fields are flipped with `ea_flip_lr_nonlinear` into the right canonical space before sampling. The driver samples both right e-fields and left-to-right flipped e-fields on the right MNI brainmask grid, averages them per subject, builds `Candidate` from `180 V/m`, and runs the `tau200 / Coverage>=5` partial-Spearman observed LOOCV branch.

Because `ea_flip_lr_nonlinear` uses interpolation, a flipped E-field magnitude image can contain very small negative interpolation artifacts. The smoke driver clamps negative sampled E-field values to `0` and records the count and minimum value in QC. This is a numeric data-integrity correction for an E-field magnitude image, not a modeling threshold.

Outputs are written under:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/
  preprocess/
  tau200/partial_spearman/
```

The smoke driver intentionally omits `direct_voxel_HF_permutation_summary.csv` and `direct_voxel_HF_bootstrap_se.nii.gz`; those belong to later gated formal/smoke resampling rounds.

## HF Normative Connectome Fiber Smoke Driver

This B-model executable layer targets the cheapest real public connectome first:

```text
model = HF normative connectome fiber
connectome = PPMI 85 (Ewert 2017) by default
scale = MDS-UPDRS III score (STN, 3 m) by default
legacy/current output branch = peak_efield_tau800_primary
revised spec branch = peak_efield_tau800_cov5_primary
validation = observed LOOCV
resampling = not run
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke.py
```

This driver reads the full public connectome from MATLAB v7.3/HDF5 `data.mat` using chunked fiber blocks. It does not target-restrict streamlines. For each subject, right-sided raw `sim-efield` and left-sided `ea_flip_lr_nonlinear` flipped e-fields are sampled along the same right-canonical streamline coordinates. Alternating same-side subprograms are max-reduced in streamline point space before the bilateral average.

The first executable branch writes a subject-by-fiber exposure sidecar, applies:

```text
tau = 800 V/m
coverage = Coverage>=5
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = Coverage_tau(l) >= 5
```

and then runs the partial-Spearman `NetFiberScore` observed LOOCV branch. Existing outputs use the legacy folder/branch name `peak_efield_tau800_primary`; documentation now maps that branch to revised `peak_efield_tau800_cov5_primary` until a future code/output migration renames directories. Formal `B=10000`, dTOR processing, and the revised `tau_coverage_source_resolver_scan` remain later gated stages. OSS-DBS, jitter, FDR cache, and enrichment cache layers remain separate downstream blockers.

The driver supports `--max-fibers` only for development self-tests and debugging. Production PPMI smoke runs should leave it unset so the candidate universe remains the full PPMI connectome.

## Four-Model Status Summary

The current status tool reads manifests/QC files and writes a compact execution table:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_gate_status.py
```

The tool does not run any model. Any older stop/go fields emitted by this code are historical execution metadata. Intended A direct-voxel dependency decisions must come from `hf_voxel_source_status` and `hf_voxel_prediction_status`; intended B normative-fiber decisions must come from `hf_norm_fiber_source_status` and `hf_norm_fiber_prediction_status`.

## ULF Component Readiness Gate

This executable layer audits whether the C and D ULF add-on models can start
without violating their component-separation requirements. It does not run ULF
voxel maps, ULF fiber maps, DeltaHFScore scoring, permutation, bootstrap, OSS,
or display outputs.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_component_readiness.py
```

The readiness check verifies:

- chronic ULF endpoint reconstruction from `subject_effect_origin.xlsx` for the
  default total motor scale;
- same-day immediate endpoint availability, recorded as unavailable when the raw
  table has no immediate rows;
- frequency-component classification from `followup_stimulation.xlsx` with
  `HF >= 100 Hz` and `ULF <= 50 Hz`;
- component-specific `3m/STN+SNr` and `immediate/STN+SNr` raw `sim-efield`
  availability for every subject, side, and frequency-classified component row;
- A/B dependency status from the current status CSV, while intended direct-voxel
  branch roles are refreshed from `hf_voxel_source_status` and
  `hf_voxel_prediction_status`.

The readiness check follows the same e-field path logic as the target-component VTA
distribution code:

- observed alternating components use observed subprogram e-fields under
  `stnsnr_vta_<ID>_<phase>_STNplusSNr_alt_<side>_<target>_c<contact>_row<index>`;
- observed single-target continuous components use the corresponding continuous
  condition e-field;
- mixed continuous STN+SNr components use the counterfactual target-component
  e-field under `stnsnr_target_component_<ID>_<phase>_STNplusSNr_<side>_<target>`.

The readiness check must not substitute the mixed `STN+SNr` condition-level e-field for
frequency-component HF or ULF e-fields. If the required observed subprogram or
target-component e-fields are missing, C/D remain not executable even when mixed
condition VTA outputs, thresholded VTA masks, or component stimulation-parameter
folders exist.

Outputs are written under:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/ulf_component_readiness/run-YYYYMMDD-HHMMSS/
  ulf_component_readiness_manifest.json
  ulf_component_readiness_checks.csv
  ulf_component_endpoint_reconstruction.csv
  ulf_component_efield_availability.csv
```

Expected current status is a hard input failure for C/D model execution if the
component folders contain only stimulation parameter files and no raw
`sim-efield` NIfTI files. This is still forward progress: it prevents an invalid
ULF analysis from being run with a mixed HF+ULF field while recording exactly
which component e-fields must be generated next.

## Commands

Run from the worktree:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py \
  --run-matlab-check
```

Use `--strict` when M0 is acting as a hard gate before starting model computation.

Run the M1 shared-kernel self-test:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py
```

Run the HF direct voxel observed smoke driver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py
```

Run the HF normative fiber observed smoke driver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py
```

Summarize legacy A/B status:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

Run the ULF component readiness check:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py
```

## Four-Model Execution Status Report

The current execution state is distributed across M0 readiness, A/B primary
status, and ULF component readiness outputs. The status report layer
collects those artifacts into one machine-readable and human-readable snapshot.
It does not run any model and does not change resolver/status fields. It should
also detect completed direct-voxel formal permutation summaries and mark A/C as
`FORMAL_PERMUTATION_COMPLETE_BOOTSTRAP_NOT_STARTED` when the final branch has a
complete `B=10000` permutation summary. Observed-robustness-only normative
connectome rows are marked `OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING` rather
than `NOT_STARTED_FORMAL_RESAMPLING`.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_execution_status.py
```

The report records, for each model:

- whether required primary observed outputs exist;
- current resolver/status decision and observed LOOCV metrics;
- whether downstream dependencies are locked or exploratory;
- whether missing inputs prevent execution;
- whether formal resampling is allowed, deferred by status, or not yet applicable.

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/status/
  four_model_execution_status.csv
  four_model_execution_status.md
  four_model_execution_status_manifest.json
```

Run the consolidated status report:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

## Final-Model Formal Target Worklist

The formal target worklist is the first executable layer after final-model
classification. It does not run permutation, bootstrap, jitter, OSS-DBS, or
display generation. It reads the consolidated execution status and writes a
machine-readable list of final model branches/sources that should be consumed by
future formal resampling drivers.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_worklist.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_formal_worklist.py
```

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/
  four_model_formal_target_worklist.csv
  four_model_formal_target_worklist.md
  four_model_formal_target_worklist_manifest.json
```

Rows with `final_model_error_predictive` or `final_model_error_nonpredictive`
are marked `READY_FOR_FORMAL_RESAMPLING` only if their model family defines a
formal inference target. Current formal targets are A, B_DTOR, C, and D_DTOR.
B_PPMI, B_MGH, and D_PPMI are retained as observed robustness outputs and are
marked `OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING`. Rows with no final model are
marked `NO_FINAL_MODEL`. This worklist is intentionally independent of manual
reporting-branch selection.

Run the worklist:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_worklist.py
```

## Final-Model Formal Readiness Audit

The formal readiness audit is the next lightweight layer after the final-model
formal target worklist. It does not run formal permutation, bootstrap, spatial
jitter, OSS-DBS, or display generation. It reads the worklist and verifies that
each `READY_FOR_FORMAL_RESAMPLING` row points to an existing branch manifest and
to the branch-level QC, score, and LOOCV prediction files required by future
formal drivers.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_readiness.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_formal_readiness.py
```

Required branch files are inferred from the manifest filename:

```text
direct_voxel_HF_generation_manifest.json:
  direct_voxel_HF_mapping_qc.json
  direct_voxel_HF_scores.csv
  direct_voxel_HF_loocv_predictions.csv

normative_HF_fiber_generation_manifest.json:
  normative_HF_fiber_mapping_qc.json
  normative_HF_fiber_scores.csv
  normative_HF_fiber_loocv_predictions.csv

direct_voxel_ULF_only_generation_manifest.json:
  direct_voxel_ULF_only_mapping_qc.json
  direct_voxel_ULF_only_scores.csv
  direct_voxel_ULF_only_loocv_predictions.csv

normative_ULF_fiber_generation_manifest.json:
  normative_ULF_fiber_mapping_qc.json
  normative_ULF_fiber_scores.csv
  normative_ULF_fiber_loocv_predictions.csv
```

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/
  four_model_formal_readiness.csv
  four_model_formal_readiness.md
  four_model_formal_readiness_manifest.json
```

Run the audit:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_readiness.py
```

## Direct-Voxel Final-Model Formal Permutation

The direct-voxel formal permutation layer is the first expensive formal layer.
It covers the A and C final models only. B_DTOR and D_DTOR are normative-fiber
formal targets and require a separate chunked fiber implementation; B_PPMI,
B_MGH, and D_PPMI remain observed robustness outputs.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_permutation.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_direct_voxel_formal_permutation.py
```

Default outputs are written into the final branch directories:

```text
A:
  direct_voxel_HF_permutation_summary.csv
  direct_voxel_HF_permutation_null_stats.npy

C:
  direct_voxel_ULF_only_permutation_summary.csv
  direct_voxel_ULF_only_permutation_null_stats.npy
```

The driver consumes the formal readiness CSV and processes only rows with
`formal_readiness_status = READY_FOR_FORMAL_DRIVER` and model IDs `A` or `C`.
Each permutation uses Freedman-Lane residual permutation with seed `42` and
reruns the direct-voxel LOOCV map, score, nuisance-only baseline, and held-out
prediction steps. It does not implement bootstrap, jitter, or fiber formal
permutation.

Run the formal A/C permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_permutation.py \
  --n-permutations 10000
```

## dTOR Normative-Fiber Smoke Permutation

The dTOR normative-fiber smoke permutation layer covers B_DTOR and D_DTOR final
branches. It is exact for the selected dTOR peak-E-field model semantics: each
permuted outcome reruns fold-specific candidate selection, `rho`, `M`,
`F+`/`F-`, `NetFiberScore`, nuisance-only baseline, held-out prediction, and
LOOCV Spearman rho over the selected tau/Coverage candidate universe. It is not
formal `B=10000` inference and does not implement bootstrap, jitter, or OSS.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_normative_fiber_smoke_permutation.py
```

Default outputs:

```text
B_DTOR branch:
  normative_HF_fiber_smoke_permutation_summary.csv
  normative_HF_fiber_smoke_permutation_null_stats.npy

D_DTOR final branch:
  normative_ULF_fiber_smoke_permutation_summary.csv
  normative_ULF_fiber_smoke_permutation_null_stats.npy

Cross-target summary:
  /Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_smoke_permutation/normative_fiber_smoke_permutation_summary.csv
```

Run the dTOR smoke permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py \
  --n-permutations 1000
```

## ULF Component E-field Worklist

When the ULF readiness check reports missing component-specific e-fields, the
worklist layer converts the latest readiness CSV into an explicit queue. It
does not run MATLAB and does not generate e-fields; it only records which
components must be generated before any ULF voxel or fiber model can execute
without mixing HF and ULF fields.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_component_efield_worklist.py
```

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/ulf_component_efield_worklist/
  ulf_component_efield_worklist.csv
  ulf_component_efield_worklist_manifest.json
```

The current expected missing items are continuous mixed STN+SNr
counterfactual target-component e-fields. Existing observed alternating
subprogram e-fields are not included in the missing worklist.

Run the worklist generator:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py
```

## HF Direct Voxel Source Resolver

The executable resolver layer replaces the older candidate-level
classification with the direct-voxel source resolver from
`hf_3m_direct_voxel_model.md`. It reads the existing all-endpoint Round 2
tau/Coverage scan outputs and writes an automatic summary of which HF endpoints
have a stable source for downstream ULF `DeltaHFScore` construction.

The classifier is implemented inside the existing tau/Coverage scan module:

```text
my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_posthoc_threshold_scan.py
```

and exposed through the existing pipeline entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py
```

Source-resolver refresh command without recomputing the 60-cell scans:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales \
  --plot-only
```

Current resolver outputs:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/posthoc_threshold_scan_all_scales/
  all_scales_posthoc_threshold_scan_long.csv
  all_scales_posthoc_threshold_scan_summary.csv
  all_scales_posthoc_threshold_scan_manifest.json
```

The intended resolver uses scan-table evidence only for computability and local
support: `n_subjects >= 12`, `n_voxels_full >= 20`, `fold_n_voxels_min >= 10`,
nonconstant `HFScore`, finite predictions, and adjacent passing grid cells on
the declared tau/Coverage grid. It first tests `tau200/Coverage>=5`; only if
that source is not accepted does it choose a fallback by distance to the
pre-specified grid, adjacent support count, `fold_n_voxels_min`, stricter
Coverage, and higher tau. MAE/RMSE define `hf_voxel_prediction_status`; `Q2`
and LOOCV Spearman rho are report metrics.

## ULF Direct Voxel Observed Driver

The C-model observed executable layer runs the core ULF direct voxel branches.
It is intentionally limited to LOOCV observed modeling; formal permutation,
bootstrap, and jitter are separate final-model drivers. Gain and total-ULF
sensitivity outputs are handled by the separate observed-only sensitivity
driver below. Same-day immediate endpoint rows are handled by the separate
observed-only endpoint-family driver below.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_observed.py
```

Lightweight implementation self-test:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_observed_selftest.py
```

Default endpoint:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference scale = same base scale under STN, 3 m
tau = 200 V/m
Coverage>=5
estimator = baseline-adjusted partial Spearman
```

The driver reads the latest `ulf_component_efield_availability.csv`, samples
component-specific HF and ULF raw `sim-efield` files into the same right
canonical brainmask feature space used by the HF direct voxel driver, and
creates:

```text
E_HF_component_i(v)  = bilateral average of HF component e-fields
E_ULF_component_i(v) = bilateral average of ULF component e-fields
X_ULF_only_i(v)      = E_ULF_component_i(v) when ULF is active and HF is not active
```

Same-side same-frequency rows are max-combined before bilateral averaging.
Left-sided fields are flipped with `ea_flip_lr_nonlinear`. The driver does not
generate missing component e-fields.

Both core branches are executed when inputs allow:

```text
tau200/partial_spearman_no_delta_hf
tau200/partial_spearman_delta_hf_adjusted
```

Under the revised A resolver, both branches are run when a stable HF voxel source
exists. The DeltaHF-adjusted branch is primary only when
`hf_voxel_prediction_status = error_predictive`; otherwise no-DeltaHF is primary.
If the HF resolver returns `absent_no_stable_grid`, only no-DeltaHF should run for
that endpoint.

For the DeltaHF-adjusted branch, `DeltaHFScore` is computed fold-locally. In
each ULF LOOCV fold, the driver refits the matched HF direct voxel map from
training patients only, projects both the HF-only reference component and the
HF component under HF+ULF programming onto that training-fold map, and subtracts
the two scores. The held-out patient never contributes to the fold-specific HF
map, ULF map, ULF scoring set, or final prediction model.

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<scale_slug>/
  preprocess/
  tau200/partial_spearman_no_delta_hf/
  tau200/partial_spearman_delta_hf_adjusted/
```

Each branch writes observed scores, LOOCV predictions, NIfTI maps, QC JSON, and
a generation manifest. The branch manifests record `ulf_primary_branch`,
`delta_hfscore_role`, `hf_voxel_source_status`, `hf_voxel_prediction_status`,
`ulf_voxel_source_status`, `ulf_voxel_prediction_status`,
`ulf_endpoint_model_status`, `ulf_branch_input_status`,
`branch_nuisance_design_status`, and `resampling_status=not_run_observed_only`.

The ULF branch resolver mirrors the HF direct-voxel split between source
stability and prediction error. Its hard computability filter is
`n_subjects >= 12`, `n_voxels_full >= 20`, `fold_n_voxels_min >= 10`,
nonconstant `ULFScore_mean_main`, valid branch-specific nuisance design, and
finite held-out predictions. The nuisance design is branch-specific:
`intercept + Y_HF_ref` for no-DeltaHF and
`intercept + Y_HF_ref + DeltaHFScore` for DeltaHF-adjusted. MAE/RMSE are
compared against that branch's nuisance-only baseline to assign
`ulf_voxel_prediction_status`. ULF statuses qualify the selected branch as
stable/error-predictive or not; they do not change the branch role assigned from
the matched HF resolver.

Current C source-resolver output:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau_coverage_source_resolver_scan/
  direct_voxel_ULF_only_tau_coverage_source_resolver_scan.csv
  direct_voxel_ULF_only_tau_coverage_source_resolver_manifest.json

no_delta_hf:        pre_specified_accepted + error_nonpredictive at tau200/Coverage>=5
delta_hf_adjusted:  pre_specified_accepted + error_predictive at tau200/Coverage>=5
endpoint status:    primary_branch_error_nonpredictive
```

The consolidated execution status reporter treats C as
`OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE` because the matched A source is
accepted but `error_nonpredictive`, so the HF-derived intended primary branch is
no-DeltaHF.

Run the C source resolver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py \
  --source-resolver-scan
```

## ULF Direct Voxel Gain / Total-ULF Sensitivity Driver

The C-model gain/total-ULF sensitivity layer is observed-only and
chronic-endpoint-only. It reuses the existing C observed output and
preprocessing products when available, and writes:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_gain_endpoint/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_total_ulf_exposure/
```

The gain endpoint replaces `Y_post` with direction-normalized `Gain_chronic`.
The total-ULF sensitivity keeps the chronic raw post-score endpoint but uses
total ULF component exposure instead of HF-overlap-excluded ULF-only exposure.
Both outputs are sensitivity branches only:

```text
resampling_status = not_run_observed_only
formal permutation/bootstrap/jitter = not run
same-day immediate endpoint family = not included
```

Current observed-only sensitivity summary:

```text
partial_spearman_gain_endpoint: rho = 0.4762799998; Q2 = 0.1980823112
partial_spearman_total_ulf_exposure: rho = 0.9278360578; Q2 = -0.0371760912
summary CSV = /Volumes/VAL/STNSNr/summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200/direct_voxel_ULF_only_sensitivity_summary.csv
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_sensitivity_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_sensitivity_observed.py
```

## ULF Direct Voxel Same-Day Immediate Endpoint-Family Driver

The C same-day immediate endpoint-family layer is observed-only. It discovers
all raw clinical `STN+SNr immediate` endpoint rows with paired `STN 3m`
reference scores and `n_subjects >= 12`, then runs the existing C observed
LOOCV driver and source-resolver scan for each endpoint row.

Current raw clinical availability:

```text
MDS-UPDRS III score (STN+SNr, immediate): n = 16 paired subjects
MDS-UPDRS III axial score (STN+SNr, immediate): n = 16 paired subjects
```

The driver depends on ULF component readiness rows for `STN+SNr immediate`.
It writes standard ULF direct-voxel branch outputs under each immediate endpoint
slug and does not run formal permutation, bootstrap, jitter, or same-day gain
sensitivity outputs.

Current observed-only immediate summary:

```text
MDS-UPDRS III axial score (STN+SNr, immediate):
  no_delta_hf rho = -0.1663032166; Q2 = -0.0688212270
  delta_hf_adjusted rho = -0.0816667582; Q2 = -0.0444042831
  resolver = pre_specified_accepted + error_nonpredictive for both branches

MDS-UPDRS III score (STN+SNr, immediate):
  no_delta_hf rho = 0.8754627142; Q2 = 0.0224944733
  delta_hf_adjusted rho = 0.8209305249; Q2 = 0.1583522560
  resolver = pre_specified_accepted + error_nonpredictive for both branches

endpoint_model_status = primary_branch_error_nonpredictive for both endpoint rows
summary CSV = /Volumes/VAL/STNSNr/summary/direct_voxel/ulf/immediate_endpoint_family/direct_voxel_ULF_only_immediate_endpoint_summary.csv
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_immediate_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_immediate_observed.py
```

## ULF Normative Fiber Observed Driver

The D-model observed executable layer runs the observed-only ULF normative
connectome fiber branches. It is intentionally limited to LOOCV observed
modeling; formal permutation, bootstrap, jitter, OSS-DBS, anatomical/pathway enrichment,
and figure-grade density outputs are separate downstream layers.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py
```

Lightweight implementation self-test:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py
```

Default observed endpoint and connectome:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference scale = same base scale under STN, 3 m
connectome = PPMI 85
tau = 800 V/m
Coverage>=5
estimator = baseline-adjusted partial Spearman
```

The driver reads the latest `ulf_component_efield_availability.csv`, samples
component-specific HF and ULF raw `sim-efield` files along the right-canonical
public connectome streamlines, and creates:

```text
X_HF_component_i(l)  = bilateral average peak HF component exposure
X_ULF_component_i(l) = bilateral average peak ULF component exposure
X_ULF_only_i(l)      = X_ULF_component_i(l) when ULF is active and HF is not active
```

The matched HF reference exposure is reused from the existing HF normative fiber
sidecar for the same connectome and scale whenever available. This keeps the
`DeltaHFFiberScore` support aligned to the already observed B branch.

Both D core branches are executed when inputs allow:

```text
default observed output: ulf_peak_efield_tau800_no_delta_hf
revised default spec:    ulf_peak_efield_tau800_cov5_no_delta_hf

default observed output: ulf_peak_efield_tau800_delta_hf_adjusted
revised default spec:    ulf_peak_efield_tau800_cov5_delta_hf_adjusted

selected-source output after current PPMI scan fallback:
  ulf_peak_efield_tau600_no_delta_hf
  ulf_peak_efield_tau600_delta_hf_adjusted
```

The revised normative-fiber resolver reads the matched B dependency before
assigning the interpretive primary branch: accepted B source plus
`hf_norm_fiber_prediction_status = error_predictive` makes
`delta_hf_adjusted` intended primary; accepted B source plus
`error_nonpredictive` makes `no_delta_hf` intended primary;
`absent_no_stable_grid` runs no-DeltaHF only.

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/<connectome_slug>/<scale_slug>/peak_efield_tau800_observed/
  preprocess/
  ulf_peak_efield_tau800_no_delta_hf/
  ulf_peak_efield_tau800_delta_hf_adjusted/
  tau_coverage_source_resolver_scan/
```

Selected-source fallback outputs use the selected tau in the observed output
root and branch names. The current PPMI fallback is:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau600_observed/
  ulf_peak_efield_tau600_no_delta_hf/
  ulf_peak_efield_tau600_delta_hf_adjusted/
```

Each branch writes observed scores, LOOCV predictions, fiber weights, QC JSON,
and a generation manifest. The branch manifests record `ulf_primary_branch`,
`delta_hfscore_role`, the relevant `hf_norm_fiber_*` source-status fields,
`ulf_norm_fiber_source_status`, `ulf_norm_fiber_prediction_status`,
`ulf_norm_fiber_endpoint_model_status`, selected tau/Coverage fields, and
`resampling_status=not_run_observed_only`.

Current PPMI source resolver and selected-source observed run:

```text
source resolver root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/tau_coverage_source_resolver_scan/
selected output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau600_observed
no_delta_hf:        scan_fallback_accepted + error_nonpredictive; LOOCV Spearman rho = 0.916054, Q2 = 0.0718562
delta_hf_adjusted:  scan_fallback_accepted + error_nonpredictive; LOOCV Spearman rho = 0.908690, Q2 = -0.0597838
endpoint status:    primary_branch_error_nonpredictive
```

The D PPMI observed output is now included in the consolidated status report as
`OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE`. The downstream display-cache
layer has generated density/label outputs for D_PPMI. Formal resampling,
OSS-DBS activation, and FDR/enrichment figure-cache outputs remain deferred
unless the row is promoted.

Current dTOR source resolver and selected-source observed run:

```text
source resolver root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/tau_coverage_source_resolver_scan/
selected output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau400_observed
no_delta_hf:        scan_fallback_accepted + error_nonpredictive; LOOCV Spearman rho = 0.941091, Q2 = -0.0849500
delta_hf_adjusted:  scan_fallback_accepted + error_predictive; LOOCV Spearman rho = 0.946982, Q2 = 0.216921
endpoint status:    primary_branch_error_nonpredictive
```

The D dTOR observed output is included in the consolidated status report as
`OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE`. The matched B_DTOR source is
accepted but `error_nonpredictive`, so the HF-derived intended primary branch is
no-DeltaHF. The D_DTOR ULF tau/Coverage source resolver scan selects
tau400/Coverage>=5 as scan fallback; endpoint realization remains
primary-branch error-nonpredictive because no-DeltaHF is the HF-derived primary.
For D rows, the consolidated status `branch` field must be generated from the
selected-source tau recorded by the source resolver, not from the default
tau800 scan root. Current selected-source rows therefore report
`peak_efield_tau600` for PPMI and `peak_efield_tau400` for dTOR.

## ULF Normative Fiber Same-Day Immediate Endpoint-Family Driver

The D same-day immediate endpoint-family layer is observed-only. It discovers
the same raw clinical `STN+SNr immediate` endpoint rows used by the C immediate
driver, then runs the existing D normative-fiber observed driver and
source-resolver scan for each endpoint/connectome row. Current default
connectomes are PPMI and dTOR. Existing complete endpoint/connectome outputs
are detected and summarized without rerunning unless explicitly forced.

Current observed-only immediate summary:

```text
PPMI / MDS-UPDRS III axial score (STN+SNr, immediate):
  default tau800 no_delta_hf rho = -0.472182; Q2 = -0.115919
  default tau800 delta_hf_adjusted rho = -0.472182; Q2 = -0.115919
  resolver = no_delta_hf scan_fallback tau600/Coverage>=5 + error_nonpredictive
  endpoint status = primary_branch_error_nonpredictive

dTOR / MDS-UPDRS III axial score (STN+SNr, immediate):
  default tau800 no_delta_hf rho = -0.432091; Q2 = -0.513404
  default tau800 delta_hf_adjusted rho = -0.432091; Q2 = -0.513404
  resolver = no_delta_hf scan_fallback tau400/Coverage>=5 + error_nonpredictive
  endpoint status = primary_branch_error_nonpredictive

PPMI / MDS-UPDRS III score (STN+SNr, immediate):
  default tau800 no_delta_hf rho = 0.844512; Q2 = 0.143565
  default tau800 delta_hf_adjusted rho = 0.853355; Q2 = 0.129717
  resolver = both branches scan_fallback tau600/Coverage>=5 + error_nonpredictive
  endpoint status = primary_branch_error_nonpredictive

dTOR / MDS-UPDRS III score (STN+SNr, immediate):
  default tau800 no_delta_hf rho = 0.847460; Q2 = 0.111157
  default tau800 delta_hf_adjusted rho = 0.853355; Q2 = -0.216171
  resolver = both branches scan_fallback tau400/Coverage>=5 + error_predictive
  endpoint status = primary_branch_error_predictive

summary CSV = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/immediate_endpoint_family/normative_ULF_fiber_immediate_endpoint_summary.csv
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_immediate_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_immediate_observed.py
```

## ULF Normative Fiber Gain / Total-ULF Sensitivity Driver

The D-model gain/total-ULF sensitivity layer is observed-only and
chronic-endpoint-only. It runs for the existing D chronic endpoint and for the
current observed D connectomes. Each connectome uses its source selected by the
D source resolver:

```text
PPMI selected source = tau600/Coverage>=5
dTOR selected source = tau400/Coverage>=5
```

The gain endpoint replaces `Y_post` with direction-normalized chronic gain and
uses the selected-source HF-overlap-excluded ULF-only fiber exposure. Its
nuisance covariate is `DeltaHFFiberScore` from the selected-source
delta-HF-adjusted branch.

The total-ULF sensitivity keeps the chronic raw post-score endpoint but uses
the total ULF component fiber exposure from the matched component cache instead
of HF-overlap-excluded ULF-only exposure. Its nuisance covariate is `Y_HF_ref`.

Both outputs are sensitivity branches only:

```text
resampling_status = not_run_observed_only
formal permutation/bootstrap/jitter = not run
same-day immediate endpoint family = not included
```

Current observed-only sensitivity summary:

```text
PPMI normative_fiber_gain_endpoint: rho = 0.5015035512; Q2 = 0.4651291267
PPMI normative_fiber_total_ulf_exposure: rho = 0.9558184151; Q2 = -0.0275760918
dTOR normative_fiber_gain_endpoint: rho = 0.5549181307; Q2 = 0.4987756614
dTOR normative_fiber_total_ulf_exposure: rho = 0.9646549490; Q2 = -0.0813080734
summary CSV = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/sensitivity_observed/normative_ULF_fiber_sensitivity_summary.csv
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_sensitivity_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_sensitivity_observed.py
```

## Configured OSS Runtime Lifecycle And Acceptance Checkpoint

The real MDS-UPDRS III/IV configured acceptance run reached the first HF dTOR
OSS producer. One completed ten-sample source row occupied about 38 GB, while
its accepted candidate-axis and activation-probability outputs occupied less
than 1 MB. The dominant files were per-sample `oss_time_result_PAM.h5` solver
outputs and stimulation workspaces. Retaining those workspaces for every source
row would exceed the available acceptance volume and is not part of the model
artifact contract.

The approved configured lifecycle is:

```text
sample execution
-> persist and hash compact Axon_state/converter/parameter/command provenance
-> validate compact sample record
-> permanently delete that sample's ephemeral solver/stimulation runtime
-> aggregate ten compact sample states
-> atomically validate probability/count artifacts and exact row identity
-> write reusable row checkpoint
-> permanently delete the filtered template and any remaining runtime
```

Accepted row artifacts retain exact activated-count/10 probabilities, canonical
fiber order, source/frequency/transform/toolchain identity, command logs, and
file hashes. They do not retain `oss_time_result_PAM.h5`, copied connectome
trees, segment masks, allocated-axon solver workspaces, or VTK/HDF5 solver
intermediates. A failed row retains compact completed-sample records/logs and
the current failed-sample diagnostics only. Resume reuses a row only after its
identity payload and every compact artifact hash validate.

The interrupted configured run is retained as acceptance evidence, but its
large completed and partial `ephemeral_runtime` trees may be permanently
cleaned. This lifecycle does not alter pPAM probabilities, `p(A) >= 0.5`
thresholding, candidate-axis selection, source resolution, final-model
selection, or any endpoint classification.

The configured implementation now creates one sample runtime at a time, copies
and validates compact sample artifacts before cleanup, deletes successful
sample runtimes, copies the local-to-candidate mapping outside the filtered
template, and deletes the filtered template after row completion. A
content-addressed row checkpoint validates top-level outputs plus nested sample
parameters, converter JSON, `Axon_state`, pathway status, compact manifests,
and command logs. Probability or nested-provenance tampering forces row
regeneration. Final verification passes 29 focused OSS tests, all 307
configured-core tests, Python compilation, and `git diff --check`.

Real compact-row verification completed for the same SNr003 left source and
exact 3,990-fiber axis used by the earlier activation-chain diagnostic. All ten
samples completed, the row retained 1,880 probabilities strictly inside
`(0, 1)`, the mapping retained 3,990 rows with zero invalid candidate columns,
and the final diagnostic directory occupied 140 MB rather than about 38 GB.
It contained ten compact sample manifests, zero stimulation runtime directories,
and zero filtered templates. A second invocation returned
`row_checkpoint_reused=true` in under two seconds without launching OSS. The
evidence directory is:

```text
/Volumes/VAL/STNSNr/configured_model_acceptance_scratch/oss_compact_chain_20260710T1845Z
```

After the real-path same-file mapping repair, missing-entry-tolerant filesystem
cleanup, and malformed-checkpoint cache-miss repair, 29 focused OSS tests and
all 307 configured-core tests pass. Python compilation and `git diff --check`
also pass.

The first clean two-scale acceptance run was stopped after 11 of 34 HF dTOR OSS
source rows completed and 110 compact samples validated. The next row had only
entered parameter preflight; no active sample runtime remained after the stop.
Those 11 checkpoints remain under run
`20260710T183813Z_b28581bfb4ac8f55` and are inputs to the checkpoint-import
acceptance for the bounded scheduler.

The configured scheduler now uses three concurrent source-row workers by
default. Each row retains sequential ten-sample execution and the existing
sample-level cleanup contract. Local exact checkpoints are skipped before
preflight. A new clean-provenance run may also import an exact checkpoint from
an earlier run with the same scientific compatibility and row identities; its
source run, path, and checkpoint hash are recorded. Scheduler implementation
identity is separate from the version-locked scientific generator identity, so
changing only scheduling does not invalidate scientifically identical pPAM
rows. The activation/preflight/merge and MATLAB numerical modules remain
dynamically hashed; only the scheduler service retains the prior scientific
contract hash. Completion order cannot alter merge order, which remains the
planned row index. A row failure prevents final matrix publication while
allowing already running rows to finish their own checkpoints. Full-run resume
with changed code provenance remains prohibited.

The bounded-scheduler RED/GREEN tests verify a default peak of three active
rows, deterministic row-index ordering despite out-of-order completion,
preflight/activation bypass for an exact prior-run checkpoint, same-hash prior
run discovery, and scientific-identity stability across scheduler-only changes.
The focused OSS suite passes 33 tests and the complete configured-core suite
passes 309 tests. Python compilation and `git diff --check` pass. Real
clean-provenance checkpoint-import acceptance remains pending.

The first real three-worker acceptance reached OSS and exposed one checkpoint
import defect before any row completed: `configured_oss_row_v1` included
`final_record_hash`, but that hash changes across runs because final records
contain run-local absolute axis paths and selected-manifest hashes. The
scientific compatibility hash, deterministic final model ID, source hashes,
and 3,990-fiber valid axis were unchanged. The reusable row identity therefore
excludes `final_record_hash`; legacy checkpoints remain eligible only after
their original identity, normalized cross-run identity, ten-sample lattice,
candidate axis, and all nested artifact hashes validate exactly.

The identity repair passes 34 focused OSS tests and all 310 configured-core
tests. A direct audit of the retained row0000 checkpoint reconstructs its
original v1 identity exactly (`f33d574c...bda230`) from the validated row and
stimulation-parameter hash, while its normalized cross-run identity remains
independent of the final-record hash. Python compilation and `git diff --check`
pass. The interrupted three-worker run produced no completed replacement row
and is not an accepted result.

The repaired run then reused all 11 retained rows, completed 23 new rows with
three workers, and closed all 34 HF rows. Final destination publication exposed
a separate pre-existing manifest defect: the publisher required one uniform
modeled frequency although each subject-side frequency had already been
validated exactly and recorded in frequency maps. The manifest contract now
treats those maps as authoritative, emits scalar frequency fields only when
uniform, and uses `frequency_scope = subject_side_specific` otherwise.

The frequency-manifest repair passes 35 focused OSS tests and all 311
configured-core tests. Python compilation and `git diff --check` pass. The 34
completed HF row checkpoints remain reusable inputs for the next
clean-provenance publication run; no OSS row needs regeneration for this
manifest-only repair.

The next clean run imported and published all 34 HF rows in eight seconds, but
the configured OSS consumer still enforced the legacy uniform-frequency scalar.
The consumer now validates either a legacy uniform scalar or exact
subject-side requested/modeled maps with complete `subject_id:L/R` keys,
positive finite values, and pairwise equality. The OSS result preserves the
frequency scope and map. This repair passes 49 focused OSS tests and all 312
configured-core tests, plus Python compilation and `git diff --check`.

Final clean-provenance acceptance run
`20260711T034644Z_d318f177f7f2ac7d` uses commit `e3606e9ba` with
`dirty=false` and the unchanged configuration hash. Its HF dTOR generation
manifest records `row_workers=3`, 34/34 rows reused, zero generated rows, 11
validated legacy imports from run `20260710T183813Z_b28581bfb4ac8f55`, and 23
v2 imports from run `20260710T234453Z_d1b7308d0ae466d0`. Sidecar preparation
completed in six seconds and configured OSS sensitivity completed six seconds
later with `pPAM_probability_ge_0.5`. The subject-side manifest preserves ten
distinct modeled frequencies from 105 to 170 Hz and reports
`verified_exact_match_per_subject_side`. The run was then stopped safely before
unrelated downstream jitter/other endpoints and may be resumed with the same
run ID and code provenance.

During the resumed report-through run, both MDS-UPDRS III ULF direct-voxel
endpoints reached `preprocessing_sidecars` and exposed a configured-adapter
signature defect. The ULF component-exposure service supplies `repo_root`,
`matlab_bin`, `side_paths`, `preprocess_dir`, and `force`, while the configured
`flip_backend` adapter accepted only the final three keywords. The underlying
MATLAB flip backend already supports the complete five-keyword contract, so the
planned repair is limited to widening the configured adapter signature while
continuing to use the repository and MATLAB paths bound by `RunContext`.

The repair was implemented test-first in commit `4eb28907f`. Registry coverage
calls the adapter using the ULF five-keyword shape, and ULF configured-backend
coverage includes a left-sided HF component so a permissive variadic test
callback cannot hide the contract. This is an execution-interface repair only;
it does not change any endpoint, source resolver, branch-role, final-model, or
scientific parameter definition. The current clean-provenance run remains
immutable. Failed ULF direct-voxel tasks must be recovered through a new forced
lineage rooted at run `20260711T034644Z_d318f177f7f2ac7d`, rather than editing
task states or resuming the older code provenance in place.

The same resumed run subsequently exposed a separate ULF normative-fiber OSS
source-wiring defect after the chronic dTOR `no_delta_hf` branch had been
realized and formal inference had completed. The generic OSS preparation path
looked for ULF component source rows in the endpoint preprocessing QC. That QC
correctly contains DeltaHFScore support information only; the authoritative
ULF subject-side rows are branch-specific and live in the selected final
manifest. Exact subject-side validation therefore reported all expected rows
as missing before OSS generation or cache lookup began.

The correction was implemented test-first in commit `5e148df42`. HF OSS source
loading remains unchanged, while ULF normative-fiber OSS loads component rows
from the hash-verified realized-final manifest. Empty source paths still use
the existing deterministic recovery, and duplicate, missing, extra, or
wrong-subject rows still fail exact-set validation. Regression coverage uses
realistic DeltaHF-only preprocessing QC and branch-specific selected-manifest
source rows. This repair changes only OSS sidecar input wiring; it does not
alter the realized final branch or any observed, formal, or jitter result.

## 2026-07-11 Paused Acceptance Snapshot

Execution was paused explicitly by the user without starting another task.
The immutable acceptance run remains:

```text
run_id: 20260711T034644Z_d318f177f7f2ac7d
run_commit: e3606e9ba57e83b61a18883b571ebe184029ebc0
configuration_hash: e686212ba6658b2f4b8abf3a94305817555ec334ee9ba07262fbca9190f5f338
dirty: false
planned_tasks: 205
terminal_tasks: 73
completed: 50
skipped_gate: 1
no_final_model: 2
skipped_dependency: 17
execution_failure: 3
```

The two ULF direct-voxel execution failures are the adapter-signature defect
repaired by `4eb28907f`. The third execution failure is ULF normative-fiber OSS
source wiring repaired by `5e148df42`. These statuses remain valid historical
evidence for the old provenance and must not be edited in place.

The run completed the first HF dTOR normative-fiber endpoint through formal,
OSS, 1,000-replicate spatial jitter, and reporting. It also completed HF MGH
and PPMI observed robustness endpoints. For MDS-UPDRS III chronic ULF dTOR, it
realized `final_9153c815de267bbd0323` from `no_delta_hf`, completed formal,
cheap sensitivity, and selected-source neighborhood tasks, then continued to
spatial jitter after the OSS preparation failure. The safe interruption point
is:

```text
endpoint_model_id: endpoint_0e489d4dae7d51a3fa0c
jitter_task_id: task_83788a6c59239f5b088b
jitter_checkpoint: 388 / 1000
active_model_processes_after_stop: 0
```

The working repository is back on clean branch `stnvop` at `5e148df42`; no
remote operation was performed. Resumption has two distinct steps. First, the
old run may be resumed only at exact commit `e3606e9ba` to continue its
checkpointed acceptance/defect-discovery pass. Second, scientific acceptance
of the two repairs requires a new forced lineage from the old run ID under the
current clean `stnvop` provenance. The forced lineage must rerun the affected
ULF direct-voxel and ULF normative-fiber paths and must not overwrite or repair
the old task-status records.

Run the D PPMI source resolver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome ppmi \
  --source-resolver-scan
```

Run the current D PPMI selected-source observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome ppmi \
  --tau 600 \
  --min-coverage 5
```

Run the D dTOR observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor
```

Run the D dTOR source resolver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor \
  --source-resolver-scan
```

Run the current D dTOR selected-source observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor \
  --tau 400 \
  --min-coverage 5
```
