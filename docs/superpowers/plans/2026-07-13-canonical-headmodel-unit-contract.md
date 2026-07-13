# Canonical Head-Model Unit Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject canonical Lead-DBS head models whose mesh and FEM volume coordinates do not satisfy the approved millimeter/meter contract.

**Architecture:** Add one side-effect-free MATLAB validator. Reused models receive an early check in the head-model preparer, while the canonical backend applies the authoritative check immediately after every load so reused and newly built paths are covered before boundary assembly.

**Tech Stack:** MATLAB function-based unit tests, Lead-DBS canonical VTA MATLAB pipeline, Git.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-07-13-canonical-headmodel-unit-contract-design.md`.
- Write code, comments, identifiers, and tests in English.
- Run MATLAB commands in the `leaddbs` Conda environment.
- Convert both coordinate arrays to `double` before comparison.
- Use an absolute node-wise tolerance of `1e-6 m`.
- Treat `mesh.unit` as optional; when present it must equal `mm`, case-insensitively.
- Require `max(abs(double(vol.pos(:)))) < 2 m`.
- Never repair, overwrite, or rescale an invalid head model automatically.
- Do not require a suprathreshold VTA voxel.

---

## File Map

- Create `my_helper/fiber/core/stimulation/model/mh_vta_validate_canonical_headmodel_units.m`: pure validator using `mh_vta:InvalidCanonicalHeadmodelUnits`.
- Create `my_helper/fiber/tests/test_vta_headmodel_unit_contract.m`: unit, integration, and backend call-order tests.
- Modify `my_helper/fiber/core/stimulation/model/mh_vta_prepare_canonical_headmodel.m`: early validation for reused models.
- Modify `my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve_canonical.m`: mandatory post-load validation.
- Modify `my_helper/fiber/tests/test_vta_common_grid_export.m`: valid mm/m Horn builder fixture.

### Task 1: Add The Pure Coordinate-Unit Validator

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_validate_canonical_headmodel_units.m`
- Create: `my_helper/fiber/tests/test_vta_headmodel_unit_contract.m`

**Interfaces:**
- Consumes: `vol.pos`, `mesh.pnt`, and optional `mesh.unit`.
- Produces: `mh_vta_validate_canonical_headmodel_units(vol, mesh)`, returning normally on success and throwing `mh_vta:InvalidCanonicalHeadmodelUnits` on violation.

- [ ] **Step 1: Write the failing tests**

Create `test_vta_headmodel_unit_contract.m` as a MATLAB function-based suite
with this header and fixture:

```matlab
function tests = test_vta_headmodel_unit_contract
% Validate canonical mesh/volume coordinate units before FEM execution.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
testCase.TestData.repoDir = repoDir;
end

function [vol, mesh] = valid_fixture(precision, includeUnit)
pointsMm = cast([0, 0, 0; 10, -20, 30; -40, 50, -60], precision);
mesh = struct('pnt', pointsMm);
if includeUnit
    mesh.unit = 'mm';
end
vol = struct('pos', cast(double(pointsMm) / 1000, precision));
end
```

Add these exact test cases:

```matlab
function testAcceptsDoubleCoordinatesWithoutUnitField(testCase)
[vol, mesh] = valid_fixture('double', false);
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testAcceptsSingleCoordinatesWithMillimeterUnit(testCase)
[vol, mesh] = valid_fixture('single', true);
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsVolumeCoordinatesStoredInMillimeters(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos = double(mesh.pnt);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsPresentNonMillimeterUnit(testCase)
[vol, mesh] = valid_fixture('double', true);
mesh.unit = 'm';
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsJointlyMisScaledCoordinatesOutsideRange(testCase)
mesh = struct('pnt', [0, 0, 0; 3000, 0, 0], 'unit', 'mm');
vol = struct('pos', double(mesh.pnt) / 1000);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonfiniteCoordinates(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = Inf;
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsCoordinateShapeAndNodeCountMismatch(testCase)
[vol, mesh] = valid_fixture('double', true);
invalidShape = mesh;
invalidShape.pnt = zeros(2, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, invalidShape), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
fewerNodes = mesh;
fewerNodes.pnt = fewerNodes.pnt(1:2, :);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, fewerNodes), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end
```

- [ ] **Step 2: Verify RED**

```bash
conda run -n leaddbs matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_headmodel_unit_contract.m'); assertSuccess(run(r));"
```

Expected: FAIL because `mh_vta_validate_canonical_headmodel_units` is undefined.

- [ ] **Step 3: Implement the validator**

Create `mh_vta_validate_canonical_headmodel_units.m`:

```matlab
function mh_vta_validate_canonical_headmodel_units(vol, mesh)
% Validate canonical millimeter mesh and meter volume coordinates.

meshPoints = coordinate_array(mesh, 'pnt', 'mesh.pnt');
volumePoints = coordinate_array(vol, 'pos', 'vol.pos');
if size(meshPoints, 1) ~= size(volumePoints, 1)
    invalid_contract('mesh.pnt and vol.pos must contain the same number of nodes.');
end
if isfield(mesh, 'unit')
    unit = mesh.unit;
    isTextScalar = (ischar(unit) && isrow(unit)) || ...
        (isstring(unit) && isscalar(unit));
    if ~isTextScalar || ~strcmpi(strtrim(char(unit)), 'mm')
        invalid_contract('mesh.unit must be mm when the field is present.');
    end
end
meshPoints = double(meshPoints);
volumePoints = double(volumePoints);
maxAbsPositionM = max(abs(volumePoints(:)));
if maxAbsPositionM >= 2
    invalid_contract( ...
        'vol.pos exceeds the canonical 2 m absolute coordinate bound (%.17g m).', ...
        maxAbsPositionM);
end
maxMismatchM = max(abs(meshPoints(:) / 1000 - volumePoints(:)));
if maxMismatchM > 1e-6
    invalid_contract( ...
        ['mesh.pnt / 1000 does not match vol.pos within 1e-6 m ', ...
         '(maximum mismatch %.17g m).'], maxMismatchM);
end
end

function value = coordinate_array(container, fieldName, displayName)
if ~isstruct(container) || ~isfield(container, fieldName)
    invalid_contract('%s is required.', displayName);
end
value = container.(fieldName);
if ~isnumeric(value) || ~isreal(value) || isempty(value) || ...
        ~ismatrix(value) || size(value, 2) ~= 3
    invalid_contract('%s must be a nonempty real numeric N x 3 array.', displayName);
end
if any(~isfinite(value(:)))
    invalid_contract('%s must contain only finite values.', displayName);
end
end

function invalid_contract(message, varargin)
error('mh_vta:InvalidCanonicalHeadmodelUnits', message, varargin{:});
end
```

- [ ] **Step 4: Verify GREEN**

Run the Step 2 command again. Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add my_helper/fiber/core/stimulation/model/mh_vta_validate_canonical_headmodel_units.m my_helper/fiber/tests/test_vta_headmodel_unit_contract.m
git commit -m "fix: validate canonical headmodel coordinate units"
```

### Task 2: Enforce The Guard In Preparation And Backend Execution

**Files:**
- Modify: `my_helper/fiber/tests/test_vta_headmodel_unit_contract.m`
- Modify: `my_helper/fiber/tests/test_vta_common_grid_export.m:302-313`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_prepare_canonical_headmodel.m:34-42`
- Modify: `my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve_canonical.m:26-29`

**Interfaces:**
- Consumes: the validator from Task 1.
- Produces: early `InvalidExistingHeadmodel` for invalid reused input and mandatory `mh_vta:InvalidCanonicalHeadmodelUnits` before backend boundary assembly.

- [ ] **Step 1: Add failing integration and call-order tests**

Add these functions to `test_vta_headmodel_unit_contract.m`:

```matlab
function testPrepareRejectsUnitMismatchWithoutOverwrite(testCase)
testRoot = tempname;
subjectDir = fullfile(testRoot, 'sub-SNr003');
headmodelDir = fullfile(subjectDir, 'headmodel', 'native');
mkdir(headmodelDir);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
[vol, mesh] = valid_fixture('double', true);
vol.pos = double(mesh.pnt);
centroids = [];
wmboundary = [];
elfv = [];
meshregions = [];
headmodelPath = fullfile(headmodelDir, 'sub-SNr003_desc-headmodel1.mat');
save(headmodelPath, 'vol', 'mesh', 'centroids', 'wmboundary', ...
    'elfv', 'meshregions', '-v7.3');
originalHash = mh_fiber_file_sha256(headmodelPath);
options = struct('native', 1, 'subj', struct( ...
    'subjDir', subjectDir, 'subjId', 'SNr003'));
verifyError(testCase, @() mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation'), ...
    'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel');
verifyEqual(testCase, mh_fiber_file_sha256(headmodelPath), originalHash);
end

function testCanonicalBackendGuardsUnitsImmediatelyAfterLoad(testCase)
source = fileread(which('mh_vta_backend_simbio_onesolve_canonical'));
loadPosition = strfind(source, 'hm = load(headmodelPath');
guardPosition = strfind(source, ...
    'mh_vta_validate_canonical_headmodel_units(hm.vol, hm.mesh);');
activeIndexPosition = strfind(source, 'activeidx = ea_getactiveidx');
verifyEqual(testCase, numel(loadPosition), 1);
verifyEqual(testCase, numel(guardPosition), 1);
verifyEqual(testCase, numel(activeIndexPosition), 1);
verifyGreaterThan(testCase, guardPosition, loadPosition);
verifyLessThan(testCase, guardPosition, activeIndexPosition);
end
```

Run the Task 1 focused command. Expected: both new tests FAIL because neither
production call site invokes the validator.

- [ ] **Step 2: Correct the existing Horn builder fixture**

Replace the body assembled by `write_headmodel_builder_stub` in
`test_vta_common_grid_export.m` with:

```matlab
text = ...
    "function diagnostics = mh_vta_run_horn_with_retry(varargin)" + newline + ...
    "expectedPath = varargin{5};" + newline + ...
    "mesh = struct('pnt',[0,0,0;10,-20,30;-40,50,-60],'unit','mm');" + newline + ...
    "vol = struct('pos',double(mesh.pnt)/1000);" + newline + ...
    "centroids = []; wmboundary = [];" + newline + ...
    "elfv = []; meshregions = [];" + newline + ...
    "save(expectedPath, 'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions', '-v7.3');" + newline + ...
    "diagnostics = struct('attempt_count', 1);" + newline + ...
    "end" + newline;
```

- [ ] **Step 3: Add early validation to reused-model preparation**

Replace the existing `load` try/catch in
`mh_vta_prepare_canonical_headmodel.m` with:

```matlab
    try
        stored = load(headmodelPath, required{:});
        mh_vta_validate_canonical_headmodel_units(stored.vol, stored.mesh);
    catch ME
        wrapped = MException( ...
            'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel', ...
            ['Existing canonical head model is unreadable or violates ', ...
             'the coordinate-unit contract: %s'], headmodelPath);
        wrapped = addCause(wrapped, ME);
        throw(wrapped);
    end
```

Do not add a second load after a new build.

- [ ] **Step 4: Add the mandatory backend guard**

Immediately after the backend's multi-line `hm = load(...)`, add:

```matlab
    mh_vta_validate_canonical_headmodel_units(hm.vol, hm.mesh);
```

Keep it before `ea_getactiveidx`, boundary assembly, FEM solving, and gradient
calculation.

- [ ] **Step 5: Run focused integration suites**

```bash
conda run -n leaddbs matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_headmodel_unit_contract.m'); r=[r testsuite('my_helper/fiber/tests/test_vta_common_grid_export.m')]; assertSuccess(run(r));"
```

Expected: all tests PASS, including build/reuse of the corrected fixture.

- [ ] **Step 6: Commit**

```bash
git add my_helper/fiber/core/stimulation/model/mh_vta_prepare_canonical_headmodel.m my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve_canonical.m my_helper/fiber/tests/test_vta_headmodel_unit_contract.m my_helper/fiber/tests/test_vta_common_grid_export.m
git commit -m "fix: enforce canonical headmodel unit guard"
```

### Task 3: Run Regression And Real-Artifact Verification

**Files:**
- Verify only; no source changes expected.

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: evidence that current VTA contracts remain green and the known valid SNr003 artifact satisfies the guard.

- [ ] **Step 1: Run relevant MATLAB regression suites**

```bash
conda run -n leaddbs matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); files={'test_vta_headmodel_unit_contract.m','test_vta_canonical_options_contract.m','test_vta_canonical_task_contract.m','test_vta_boundary_contract.m','test_vta_common_grid_export.m'}; r=matlab.unittest.Test.empty; for i=1:numel(files), r=[r testsuite(fullfile('my_helper','fiber','tests',files{i}))]; end; assertSuccess(run(r));"
```

Expected: all selected suites PASS.

- [ ] **Step 2: Validate the existing accepted SNr003 head model when present**

```bash
conda run -n leaddbs matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); p='/Volumes/VAL/STNSNr/validation/vta_pipeline_e2e_maskfix_20260713T172111Z/copied_dataset/derivatives/leaddbs/sub-SNr003/headmodel/native/sub-SNr003_desc-headmodel1.mat'; if isfile(p), hm=load(p,'vol','mesh'); mh_vta_validate_canonical_headmodel_units(hm.vol,hm.mesh); end"
```

Expected: exit code 0. The command is read-only.

- [ ] **Step 3: Run repository consistency checks**

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors and no uncommitted changes.
