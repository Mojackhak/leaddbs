function tests = test_run_single_current_backend_equivalence
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

function testWorkRootCannotBeProductionSubjectTree(testCase)
unsafeRoots = { ...
    '/Volumes/VAL/STNSNr/derivatives/leaddbs', ...
    '/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr003', ...
    '/Volumes/VAL/STNSNr/derivatives'};
for index = 1:numel(unsafeRoots)
    verifyError(testCase, @() run_single_current_backend_equivalence( ...
        'Mode', 'fixture_only', ...
        'WorkRoot', unsafeRoots{index}), ...
        'mh_vta_acceptance:UnsafeWorkRoot');
end
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
result = run_single_current_backend_equivalence( ...
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
