function tests = test_vta_canonical_task_contract
% Contract tests for canonical Python-to-MATLAB VTA task payloads.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
addpath(repoDir);
testCase.TestData.repoDir = repoDir;
end

function testContinuousSourcesRemainJoint(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    [fixture_source('source-1', 'voltage'), ...
     fixture_source('source-2', 'voltage')]);

resolved = mh_vta_validate_canonical_task(task);

verifyEqual(testCase, numel(resolved.solve_units), 1);
verifyEqual(testCase, ...
    string({resolved.solve_units{1}.source_id}), ...
    ["source-1", "source-2"]);
end

function testAlternatingSourceRemainsIndependent(testCase)
task = fixture_task('alternating_source', 'alternating', ...
    fixture_source('source-1', 'current'));

resolved = mh_vta_validate_canonical_task(task);

verifyEqual(testCase, numel(resolved.solve_units), 1);
verifyEqual(testCase, string(resolved.solve_units{1}.source_id), "source-1");
end

function testAlternatingGroupPeakIsDerivedWithoutSolveUnits(testCase)
task = fixture_task('alternating_group_peak', 'alternating', ...
    [fixture_source('source-1', 'voltage'), ...
     fixture_source('source-2', 'voltage')]);

resolved = mh_vta_validate_canonical_task(task);

verifyEmpty(testCase, resolved.solve_units);
end

function testMixedControlModesAreRejected(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    [fixture_source('source-1', 'voltage'), ...
     fixture_source('source-2', 'current')]);

verifyError(testCase, @() mh_vta_validate_canonical_task(task), ...
    'mh_vta:MixedControlMode');
end

function testTaskKindMustMatchDeliveryMode(testCase)
task = fixture_task('continuous_joint', 'alternating', ...
    fixture_source('source-1', 'voltage'));

verifyError(testCase, @() mh_vta_validate_canonical_task(task), ...
    'mh_vta:TaskKindDeliveryMismatch');
end

function testRuntimeContextFieldsAreRequired(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
task = rmfield(task, 'run_id');

verifyError(testCase, @() mh_vta_validate_canonical_task(task), ...
    'mh_vta:InvalidCanonicalTask');
end

function testMissingArtifactsAreRequired(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
task = rmfield(task, 'missing_artifacts');

verifyError(testCase, @() mh_vta_validate_canonical_task(task), ...
    'mh_vta:InvalidCanonicalTask');
end

function testUnknownMissingArtifactIsRejected(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
task.missing_artifacts.native = {'unexpected.nii.gz'};

verifyError(testCase, @() mh_vta_validate_canonical_task(task), ...
    'mh_vta:InvalidCanonicalTask');
end

function testThresholdOnlyRequestDoesNotRequireFemOrTransform(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
task.missing_artifacts = struct( ...
    'native', {{'vta_threshold-0p20Vpermm.nii.gz'}});
task = mh_vta_validate_canonical_task(task);

actions = mh_vta_resolve_output_actions(task);

verifyFalse(testCase, actions.solve_native_efield);
verifyFalse(testCase, actions.transform_mni_efield);
verifyEqual(testCase, actions.native_threshold_names, ...
    "vta_threshold-0p20Vpermm.nii.gz");
verifyEmpty(testCase, actions.mni_threshold_names);
end

function testMniEfieldOnlyRequestTransformsWithoutFem(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
task.missing_artifacts = struct( ...
    'MNI152NLin2009bAsym', {{'efield.nii.gz'}});
task = mh_vta_validate_canonical_task(task);

actions = mh_vta_resolve_output_actions(task);

verifyFalse(testCase, actions.solve_native_efield);
verifyTrue(testCase, actions.transform_mni_efield);
end

function testRunnerReadsCanonicalJson(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
taskPath = [tempname '.json'];
cleanup = onCleanup(@() delete_if_present(taskPath));
fid = fopen(taskPath, 'w');
assert(fid >= 0, 'Could not create canonical task fixture.');
fileCleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(task), 'char');
clear fileCleanup;

resolved = mh_vta_run_canonical_task(taskPath, ...
    'SolveFunction', @identity_task);

verifyEqual(testCase, string(resolved.task_id), "task-001");
verifyEqual(testCase, string(resolved.kind), "continuous_joint");
verifyEqual(testCase, numel(resolved.solve_units), 1);
end

function status = identity_task(task)
status = task;
end

function testRunnerDispatchesSolveTask(testCase)
task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
taskPath = write_task_fixture(task);
cleanup = onCleanup(@() delete_if_present(taskPath));

status = mh_vta_run_canonical_task(taskPath, ...
    'SolveFunction', @record_solve, ...
    'DerivedFunction', @reject_unexpected_dispatch);

verifyEqual(testCase, string(status.execution), "solve");
verifyEqual(testCase, string(status.task_id), "task-001");
end

function testRunnerDispatchesDerivedTaskWithoutFem(testCase)
task = fixture_task('alternating_group_peak', 'alternating', ...
    [fixture_source('source-1', 'voltage'), ...
     fixture_source('source-2', 'voltage')]);
taskPath = write_task_fixture(task);
cleanup = onCleanup(@() delete_if_present(taskPath));

status = mh_vta_run_canonical_task(taskPath, ...
    'SolveFunction', @reject_unexpected_dispatch, ...
    'DerivedFunction', @record_derived);

verifyEqual(testCase, string(status.execution), "derived");
verifyEqual(testCase, string(status.task_id), "task-001");
end

function testDefaultSolveDispatchesDirectlyToCanonicalBackend(testCase)
stubDir = tempname;
mkdir(stubDir);
cleanup = onCleanup(@() cleanup_backend_stubs(stubDir));
write_backend_stub(stubDir, ...
    'mh_vta_backend_simbio_onesolve_canonical', ...
    "status = struct('execution','canonical','task_id',task.task_id);");
write_backend_stub(stubDir, 'mh_vta_backend_simbio_onesolve', ...
    "error('test_vta:LegacyBackendCalled','Legacy backend was called.');");
addpath(stubDir, '-begin');
clear mh_vta_backend_simbio_onesolve_canonical ...
    mh_vta_backend_simbio_onesolve mh_vta_execute_canonical_task;
rehash;

task = fixture_task('continuous_joint', 'continuous', ...
    fixture_source('source-1', 'voltage'));
status = mh_vta_execute_canonical_task(task);

verifyEqual(testCase, string(status.execution), "canonical");
verifyEqual(testCase, string(status.task_id), "task-001");
end

function task = fixture_task(kind, deliveryMode, sources)
task = struct( ...
    'task_id', 'task-001', ...
    'kind', kind, ...
    'subject_id', 'SNr003', ...
    'subject_dir', '/tmp/sub-SNr003', ...
    'reconstruction_path', '/tmp/sub-SNr003/reconstruction.mat', ...
    'phase_id', 'T1', ...
    'program_id', 1, ...
    'electrode_id', 'lead-R', ...
    'hemisphere', 'R', ...
    'electrode_model', 'Medtronic 3387', ...
    'reconstruction_lead_id', 1, ...
    'frequency_group_id', 'group-1', ...
    'delivery_mode', deliveryMode, ...
    'sources', sources, ...
    'dependencies', {{}}, ...
    'model', fixture_model(), ...
    'run_id', '20260713T120000Z', ...
    'output_leaves', struct( ...
        'native', '/tmp/native-leaf', ...
        'MNI152NLin2009bAsym', '/tmp/mni-leaf'), ...
    'missing_artifacts', struct( ...
        'native', {{'efield.nii.gz', ...
            'vta_threshold-0p18Vpermm.nii.gz', ...
            'vta_threshold-0p20Vpermm.nii.gz', ...
            'vta_threshold-0p22Vpermm.nii.gz'}}, ...
        'MNI152NLin2009bAsym', {{'efield.nii.gz', ...
            'vta_threshold-0p18Vpermm.nii.gz', ...
            'vta_threshold-0p20Vpermm.nii.gz', ...
            'vta_threshold-0p22Vpermm.nii.gz'}}));
end

function source = fixture_source(sourceId, controlMode)
source = struct( ...
    'source_id', sourceId, ...
    'frequency_hz', 130, ...
    'control_mode', controlMode, ...
    'amplitude', 2.0, ...
    'pulse_width_us', 60, ...
    'contacts', [ ...
        struct('contact', 1, 'polarity', 'cathode', 'fraction', 1.0), ...
        struct('contact', 'case', 'polarity', 'anode', 'fraction', 1.0)]);
end

function path = write_task_fixture(task)
path = [tempname '.json'];
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create canonical task fixture.');
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(task), 'char');
end

function status = record_solve(task)
status = struct('execution', 'solve', 'task_id', task.task_id);
end

function status = record_derived(task)
status = struct('execution', 'derived', 'task_id', task.task_id);
end

function status = reject_unexpected_dispatch(~)
error('test_vta:UnexpectedDispatch', 'Unexpected execution path.');
status = struct(); %#ok<UNRCH>
end

function model = fixture_model()
model = struct( ...
    'gray_matter_s_per_m', 0.33, ...
    'white_matter_s_per_m', 0.14, ...
    'atlas_set', 'Custom_Ewert_Zhang_Middlebrooks', ...
    'spaces', {{'native', 'MNI152NLin2009bAsym'}}, ...
    'thresholds_v_per_m', [180, 200, 220]);
end

function delete_if_present(path)
if isfile(path)
    delete(path);
end
end

function write_backend_stub(stubDir, functionName, body)
path = fullfile(stubDir, [functionName, '.m']);
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create backend stub.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, 'function status = %s(task)\n%s\nend\n', ...
    functionName, char(body));
end

function cleanup_backend_stubs(stubDir)
if isfolder(stubDir)
    rmpath(stubDir);
    rmdir(stubDir, 's');
end
clear mh_vta_backend_simbio_onesolve_canonical ...
    mh_vta_backend_simbio_onesolve mh_vta_execute_canonical_task;
rehash;
end
