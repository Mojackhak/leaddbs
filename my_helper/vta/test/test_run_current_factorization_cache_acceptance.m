function tests = test_run_current_factorization_cache_acceptance
% Verify the bounded current factorization-cache acceptance declaration.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.workRoot = tempdir;
end

function testFixtureDeclaresExactlyTwoFemSolves(testCase)
result = run_current_factorization_cache_acceptance( ...
    'Mode', 'fixture_only', 'WorkRoot', testCase.TestData.workRoot);

verifyTrue(testCase, result.pass);
verifyEqual(testCase, result.planned_fem_solve_count, 2);
verifyEqual(testCase, string(result.case.control_mode), "current");
verifyEqual(testCase, string(result.case.hemisphere), "R");
verifyEqual(testCase, string(result.case.design), ...
    "single_cathode_case_return");
verifyEqual(testCase, string(result.expected_matrix_cache_status), ...
    ["miss" "hit"]);
verifyEqual(testCase, string(result.expected_preconditioner_cache_status), ...
    ["miss" "hit"]);
end

function testInvalidModeIsRejected(testCase)
verifyError(testCase, @() run_current_factorization_cache_acceptance( ...
    'Mode', 'invalid', 'WorkRoot', testCase.TestData.workRoot), ...
    'run_current_factorization_cache_acceptance:InvalidMode');
end
