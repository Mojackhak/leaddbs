# STNSNr Normative Fiber OSS / pPAM Generation Plan

> **Purpose.** This is the `/goal` sub-plan document for generating OSS-DBS / pPAM activation sidecars for STNSNr normative fiber final dTOR branches.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_execution_plan.md`
> **Authoritative model specs.** `my_helper/stnsnr/model_summaries/`
> **Status.** Input audit/worklist, parameter preflight, and row-level activation harness implemented; full B_DTOR/D_DTOR parameter preflight passes 64/64 rows; full B_DTOR/D_DTOR row-level activation reaches `pathway_activation_complete` for 64/64 rows; no final branch OSS sidecars have been merged yet.

---

## Summary

Generate OSS-DBS / probabilistic pathway activation modeling (pPAM) activation sidecars only for the final dTOR normative fiber branches. OSS/pPAM is an activation sensitivity layer, not a primary model and not a tau/Coverage resolver.

The core operation is to keep the final branch subject rows and selected-source
candidate fiber columns unchanged, then replace the peak-E-field exposure value
with a continuous pPAM activation probability:

```text
same subject rows
same selected-source candidate fiber columns
peak E-field value -> pPAM activation probability
```

The canonical output is:

```text
X_oss_float32_fiber_major.npy
```

with rows = subjects and columns = the selected-source candidate fiber id order.
This order must be written explicitly as `oss_fiber_ids.npy` or recorded in the
OSS sidecar manifest. A parent exposure `fiber_ids.npy` that contains the raw
dTOR atlas or full exposure id universe is not the OSS sidecar column contract.

## Goal

Produce valid OSS sidecar inputs so current normative-fiber readiness can move from:

```text
not_run_missing_oss_inputs
```

to:

```text
ready_for_oss_sensitivity
```

for the HF and ULF dTOR normative fiber final branches.

This plan does not complete the downstream OSS sensitivity model itself. A later execution step must consume `X_oss_float32_fiber_major.npy` and compute OSS weights, scores, LOOCV predictions, smoke permutation, and plain OSS activation controls.

## Executable Input Audit / Worklist

Before running expensive OSS-DBS / pPAM jobs, run a read-only worklist audit:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_oss_sidecar_worklist.py
```

The audit writes:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_oss_sidecar_worklist/normative_fiber_oss_sidecar_input_audit.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_oss_sidecar_worklist/normative_fiber_oss_sidecar_worklist.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_oss_sidecar_worklist/normative_fiber_oss_sidecar_worklist_manifest.json
```

This layer does not create `X_oss_float32_fiber_major.npy`, does not mark
`ready_for_oss_sensitivity`, and does not run downstream OSS fitting. It checks
the final dTOR target manifests, branch score subject order, selected-source
candidate fiber id order, required sidecar paths, and source stimulation paths
that must be passed to the true OSS/pPAM execution layer. A branch can proceed to actual
OSS sidecar generation only when this audit reports complete subject coverage,
existing source stimulation inputs, and no pre-existing invalid sidecar files.
The audit writes workflow-local `candidate_fiber_ids/<MODEL>_oss_fiber_ids.npy`
files derived from the selected-source weights table. These files define the
OSS candidate column order for downstream preflight and row-level activation
bookkeeping, but they are not final branch OSS sidecars and do not by themselves
make the branch `ready_for_oss_sensitivity`.
For ULF alternating-program rows, if the generation manifest has an empty ULF
`source_paths` entry but the corresponding
`stnsnr_vta_<subject>_3m_STNplusSNr_alt_<side>_SNr_*` e-field folder exists in
the derivatives tree, the audit may recover that source path and must label the
row `recovered_derivatives_ulf_alt_snr`.

The existing Lead-DBS `sub-*_desc-stimparameters.mat` files are not themselves
valid `leaddbs2ossdbs` input dictionaries. A converter smoke test showed that
the OSS-DBSv2 converter expects an HDF5/v7.3 MAT file containing a top-level
`settings` object, not only the Lead-DBS `S` stimulation structure. Therefore the
true sidecar generator must first run the Lead-DBS MATLAB OSS preparation path
(`ea_prepare_ossdbs` / `ea_save_ossdbs_settings`, or an equivalent batch wrapper)
to create the OSS parameter dictionary before calling `leaddbs2ossdbs`, `ossdbs`,
and `run_pathway_activation`.

## OSS Parameter-Dictionary Preflight

Before running full pPAM activation sidecars, run a bounded parameter-dictionary
preflight on worklist rows. This layer verifies the MATLAB-to-OSS-DBSv2 bridge
without claiming OSS sensitivity readiness.

The preflight must:

```text
read normative_fiber_oss_sidecar_worklist.csv
choose final dTOR worklist rows
load the source Lead-DBS stimulation S structure
run the Lead-DBS MATLAB OSS preparation path
write an HDF5/v7.3 oss-dbs_parameters.mat with top-level settings
populate stimulation protocol fields including Phi_vector and current_control
lock the OSS connectome to dTOR-985 Full (Elias 2024)
run leaddbs2ossdbs converter smoke on the generated parameter file
validate and, if needed, patch the converter JSON stimulation frequency from the source S frequency
write row-level status and manifest outputs
```

The MATLAB preparation path must include the stimulation-source and protocol
steps that are required before `ea_save_ossdbs_settings`:

```text
ea_prepare_ossdbs
ea_get_oss_outputPaths
ea_segment_MRI
ea_prepare_DTI
ea_get_oss_reco
ea_check_stimSources
ea_get_stimProtocol
ea_prepare_fibers
ea_save_ossdbs_settings
```

Because required OSS sidecars are limited to the final dTOR normative fiber
branches, this preflight must not rely on a GUI/default OSS connectome. It must
set the OSS connectome explicitly to:

```text
dTOR-985 Full (Elias 2024)
```

If the generated MAT file lacks a top-level `settings` object, or if the
generated `settings` lacks required converter fields such as `Phi_vector`,
`current_control`, implantation coordinates, or `pathwayParameterFile`, the row
must be marked as a parameter-preflight failure. The runner must not fall back
to the original `sub-*_desc-stimparameters.mat` file as converter input.

The current OSS-DBSv2 `leaddbs2ossdbs` converter hard-codes
`StimulationSignal.Frequency[Hz] = 130.0` in its generated JSON. The STNSNr
sidecar layer must therefore read the active source frequency from the Lead-DBS
`S` structure, compare it with the converter JSON, and patch the JSON frequency
when they differ. A row is valid only when the final JSON satisfies:

```text
oss_json_frequency_hz = source_stimulation_frequency_hz
```

This is required for both HF and ULF branches. It prevents a silent 130 Hz
fallback and must be recorded in the row manifest.

The converter `--output_path` must be the same Lead-DBS OSS output directory
that contains `oss-dbs_parameters.mat` and the filtered connectome files
(`data1.mat`, `data2.mat`, ...). Do not redirect converter JSON to a separate
folder, because downstream `prepareaxonmodel` resolves pathway files relative
to the converter output path.

The converter JSON `StimulationFolder` should also point to that same Lead-DBS
OSS output directory for path consistency. However, OSS-DBSv2 CLI overwrites
`StimulationFolder` at runtime with the parent directory of the input JSON file
before writing success/failure marker files. Therefore the row-level runner must
keep the copied converter JSON inside the row sandbox and accept the OSS success
marker in either location:

```text
<row_dir>/success_<FailFlag>.txt
<filtered_stimulation_folder>/success_<FailFlag>.txt
```

The row is `ossdbs_complete` only when one accepted success marker exists and
`Results/oss_time_result_PAM.h5` exists under the filtered stimulation folder.

## Resumable Row-Level Activation Runner

After parameter-dictionary preflight passes, full sidecar generation must run
as a resumable row-level activation workflow. It must not be run as a
single interactive shell command because `prepareaxonmodel` can spend many
minutes converting dTOR fibers to streamlines for one subject-side-source row.

The row-level runner executes:

```text
prepareaxonmodel
ossdbs
run_pathway_activation
```

for selected preflight rows. It writes row-local logs and a row-local status
manifest after each step. A row can resume from the first incomplete step when
the previous step's expected outputs and return code are already present.
When a step is launched through an absolute OSS-DBSv2 executable path, the runner
must prepend that executable's parent directory to `PATH`. This is required for
`run_pathway_activation`, which shells out to NEURON's `nrnivmodl` from the same
OSS-DBSv2 environment.

`run_pathway_activation` may write pathway-name-qualified status files. For the
current generated pathway file, the default pathway output is:

```text
Pathway_status_default_<scaling_index>.json
```

The row-level runner must therefore accept either the generic
`Pathway_status_<scaling_index>.json` path or the pathway-qualified
`Pathway_status_default_<scaling_index>.json` path when deciding whether pathway
activation completed.

Recommended command:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_oss_activation_rows.py \
  --one-row-per-model \
  --max-rows 2
```

The command above is a smoke/probe form. The current full row-level execution
uses:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_oss_activation_rows.py \
  --max-rows 0 \
  --stop-after-step all \
  --pathway-timeout-s 120
```

This runner still does not write final branch readiness files:

```text
X_oss_float32_fiber_major.npy
oss_parameter_manifest.json
oss_activation_sidecar_metadata.json
```

Those final branch files are written only after all required subject-side-source
rows for a branch have completed pPAM activation and have been projected onto
the selected-source candidate fiber id order with the declared
`max_probability_union` merge rule. Row-level `pathway_activation_complete`
therefore proves that the OSS/pPAM row calculation finished; it does not by
itself prove that the branch-level `X_oss_float32_fiber_major.npy` sidecar is
ready.

Required row-level outputs:

```text
normative_fiber_oss_activation_row_summary.csv
normative_fiber_oss_activation_row_manifest.json
row*/prepareaxonmodel_stdout.log
row*/prepareaxonmodel_stderr.log
row*/ossdbs_stdout.log
row*/ossdbs_stderr.log
row*/run_pathway_activation_stdout.log
row*/run_pathway_activation_stderr.log
row*/oss_activation_row_status.json
```

Required merge-bookkeeping output for each completed row:

```text
row*/oss_local_to_candidate_fiber_mapping.csv
```

This file must map the OSS filtered local axon/status index back to the
selected-source candidate fiber id order. Required fields:

```text
row_index
model_id
subject_id
side
filtered_stimulation_folder
local_axon_index
filtered_local_fiber_id
source_local_fiber_id
selected_candidate_fiber_id
candidate_column_index
oss_fiber_ids_path
```

The branch merge layer must not infer candidate-fiber alignment from the
filtered connectome `idx` vector alone. That vector stores filtered local fiber
point counts, not the selected-source candidate fiber ids.

Row status vocabulary:

```text
pending
prepareaxonmodel_complete
prepareaxonmodel_failed
ossdbs_complete
ossdbs_failed
pathway_activation_complete
pathway_activation_failed
timeout_or_interrupted
```

If a long-running command is interrupted, record the partial status and keep
the output directory for resume/debugging. Do not mark the row complete unless
the expected success marker or activation output exists.

Current execution checkpoint:

```text
normative_fiber_oss_activation_row_summary.csv rows = 64
B_DTOR rows = 32
D_DTOR rows = 32
row_status = pathway_activation_complete for 64/64 rows
code provenance = clean stnvop commit 6e5c4aa3d
```

The remaining branch-level blocker is not row execution. It is the merge layer:
complete local-to-candidate mapping files and a locked interpretation of the
OSS `Status`/p(A) output are required before writing canonical branch sidecars.

Preflight outputs live outside the final branch preprocess directory until they
pass validation. They do not create:

```text
X_oss_float32_fiber_major.npy
oss_parameter_manifest.json
oss_activation_sidecar_metadata.json
```

and they do not change:

```text
oss_sensitivity_status
ready_for_oss_sensitivity
source status
prediction status
final branch selection
```

Recommended output root:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_oss_parameter_preflight/
```

Required preflight summary files:

```text
normative_fiber_oss_parameter_preflight_summary.csv
normative_fiber_oss_parameter_preflight_manifest.json
```

## Model Role

OSS/pPAM does not alter:

```text
tau/Coverage source resolver
HF/ULF source status
HF/ULF prediction status
endpoint model status
final branch selection
DeltaHFScore source
FDR cache
enrichment cache
jitter inputs
```

OSS/pPAM answers only:

```text
Does the peak-E-field normative fiber pattern remain directionally and spatially interpretable when the exposure variable is replaced by modeled axon/pathway activation probability?
```

## Target Branches

Generate OSS sidecars only for:

```text
HF normative fiber final dTOR branch
ULF normative fiber final dTOR branch
```

Do not generate required OSS sidecars for:

```text
PPMI observed robustness branches
MGH observed robustness branches
direct voxel models
tau/Coverage scan branches
non-final sensitivity branches
```

## Fiber Universe

The OSS sidecar does not use the whole dTOR connectome atlas as its final matrix column set.

The source pool is:

\[
F_{\mathrm{dTOR\ atlas}}
\]

but the sidecar column universe is inherited from the already selected final branch:

\[
F_{\mathrm{candidate,selected}}
=
\{f \in F_{\mathrm{dTOR\ atlas}}:
Coverage_{\tau_{\mathrm{selected}}}(f)
\ge Coverage_{\mathrm{selected}}\}
\]

The sidecar columns must exactly equal the selected-source candidate fiber id
order for the final executable branch:

```text
oss_fiber_ids.npy, or an equivalent manifest-recorded selected candidate id order
```

Therefore:

```text
X_oss rows    = final branch subjects
X_oss columns = selected-source candidate fiber ids
```

OSS must not redefine, shrink, expand, or rescan the candidate fiber universe.
If a branch-level `fiber_ids.npy` stores the raw dTOR atlas or parent exposure id
universe, it is only the source pool from which `F_candidate,selected` is derived;
it is not the final OSS column set.

## Core Exposure Replacement

Non-OSS normative fiber model:

\[
X_{i,f}
=
\text{peak E-field exposure for subject } i \text{ on fiber } f
\]

OSS / pPAM sensitivity:

\[
X^{OSS}_{i,f}
=
p(A_{i,f})
\]

The replacement is:

```text
same subject rows
same selected-source candidate fiber columns
peak E-field value -> pPAM activation probability
```

## pPAM Probability Definition

For subject \(i\) and fiber \(f\):

\[
p(A_{i,f})
=
\frac{
\#\{\text{pPAM samples where fiber } f \text{ is activated in subject } i\}
}{
N_{\mathrm{samples}}
}
\]

The primary stored value is continuous \(p(A)\), not a binary thresholded activation.

Display/QC thresholds only:

```text
loose activation  = p(A) >= 0.05
strict activation = p(A) >= 0.5
```

These thresholds do not change the stored matrix and do not replace canonical OSS fitting.

## Canonical Output Matrix

Required output:

```text
X_oss_float32_fiber_major.npy
```

Contract:

```text
shape = n_subjects x n_fibers
dtype = float32
range = [0, 1]
row order = final branch manifest / score table subject order
column order = selected-source candidate fiber id order
value = continuous pPAM activation probability
```

HF and ULF both use this same canonical filename. Distinguish HF versus ULF by path and manifest fields, not by changing the matrix filename.

Do not use the old ULF-specific name as canonical:

```text
X_ULF_OSS_activation_float32_fiber_major.npy
```

## Right-Canonical Hemisphere Rule

The feature space remains right-canonical.

Right-side stimulation:

\[
p(A^R_{i,f})
\]

is already expressed on right-canonical fiber \(f\).

Left-side stimulation is first modeled in the real left hemisphere, then mapped to the right-canonical homologous fiber:

\[
p(A^{L \rightarrow R}_{i,f})
\]

Final canonical OSS exposure:

\[
X^{OSS}_{i,f}
=
\max\left(
p(A^R_{i,f}),
p(A^{L \rightarrow R}_{i,f})
\right)
\]

This is the accepted `max_probability_union` rule.

Interpretation:

```text
Left stimulation is not moved anatomically to the right side.
Left activation is computed in the left hemisphere first.
The resulting left fiber activation is then represented on the right-canonical homologous fiber id.
If either side activates the homologous fiber, the subject-level canonical value keeps the larger p(A).
```

## Why Max Instead Of Mean

Use `max p(A)` as the canonical OSS exposure.

Rationale:

```text
pPAM is an activation probability / activation certainty metric.
Mean p(A) represents bilateral average activation burden and can dilute unilateral high-confidence activation.
Max p(A) represents activation union with fewer assumptions than probabilistic union.
Lead-DBS OSS multi-source PAM handling uses disjunction/union semantics, not averaging.
```

Mean may be reported only as descriptive burden sensitivity:

```text
X_oss_mean_bilateral_descriptive
```

It must not replace the canonical `X_oss_float32_fiber_major.npy`.

Do not use probabilistic union as the primary rule:

\[
1-(1-p_R)(1-p_L)
\]

because it assumes independence between left and right activation events.

## Locked OSS / pPAM Parameters

Use:

```text
OSS model = OSS-DBSv2
activation model = pPAM
deterministic PAM = fallback/debugging only

cond_model = ColeCole4
conductivity = isotropic
patient DTI anisotropic conductivity = not used

probabilistic_parameter = Fiber Diameter
fiber_diameter_range = [1, 4] um
sampling_distribution = Equidistant
N_samples = 10
sample_diameters = linspace(1, 4, 10)
```

Do not use patient DTI anisotropic conductivity because the available DTI slice thickness is 5 mm, which is too low for reliable STN/SNr conductivity tensor modeling.

## Frequency Validation Requirement

Before a sidecar can be valid, the OSS JSON frequency must satisfy:

```text
requested_frequency_hz == oss_parameter_frequency_hz
```

Required behavior:

```text
Read the real subject/side/source frequency from Lead-DBS stimulation protocol.
Run leaddbs2ossdbs.
Patch StimulationSignal.Frequency[Hz] in the generated JSON if needed.
Re-read the JSON.
Validate requested_frequency_hz == oss_parameter_frequency_hz.
Record validation in manifest.
```

ULF rule:

```text
ULF sidecar is invalid if it silently uses an unverified 130 Hz fallback.
```

Manifest fields must include:

```text
requested_frequency_hz
oss_parameter_frequency_hz
frequency_source
frequency_modeled
frequency_validation_status
```

## HF Sidecar Definition

HF normative fiber OSS sidecar:

```text
model_family = HF_normative_fiber
oss_exposure_component = HF_only_reference
OSS input = HF-only reference stimulation component
frequency = actual HF frequency
fiber universe = selected HF dTOR final-branch candidate fiber ids
```

Candidate fibers are inherited from the peak-E-field final branch's
selected-source tau/Coverage candidate set. Record the actual sidecar column
order as `oss_fiber_ids.npy` or as an equivalent manifest field.

## ULF Sidecar Definition

ULF normative fiber OSS sidecar:

```text
model_family = ULF_normative_fiber
oss_exposure_component = ULF_addon_component
OSS input = ULF add-on component
frequency = actual ULF frequency
fiber universe = selected ULF dTOR realized-primary candidate fiber ids
```

Candidate fibers are inherited from the realized primary ULF branch's
selected-source tau/Coverage candidate set. Record the actual sidecar column
order as `oss_fiber_ids.npy` or as an equivalent manifest field.

If the ULF component cannot be separated from the stimulation protocol, generate only:

```text
HF+ULF total OSS pPAM sensitivity
```

and record:

```text
oss_exposure_component = HF_ULF_total_sensitivity
ulf_only_oss_status = not_available_component_not_separable
```

Do not call this output ULF-only OSS.

## ULF HF-Overlap Rule

ULF OSS inherits the final ULF branch candidate universe and HF-overlap exclusion rule.

HF-overlap is still defined by the matched HF peak-E-field selected source:

\[
HF\_touched_i(f)
=
X^{HF\_component}_i(f)
>
\tau^{HF}_{selected}
\]

If the matched HF source is absent:

\[
HF\_touched_i(f) = false
\]

ULF-only OSS exposure:

\[
X^{ULF-only,OSS}_{i,f}
=
\begin{cases}
X^{OSS,ULF}_{i,f}, & f \in F^{ULF}_{candidate}\ \text{and}\ HF\_touched_i(f)=false \\
0, & otherwise
\end{cases}
\]

Do not use HF OSS activation to redefine HF-overlap.

DeltaHFScore remains the matched HF normative fiber score projection. It is not replaced by HF OSS score.

## Output Location

Write the three required sidecar files under each final branch `preprocess_dir`:

```text
<final_branch_preprocess_dir>/
  X_oss_float32_fiber_major.npy
  oss_parameter_manifest.json
  oss_activation_sidecar_metadata.json
```

The readiness code resolves `preprocess_dir` from the branch generation manifest when available. If not available, it falls back to:

```text
<branch_dir>/preprocess/
```

ULF normative fiber selected-source branch manifests may store branch outputs
under `branch_dir` while the shared component and ULF-only exposure sidecars live
one level higher in the selected-source exposure `preprocess` directory. For
those D_DTOR targets, if `outputs.preprocess_dir` is absent, the OSS worklist
and sensitivity-readiness code must use the directory that contains the selected
`X_ULF_only_fiber...` exposure matrix (`target.x_path.parent`) rather than fabricating
`<branch_dir>/preprocess/`.

## Required Manifest Fields

`oss_parameter_manifest.json` must record:

```text
OSS-DBS version
Lead-DBS commit
conda environment name
conda environment path
python version
OSS executable paths
subject order
subject order hash
oss_fiber_ids path
oss_fiber_ids hash
parent fiber_ids path, when different from oss_fiber_ids
parent fiber_ids hash, when different from oss_fiber_ids
connectome name
model_family
branch id
endpoint id
selected tau
selected Coverage
frequency requested/modeled
frequency validation status
pulse width
amplitude/current
waveform
cond_model
conductivity model
DTI anisotropy use status
pPAM enabled
fiber diameter range
sampling distribution
N_samples
sample diameters
activation output definition
right-canonical mapping rule
left-to-right mapping method
merge rule = max_probability_union
missing subject list
failed subject list
```

`oss_activation_sidecar_metadata.json` must record:

```text
matrix path
shape
dtype
min value
max value
finite check status
subject order source
oss fiber id source
oss fiber id hash
parent fiber id source, when different from oss fiber ids
row count
column count
activation value type = continuous_pPAM_probability
display threshold loose = 0.05
display threshold strict = 0.5
hemisphere/source merge rule = max_probability_union
created_at
code provenance
```

## Valid Sidecar Criteria

A branch-level OSS sidecar is valid only if all are true:

```text
frequency modeled and verified
pPAM samples completed
subject order matched
oss fiber id order matched to selected-source candidate ids
X_oss written
X_oss dtype = float32
X_oss shape = n_subjects x n_fibers
all X_oss values finite
min(X_oss) >= 0
max(X_oss) <= 1
manifest complete
no silent 130 Hz fallback for ULF
```

If a subject OSS run fails:

```text
subject_status = oss_failed
branch_status = incomplete
```

Do not silently fill the subject row with zeros and mark it valid unless a missing-subject tolerance is explicitly approved later.

## QC Summary Outputs

Recommended branch-level QC summaries:

```text
per-subject activated fiber count at p(A) >= 0.05
per-subject activated fiber count at p(A) >= 0.5
median p(A)
max p(A)
nonzero p(A) fraction
missing hemisphere count
missing source count
failed subject list
frequency validation summary
```

Optional descriptive outputs:

```text
X_oss_mean_bilateral_descriptive.npy
X_oss_right_only_descriptive.npy
X_oss_left_to_right_only_descriptive.npy
```

These optional outputs must not be consumed as canonical OSS exposure.

## Readiness Integration

Current readiness expects exactly:

```text
X_oss_float32_fiber_major.npy
oss_parameter_manifest.json
oss_activation_sidecar_metadata.json
```

When all three exist in final branch `preprocess_dir`, readiness can change from:

```text
not_run_missing_oss_inputs
```

to:

```text
ready_for_oss_sensitivity
```

This only means OSS input sidecar readiness. It does not mean OSS sensitivity results have been computed.

## Downstream OSS Sensitivity Results

After sidecar readiness, a later runner must consume `X_oss_float32_fiber_major.npy` and compute:

```text
M_OSS
SweetPeak5_OSS
SourPeak5_OSS
NetFiberScore_OSS
LOOCV predictions
smoke Freedman-Lane permutation
plain OSS activation burden control
```

Default OSS sensitivity uses smoke permutation only:

```text
B = 1000
seed = 42
```

Any `B=10000` OSS permutation/bootstrap layer requires a separate model-document revision.

Canonical OSS fitting uses continuous \(p(A)\). Thresholded \(p(A) \ge 0.05\) or \(p(A) \ge 0.5\) variables are QC/display/plain-burden controls only. They do not replace `X_oss_float32_fiber_major.npy` in `M_OSS`, `NetFiberScore_OSS`, LOOCV, or smoke permutation.

## Status Semantics

If sidecars are absent:

```text
oss_sensitivity_status = not_run_missing_oss_inputs
```

If sidecars exist but fail validity checks:

```text
oss_sensitivity_status = failed_invalid_oss_sidecar
```

If pPAM activation is all zero or nearly tied:

```text
oss_sensitivity_status = failed_activation_degenerate
```

If OSS is technically valid but disagrees with peak-E-field result:

```text
oss_sensitivity_status = passed_activation_model_dependent
```

If OSS is technically valid and directionally/spatially supports peak-E-field result:

```text
oss_sensitivity_status = passed_activation_consistent
```

## Documentation Synchronization Targets

Synchronize these documents with this plan:

```text
my_helper/stnsnr/four_model_execution_plan.md
my_helper/stnsnr/four_model_execution_implementation_notes.md
my_helper/stnsnr/endpoint_specific_sweetspot_plan.md
my_helper/stnsnr/model_summaries/hf_3m_normative_connectome_fiber_model.md
my_helper/stnsnr/model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md
```

## Documentation Test Plan

Run:

```bash
git diff --check
```

Check old/conflicting terms:

```bash
rg -n "X_ULF_OSS_activation|averaged.*X_HF_OSS|\\(A_R.*A_L\\) / 2|whole.*connectome atlas|OSS.*redefine.*candidate|ULF-only OSS.*HF\\+ULF total" my_helper/stnsnr -g '*.md'
```

Allowed hits are only explicit "do not use", "not the whole atlas", "must not redefine", or test-plan text in this document. Any hit that defines old behavior as canonical must be removed or rewritten.

Check required new terms:

```bash
rg -n "X_oss_float32_fiber_major|max_probability_union|continuous pPAM activation probability|requested_frequency_hz|oss_parameter_frequency_hz|HF\\+ULF total OSS pPAM sensitivity|fiber_ids.npy" my_helper/stnsnr -g '*.md'
```

No Python tests or model runs are required for the documentation-only pass.

## Assumptions

- This document is the OSS/pPAM sidecar contract. Row-level OSS outputs may
  exist under the workflow summary directory, but final branch sidecar readiness
  requires `X_oss_float32_fiber_major.npy`, `oss_parameter_manifest.json`, and
  `oss_activation_sidecar_metadata.json` under the final branch preprocess
  directory.
- OSS sidecar generation is limited to final dTOR normative fiber branches.
- Canonical OSS exposure uses right-canonical fiber columns with left activation mapped to right-canonical ids.
- Canonical hemisphere/source merge rule is `max_probability_union`.
- Mean bilateral p(A) is allowed only as a descriptive burden sensitivity.
- FDR cache, enrichment cache, and jitter QC remain separate layers. FDR and enrichment cache definitions are maintained in `my_helper/stnsnr/normative_fiber_fdr_enrichment_cache_definition.md`; they are not generated by this OSS/pPAM sidecar plan.
