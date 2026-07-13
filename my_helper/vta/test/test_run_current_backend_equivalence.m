function tests = test_run_current_backend_equivalence
% Validate deterministic current fixtures without running FEM.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.safeWorkRoot = fullfile(tempdir, ...
    'vta_current_acceptance_unit_tests');
end

function testGeneratedCurrentCasesAreDeterministic(testCase)
first = fixture_result(testCase, 20260712);
second = fixture_result(testCase, 20260712);

verifyEqual(testCase, first.cases, second.cases);
verifyEqual(testCase, first.fixture_sha256, second.fixture_sha256);
verifyEqual(testCase, first.seed, 20260712);
verifyEqual(testCase, first.atlas_set, ...
    'Custom_Ewert_Zhang_Middlebrooks');
end

function testGeneratedCasesCoverBothSidesAndReturnDesigns(testCase)
result = fixture_result(testCase, 20260712);
cases = result.cases;

verifyEqual(testCase, numel(cases), 6);
verifyEqual(testCase, unique(string({cases.hemisphere})), ["L" "R"]);
for side = ["L" "R"]
    sideCases = cases(string({cases.hemisphere}) == side);
    verifyEqual(testCase, string({sideCases.design}), ...
        ["single_cathode_case_return", ...
         "multi_cathode_case_return", ...
         "electrode_return"]);
end
verifyTrue(testCase, any([cases.has_case_return]));
verifyTrue(testCase, any([cases.has_electrode_return]));
end

function testGeneratedParametersAndFractionsSatisfyContract(testCase)
cases = fixture_result(testCase, 20260712).cases;

verifyGreaterThanOrEqual(testCase, [cases.amplitude_mA], 0.5);
verifyLessThanOrEqual(testCase, [cases.amplitude_mA], 5.0);
verifyGreaterThanOrEqual(testCase, [cases.pulse_width_us], 30);
verifyLessThanOrEqual(testCase, [cases.pulse_width_us], 120);
verifyEqual(testCase, string({cases.control_mode}), ...
    repmat("current", 1, numel(cases)));
verifyEqual(testCase, string({cases.unit}), repmat("mA", 1, numel(cases)));

for index = 1:numel(cases)
    contacts = cases(index).contacts;
    polarities = string({contacts.polarity});
    verifyEqual(testCase, sum([contacts(polarities == "cathode").fraction]), ...
        1, 'AbsTol', 1e-12);
    verifyEqual(testCase, sum([contacts(polarities == "anode").fraction]), ...
        1, 'AbsTol', 1e-12);
    verifyEqual(testCase, numel(unique(contact_keys(contacts))), numel(contacts));
end
end

function testDifferentSeedChangesFixture(testCase)
first = fixture_result(testCase, 20260712);
second = fixture_result(testCase, 20260713);

verifyNotEqual(testCase, first.fixture_sha256, second.fixture_sha256);
end

function testOfficialFemPlanUsesOneFixedRightCase(testCase)
result = fixture_result(testCase, 20260712);
plan = result.fem_plan;

verifyEqual(testCase, numel(plan.cases), 1);
verifyEqual(testCase, string(plan.cases.hemisphere), "R");
verifyEqual(testCase, string(plan.cases.design), ...
    "single_cathode_case_return");
verifyEqual(testCase, string(plan.backends), ["simbio" "canonical"]);
verifyEqual(testCase, string(plan.execution_paths), ...
    ["standard_simbio" "canonical_backend"]);
verifyEqual(testCase, plan.runs_per_backend, 1);
verifyEqual(testCase, plan.planned_fem_solve_count, 2);
end

function testWorkRootCannotBeProductionSubjectTree(testCase)
unsafeRoots = { ...
    '/Volumes/VAL/STNSNr/derivatives/leaddbs', ...
    '/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr003', ...
    '/Volumes/VAL/STNSNr/derivatives'};
for index = 1:numel(unsafeRoots)
    verifyError(testCase, @() run_current_backend_equivalence( ...
        'Mode', 'fixture_only', ...
        'WorkRoot', unsafeRoots{index}), ...
        'mh_vta_acceptance:UnsafeWorkRoot');
end
end

function testRerunCandidateModeIsRecognizedBeforeExistingRunValidation(testCase)
missingRun = fullfile(tempdir, 'missing-current-acceptance-run');
verifyError(testCase, @() run_current_backend_equivalence( ...
    'Mode', 'rerun_candidate', ...
    'ExistingRunRoot', missingRun, ...
    'WorkRoot', testCase.TestData.safeWorkRoot), ...
    'run_current_backend_equivalence:MissingFolder');
end

function testCompareExistingUsesNoFemAndRefreshesMetrics(testCase)
runRoot = tempname;
mkdir(runRoot);
cleanup = onCleanup(@() remove_test_root(runRoot));
trashRoot = fullfile(runRoot, 'test-trash');
caseId = 'R_single_cathode_case_return';
referenceDir = fullfile(runRoot, 'outputs', 'simbio', caseId);
candidateNativeDir = fullfile(runRoot, 'outputs', 'simbio_onesolve', ...
    caseId, 'native');
candidateMniDir = fullfile(runRoot, 'outputs', 'simbio_onesolve', ...
    caseId, 'MNI152NLin2009bAsym');
mkdir(referenceDir);
mkdir(candidateNativeDir);
mkdir(candidateMniDir);

referenceAffine = diag([2 2 2 1]);
candidateAffine = diag([1 1 1 1]);
referenceData = linear_world_field([10 10 10], referenceAffine);
candidateData = linear_world_field([20 20 20], candidateAffine);
write_nii_with_affine(fullfile(referenceDir, 'native_efield.nii'), ...
    referenceData, referenceAffine);
write_nii_with_affine(fullfile(referenceDir, 'mni_efield.nii'), ...
    referenceData, referenceAffine);
write_nii_with_affine(fullfile(candidateNativeDir, 'efield.nii.gz'), ...
    candidateData, candidateAffine);
write_nii_with_affine(fullfile(candidateMniDir, 'efield.nii.gz'), ...
    candidateData, candidateAffine);
write_candidate_thresholds(candidateMniDir, candidateData, candidateAffine);
write_json(fullfile(runRoot, 'validation_manifest.json'), struct( ...
    'subject_id', 'Synthetic', ...
    'hemisphere', 'R', ...
    'case_design', 'single_cathode_case_return', ...
    'planned_fem_solve_count', 2, ...
    'pass', false));
write_json(fullfile(runRoot, 'acceptance_summary.json'), struct( ...
    'production_subject_tree_unchanged', true, ...
    'pass', false));
staleFiles = { ...
    'efield_metrics.csv', ...
    'binary_vta_metrics.csv', ...
    'repeatability_metrics.csv', ...
    'mni_transform_metrics.csv'};
for index = 1:numel(staleFiles)
    write_text(fullfile(runRoot, staleFiles{index}), 'stale');
end

result = run_current_backend_equivalence( ...
    'Mode', 'compare_existing', ...
    'ExistingRunRoot', runRoot, ...
    'TrashRoot', trashRoot, ...
    'MniRepeatFunction', @copy_stored_mni_to_repeat, ...
    'WorkRoot', testCase.TestData.safeWorkRoot);

verifyEqual(testCase, string(result.mode), "compare_existing");
verifyEqual(testCase, result.fem_solve_count, 0);
verifyTrue(testCase, result.pass);
verifyTrue(testCase, isfile(fullfile(runRoot, 'efield_metrics.csv')));
verifyTrue(testCase, isfile(fullfile(runRoot, 'binary_vta_metrics.csv')));
summary = jsondecode(fileread(fullfile(runRoot, 'acceptance_summary.json')));
verifyEqual(testCase, summary.comparison_fem_solve_count, 0);
verifyTrue(testCase, summary.production_subject_tree_unchanged);
verifyTrue(testCase, summary.mni_transform_contract_passed);
verifyTrue(testCase, summary.pass);
trashed = dir(fullfile(trashRoot, '*'));
verifyEqual(testCase, nnz(~[trashed.isdir]), 5);
end

function testCompareExistingPreservesFailedProductionSafetyGate(testCase)
runRoot = tempname;
mkdir(runRoot);
cleanup = onCleanup(@() remove_test_root(runRoot));
trashRoot = fullfile(runRoot, 'test-trash');
write_existing_comparison_fixture(runRoot, false);

result = run_current_backend_equivalence( ...
    'Mode', 'compare_existing', ...
    'ExistingRunRoot', runRoot, ...
    'TrashRoot', trashRoot, ...
    'MniRepeatFunction', @copy_stored_mni_to_repeat, ...
    'WorkRoot', testCase.TestData.safeWorkRoot);

verifyFalse(testCase, result.pass);
verifyFalse(testCase, result.summary.production_subject_tree_unchanged);
verifyTrue(testCase, result.summary.comparison_gates_passed);
end

function testSignedVectorSuperpositionRejectsScalarAlternatives(testCase)
evidence = fixture_result(testCase, 20260712).superposition_fixture;

verifyTrue(testCase, evidence.signed_linear_superposition_passed);
verifyTrue(testCase, evidence.scalar_max_rejected);
verifyTrue(testCase, evidence.scalar_sum_rejected);
verifyEqual(testCase, evidence.combined_vector, ...
    sum(evidence.signed_source_vectors, 1), 'AbsTol', 1e-12);
verifyEqual(testCase, evidence.combined_magnitude, ...
    norm(evidence.combined_vector), 'AbsTol', 1e-12);
verifyNotEqual(testCase, evidence.combined_magnitude, ...
    evidence.scalar_max_magnitude);
verifyNotEqual(testCase, evidence.combined_magnitude, ...
    evidence.scalar_sum_magnitude);
end

function result = fixture_result(testCase, seed)
result = run_current_backend_equivalence( ...
    'Mode', 'fixture_only', ...
    'WorkRoot', testCase.TestData.safeWorkRoot, ...
    'Seed', seed);
end

function keys = contact_keys(contacts)
keys = strings(1, numel(contacts));
for index = 1:numel(contacts)
    if isnumeric(contacts(index).contact)
        keys(index) = "contact:" + string(contacts(index).contact);
    else
        keys(index) = lower(string(contacts(index).contact));
    end
end
end

function data = linear_world_field(dimensions, affine)
[x, y, z] = ndgrid(1:dimensions(1), 1:dimensions(2), 1:dimensions(3));
coordinates = [x(:), y(:), z(:), ones(numel(x), 1)] * affine';
values = 160 + 2 * coordinates(:, 1) + coordinates(:, 2) + ...
    0.5 * coordinates(:, 3);
data = reshape(values, dimensions);
end

function write_nii_with_affine(path, data, affine)
temporary = [tempname, '.nii'];
niftiwrite(single(data), temporary, 'Compressed', false);
nii = ea_load_nii(temporary);
nii.fname = path;
nii.img = single(data);
nii.mat = affine;
ea_write_nii(nii);
delete(temporary);
end

function write_json(path, value)
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create JSON fixture.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(value, PrettyPrint=true));
end

function write_text(path, value)
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create text fixture.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', value);
end

function write_existing_comparison_fixture(runRoot, productionUnchanged)
caseId = 'R_single_cathode_case_return';
referenceDir = fullfile(runRoot, 'outputs', 'simbio', caseId);
candidateNativeDir = fullfile(runRoot, 'outputs', 'simbio_onesolve', ...
    caseId, 'native');
candidateMniDir = fullfile(runRoot, 'outputs', 'simbio_onesolve', ...
    caseId, 'MNI152NLin2009bAsym');
mkdir(referenceDir);
mkdir(candidateNativeDir);
mkdir(candidateMniDir);
referenceAffine = diag([2 2 2 1]);
candidateAffine = eye(4);
referenceData = linear_world_field([10 10 10], referenceAffine);
candidateData = linear_world_field([20 20 20], candidateAffine);
write_nii_with_affine(fullfile(referenceDir, 'native_efield.nii'), ...
    referenceData, referenceAffine);
write_nii_with_affine(fullfile(referenceDir, 'mni_efield.nii'), ...
    referenceData, referenceAffine);
write_nii_with_affine(fullfile(candidateNativeDir, 'efield.nii.gz'), ...
    candidateData, candidateAffine);
write_nii_with_affine(fullfile(candidateMniDir, 'efield.nii.gz'), ...
    candidateData, candidateAffine);
write_candidate_thresholds(candidateMniDir, candidateData, candidateAffine);
write_json(fullfile(runRoot, 'validation_manifest.json'), struct( ...
    'subject_id', 'Synthetic', ...
    'hemisphere', 'R', ...
    'case_design', 'single_cathode_case_return', ...
    'planned_fem_solve_count', 2, ...
    'pass', false));
write_json(fullfile(runRoot, 'acceptance_summary.json'), struct( ...
    'production_subject_tree_unchanged', productionUnchanged, ...
    'pass', false));
end

function write_candidate_thresholds(candidateMniDir, data, affine)
thresholds = [180, 200, 220];
for threshold = thresholds
    token = strrep(sprintf('%.2f', threshold / 1000), '.', 'p');
    path = fullfile(candidateMniDir, ...
        ['vta_threshold-', token, 'Vpermm.nii.gz']);
    write_nii_with_affine(path, uint8(data >= threshold), affine);
end
end

function copy_stored_mni_to_repeat(~, storedPath, repeatPath, varargin) %#ok<INUSD>
parent = fileparts(repeatPath);
if ~isfolder(parent)
    mkdir(parent);
end
[copied, message] = copyfile(storedPath, repeatPath);
assert(copied, 'Could not create repeated MNI fixture: %s', message);
end

function remove_test_root(path)
if isfolder(path)
    rmdir(path, 's');
end
end
