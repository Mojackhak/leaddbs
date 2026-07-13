# Generic VTA Stimulation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved frequency-group/source/contact contract without changing public JSON field names, preserve current STNSNr stimulation values, and make the MATLAB VTA adapter consume multi-contact voltage/current sources correctly.

**Architecture:** A small project-independent Python contact-fraction module resolves and validates contact allocation before JSON serialization. The STNSNr importer remains a voltage-only source adapter but validates against the expanded generic Schema. MATLAB normalizes legacy single-contact stimulation specs into one canonical contact-array representation, maps fractions into Lead-DBS `S`, and expands continuous versus alternating delivery groups without silently changing physical semantics.

**Tech Stack:** Python 3.11 in Conda `leaddbs`, JSON Schema Draft 2020-12, `unittest`, MATLAB R2024b, existing Lead-DBS Horn/SimBio helpers.

## Global Constraints

- Preserve all existing `study_base.json` key names and nesting.
- Do not add or infer source duty cycle.
- All sources in one frequency group have exactly equal finite positive `frequency_hz`.
- Continuous groups contain at least one source; alternating groups contain at least two sources.
- Observed current allocation has precedence; complete absence infers `1 / n` within one source and polarity; partial allocation is invalid.
- Voltage fractions are exactly `1.0` for every active contact.
- Current fractions sum to `1.0` independently for cathodes and anodes.
- Current STNSNr workbook rows remain voltage controlled and must not change stimulation values.
- Continuous multi-source execution requires a joint-solve-capable backend; unsupported combinations fail explicitly.
- Do not run formal VTA/FEM generation during this implementation slice.

---

### Task 1: Port The Validated Raw-Component Importer Baseline

**Files:**
- Modify: `my_helper/fiber/projects/stnsnr/importer/study_base.py`
- Modify: `my_helper/fiber/projects/stnsnr/importer/tests/test_study_base.py`
- Modify: `my_helper/stnsnr/study_base.schema.json`

**Interfaces:**
- Consumes: the already tested raw-target/per-source-frequency patch from the primary `stnvop` worktree.
- Produces: a clean isolated-branch baseline with `target_stn`/`target_snr`, source-level `frequency_hz`, legacy role rejection, and external-volume-safe atomic publication.

- [x] Apply the exact unstaged three-file diff from `/Users/mojackhu/Github/leaddbs` to this isolated worktree without modifying the primary worktree.
- [x] Run `conda run -n leaddbs python -m unittest projects.stnsnr.importer.tests.test_study_base` from `my_helper/fiber` and require all 25 baseline tests to pass.
- [x] Run `git diff --check`.
- [x] Commit as `feat: preserve raw stimulation components in study base`.

### Task 2: Add The Generic Contact-Fraction Resolver

**Files:**
- Create: `my_helper/fiber/core/stimulation/contact_fraction.py`
- Create: `my_helper/fiber/core/stimulation/tests/test_contact_fraction.py`

**Interfaces:**
- Produces: `resolve_contact_fractions(contacts, control_mode, *, observed_fractions=None, observed_currents=None) -> tuple[float, ...]`.
- Produces: `validate_resolved_contact_fractions(contacts, control_mode, *, tolerance=1e-9) -> None`.
- Raises: `ContactFractionError` for invalid mode, partial allocation, nonfinite/nonpositive allocation, simultaneous fraction/current inputs, or invalid polarity sums.

- [x] Write failing tests for voltage contacts resolving to all `1.0`.
- [x] Write failing tests for complete observed current fractions `0.7/0.3` and complete absolute currents `7/3`.
- [x] Write failing tests for all-missing current allocation resolving to `1 / n` separately for cathodes and anodes.
- [x] Write failing tests proving partial current allocation and mixed fraction/current inputs fail.
- [x] Run the focused tests and verify failure because the module is absent.
- [x] Implement the resolver using polarity-index groups and `math.isfinite`; never normalize incomplete values.
- [x] Run the focused tests and require success.
- [x] Commit as `feat: add canonical contact fraction resolver`.

### Task 3: Expand Study-Base Schema And Semantic Validation

**Files:**
- Modify: `my_helper/stnsnr/study_base.schema.json`
- Modify: `my_helper/fiber/projects/stnsnr/importer/study_base.py`
- Modify: `my_helper/fiber/projects/stnsnr/importer/tests/test_study_base.py`

**Interfaces:**
- Consumes: `validate_resolved_contact_fractions` from Task 2.
- Produces: schema-valid voltage/current, monopolar/bipolar/multipolar source records using unchanged JSON fields.

- [x] Add failing fixture tests for voltage multi-contact, current explicit allocation, current equal inferred allocation after resolution, bipolar electrode return, and multipolar case return.
- [x] Add failing tests for alternating one-source groups, duplicate contacts/case, missing polarity, voltage fraction other than `1.0`, current polarity sums other than `1.0`, and mixed source frequencies.
- [x] Run importer tests and verify failures reflect current `control_mode: const voltage`, one-cathode/case-only semantics, and missing delivery cardinality checks.
- [x] Change `control_mode` to enum `voltage | current`; keep all field names unchanged.
- [x] Add Schema `if/then` cardinality: continuous `minItems: 1`, alternating `minItems: 2`.
- [x] Replace one-cathode/case-only semantic validation with duplicate-contact, polarity-presence, return-mode, fraction, and same-frequency validation.
- [x] Keep the STNSNr workbook adapter voltage-only and emit its current cathode/case values through the voltage resolver.
- [x] Run resolver and importer suites and require success.
- [x] Commit as `feat: validate multi-contact stimulation sources`.

### Task 4: Normalize MATLAB StimSpec Contact Arrays

**Files:**
- Modify: `my_helper/fiber/core/stimulation/mh_fiber_set_stimulation.m`
- Modify: `my_helper/fiber/core/stimulation/mh_fiber_stimspec_from_table.m`
- Modify: `my_helper/fiber/core/stimulation/mh_fiber_make_stim_label.m`
- Create: `my_helper/fiber/tests/test_stimulation_contact_contract.m`

**Interfaces:**
- Canonical source field: `contacts`, a struct array with `contact`, `polarity`, and `fraction`.
- Compatibility input: legacy `contact`, `cathode`, and `anode` fields normalize into canonical contacts before validation.
- Existing single-contact labels remain byte-identical.

- [x] Write a MATLAB test covering legacy normalization, voltage multi-contact, current equal/explicit fraction validation, bipolar return, duplicate contacts, and partial/invalid sums.
- [x] Run MATLAB batch and verify the test fails on missing canonical contact support.
- [x] Normalize legacy sources into contact arrays in `mh_fiber_set_stimulation`.
- [x] Validate side, unit, source amplitude/frequency/pulse width, unique contacts, required polarities, case-return exclusivity, and control-mode-specific fractions.
- [x] Update table conversion to produce canonical contact arrays while preserving existing public arguments.
- [x] Update label generation to preserve legacy labels and deterministically encode multiple numeric contacts.
- [x] Run the MATLAB test and require success.
- [x] Commit as `feat: normalize multi-contact stimulation specs`.

### Task 5: Map Canonical Contacts Into Lead-DBS S

**Files:**
- Create: `my_helper/fiber/core/stimulation/mh_fiber_apply_source_contacts.m`
- Modify: `my_helper/fiber/core/stimulation/mh_fiber_build_stimulation.m`
- Modify: `my_helper/fiber/tests/test_stimulation_contact_contract.m`

**Interfaces:**
- Produces: `S = mh_fiber_apply_source_contacts(S, sourceField, source, numContacts)`.
- Voltage mapping: every active contact has `perc = 100`.
- Current mapping: every active contact has `perc = 100 * fraction`.
- Polarity mapping: cathode `pol = 1`, anode `pol = 2`; `case` maps to `S.(sourceField).case`.

- [x] Extend the MATLAB test with a synthetic `S` and expected voltage/current `perc` and `pol` values.
- [x] Run the test and verify failure because the pure mapping helper is absent.
- [x] Implement the pure helper and replace single-contact writes in `mh_fiber_build_stimulation`.
- [x] Verify monopolar case return, bipolar electrode return, and multipolar current allocation.
- [x] Run the focused MATLAB test and existing static MATLAB tests.
- [x] Commit as `feat: map contact fractions into Lead-DBS stimulation`.

### Task 6: Add Delivery-Group Expansion And Backend Capability Checks

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_expand_delivery_group.m`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_model_registry.m`
- Create: `my_helper/fiber/tests/test_vta_delivery_group_contract.m`

**Interfaces:**
- Produces: `[stimSpecs, executionKind] = mh_vta_expand_delivery_group(group, backendEntry)`.
- Continuous: returns one joint stimSpec containing all group sources.
- Alternating: returns one stimSpec per source.
- Backend flags: `supportsJointVoltage`, `supportsJointCurrent`.
- Raises `mh_vta_expand_delivery_group:UnsupportedBackendCapability` instead of changing solve semantics.

- [x] Write failing MATLAB tests for continuous one/multi-source expansion, alternating two-source expansion, one-source alternating rejection, frequency mismatch, and unsupported joint-current failure.
- [x] Run the test and verify expected failure.
- [x] Implement delivery expansion without duty-cycle or time-weighted fields.
- [x] Add explicit capability flags: `simbio_onesolve` supports joint voltage only; no current backend claims joint current until a simultaneous current solve exists.
- [x] Run focused MATLAB tests and require success.
- [x] Commit as `feat: expand VTA delivery groups deterministically`.

### Task 7: Generate And Compare Real Study Bases

**Files:**
- Generate: `/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json`
- Create run-scoped comparison report outside the authoritative JSON, under `/Volumes/VAL/STNSNr/summary/cohort/subj/study_base_audit/`.

**Interfaces:**
- Compares the Task 1 raw-component baseline with the final implementation using identical source workbooks, fixed `created_at`, and fixed `code_commit` so provenance does not create false differences.
- Records `study.provenance.importer.code_commit` from the repository containing the importer implementation, not from the configured Lead-DBS asset root.

- [x] Generate `before.json` from the Task 1 commit in a temporary detached worktree.
- [x] Generate `after.json` from final HEAD with identical fixed provenance.
- [x] Validate both against their corresponding Schema.
- [x] Write a machine-readable recursive JSON diff and aggregate count summary.
- [x] Require no stimulation-value differences for the current all-voltage cohort: subjects `16`, scales `28`, slots `2240`, sources `194`, HF audit `142`, ULF audit `52`, unclassified `0`, and all fractions `1.0`.
- [x] Move the previous external authoritative JSON to Trash, generate the final JSON atomically, and validate the on-disk file.
- [x] Verify the generated `code_commit` equals the implementation worktree HEAD used for generation.
- [x] Run all Python importer/resolver tests, focused MATLAB contract tests, and `git diff --check`.
- [x] Commit code and audit tooling only; do not commit external generated data.

## Final Acceptance

- Public JSON field names are unchanged.
- Current real stimulation data are unchanged after provenance normalization.
- The generated real JSON is Schema-valid and contains no partial allocation.
- Generic tests demonstrate current explicit, inferred, and invalid allocation behavior.
- MATLAB maps voltage/current contacts into Lead-DBS `S` without dropping contacts.
- Delivery expansion distinguishes simultaneous continuous from independent alternating states.
- No FEM, formal model, OSS, coverage, or fiber analysis is run in this slice.

## Implementation Record

- Status: `implemented_and_verified`
- Implementation branch: `codex/vta-stimulation-contract`
- Final importer commit used for generation: `ec5593a6aff1917ed4215b218a44313280eb5876`
- Generated study base: `/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json`
- Audit directory: `/Volumes/VAL/STNSNr/summary/cohort/subj/study_base_audit/20260712T205428_vta_stimulation_contract`
- Fixed-provenance generator comparison: byte-identical, zero differences.
- On-disk comparison: only `created_at` and importer `code_commit` differ; data differences after provenance normalization are zero.
- Final tests: 39 Python tests and both MATLAB stimulation-contract tests passed.
- Execution boundary: no FEM/VTA generation or downstream model run was performed.
