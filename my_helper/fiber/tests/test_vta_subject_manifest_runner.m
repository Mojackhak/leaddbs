function tests = test_vta_subject_manifest_runner
% Solver-free tests for persistent subject-manifest execution.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
addpath(repoDir);
testCase.TestData.repoDir = repoDir;
end

function testMultipleTasksExecuteInManifestOrder(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("result = mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @publish_all);");
events = parse_events(output);

verifyEqual(testCase, cellfun(@(event) event.sequence, events), ...
    1:numel(events));
verifyEqual(testCase, event_types(events), [ ...
    "stage_timing", "stage_timing", "subject_ready", ...
    "task_started", "stage_timing", "task_outcome", ...
    "task_started", "stage_timing", "task_outcome", ...
    "subject_summary"]);
verifyEqual(testCase, string({events{1}.stage, events{2}.stage}), ...
    ["path_initialization", "manifest_decode_validation"]);
verifyEqual(testCase, outcome_task_ids(events), ["task-1", "task-2"]);
verifyEqual(testCase, outcome_statuses(events), ["generated", "generated"]);
verifyEqual(testCase, result.summary.generated, 2);
verifyTrue(testCase, result.summary.process_success);
end

function testCompleteAndCopiedTasksAvoidDispatch(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
write_all_artifacts(runtime_task(manifest, 1), 'existing');
donor = donor_for_task(manifest.tasks(2).task, 'copy-donor', 'copy-source');
manifest.reuse_donors(end + 1) = donor;
manifest.tasks(2).reuse_candidate_ids = {'copy-donor'};
write_all_donor_artifacts(donor, ...
    manifest.tasks(2).task.model.thresholds_v_per_m, 'copied');
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("result = mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @reject_dispatch);");
events = parse_events(output);

verifyEqual(testCase, outcome_statuses(events), ...
    ["skipped_existing", "copied"]);
verifyEqual(testCase, outcome_copied_counts(events), [0, 8]);
verifyEqual(testCase, result.summary.skipped_existing, 1);
verifyEqual(testCase, result.summary.copied, 1);
end

function testPartialCopyDispatchesOnlyMissingArtifacts(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
donor = donor_for_task(manifest.tasks(1).task, ...
    'partial-donor', 'partial-source');
manifest.reuse_donors(end + 1) = donor;
manifest.tasks(1).reuse_candidate_ids = {'partial-donor'};
write_text(fullfile(donor.output_leaves.native, 'efield.nii.gz'), 'copied');
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @publish_all);");
events = parse_events(output);
outcome = task_outcomes(events);

verifyEqual(testCase, string(outcome{1}.status), "generated");
verifyEqual(testCase, outcome{1}.copied_artifact_count, 1);
verifyEqual(testCase, outcome{1}.generated_artifact_count, 7);
end

function testFailedTaskDoesNotStopIndependentTask(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("result = mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @fail_first_publish_later);");
events = parse_events(output);

verifyEqual(testCase, outcome_statuses(events), ["failed", "generated"]);
verifyEqual(testCase, result.summary.failed, 1);
verifyEqual(testCase, result.summary.generated, 1);
verifyFalse(testCase, result.summary.process_success);
end

function testGroupPeakSkipsMissingArtifactDependency(testCase)
[manifest, cleanup] = fixture_group_peak_manifest(); %#ok<ASGLU>
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("result = mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @always_fail, " + ...
    "'DerivedFunction', @reject_dispatch);");
events = parse_events(output);

verifyEqual(testCase, outcome_statuses(events), ...
    ["failed", "skipped_dependency"]);
verifyEqual(testCase, result.summary.skipped_dependency, 1);
verifyFalse(testCase, result.summary.process_success);
end

function testCaughtExceptionIsFailedAfterPublication(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("result = mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @publish_then_fail_second);");
events = parse_events(output);
outcomes = task_outcomes(events);

verifyEqual(testCase, outcome_statuses(events), ...
    ["generated", "failed"]);
verifyEqual(testCase, string(outcomes{2}.error_identifier), ...
    "test_vta:PostPublishFailure");
verifyEqual(testCase, result.summary.generated, 1);
verifyEqual(testCase, result.summary.failed, 1);
verifyEqual(testCase, result.summary.recovered_complete, 0);
verifyFalse(testCase, result.summary.process_success);
end

function testReturnedIncompleteTaskIsFailed(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifestPath = write_manifest(manifest);
pathCleanup = onCleanup(@() delete_if_present(manifestPath));
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

output = evalc("mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot, " + ...
    "'SolveFunction', @return_without_artifacts);");
outcomes = task_outcomes(parse_events(output));

verifyEqual(testCase, string(outcomes{1}.status), "failed");
verifyEqual(testCase, string(outcomes{1}.error_identifier), ...
    "mh_vta:IncompleteTaskArtifacts");
end

function testMalformedManifestIsFatalBeforeEvents(testCase)
manifestPath = [tempname, '.json'];
cleanup = onCleanup(@() delete_if_present(manifestPath));
write_text(manifestPath, '{invalid json');
repoRoot = testCase.TestData.repoDir; %#ok<NASGU>

caughtError = [];
output = evalc("try, mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot); " + ...
    "catch caughtError, end");

verifyEqual(testCase, string(caughtError.identifier), ...
    "mh_vta:InvalidSubjectManifestJson");
verifyEmpty(testCase, parse_events(output));

write_text(manifestPath, jsonencode(struct('schema_version', 'invalid')));
caughtError = [];
output = evalc("try, mh_vta_run_canonical_subject_manifest(" + ...
    "manifestPath, repoRoot); " + ...
    "catch caughtError, end");
verifyEqual(testCase, string(caughtError.identifier), ...
    "mh_vta:InvalidSubjectManifest");
verifyEmpty(testCase, parse_events(output));
end

function status = publish_all(task)
write_all_artifacts(task, task.task_id);
status = struct('task_id', task.task_id);
end

function status = fail_first_publish_later(task)
if strcmp(task.task_id, 'task-1')
    error('test_vta:ExpectedFailure', 'Expected first-task failure.');
end
status = publish_all(task);
end

function status = publish_then_fail_second(task)
status = publish_all(task);
if strcmp(task.task_id, 'task-2')
    error('test_vta:PostPublishFailure', ...
        'Expected failure after artifact publication.');
end
end

function status = always_fail(~) %#ok<STOUT>
error('test_vta:ExpectedFailure', 'Expected solve failure.');
end

function status = return_without_artifacts(task)
status = struct('task_id', task.task_id);
end

function status = reject_dispatch(~) %#ok<STOUT>
error('test_vta:UnexpectedDispatch', 'Task should not have been dispatched.');
end

function [manifest, cleanup] = fixture_manifest(taskCount)
root = tempname;
subjectDir = fullfile(root, 'sub-S001');
mkdir(subjectDir);
cleanup = onCleanup(@() remove_tree(root));
tasks = repmat(struct('task', struct(), 'output_leaves', struct(), ...
    'reuse_candidate_ids', {{}}), taskCount, 1);
donors = repmat(struct('donor_id', '', 'output_leaves', struct()), ...
    taskCount, 1);
for taskIndex = 1:taskCount
    task = fixture_task(subjectDir, sprintf('task-%d', taskIndex), ...
        sprintf('phase-%d', taskIndex), 'continuous_joint', {});
    tasks(taskIndex) = manifest_entry(task);
    donors(taskIndex) = donor_entry(task);
end
manifest = struct('schema_version', 'vta_subject_manifest_v1', ...
    'run_id', 'run-001', 'subject_id', 'S001', ...
    'tasks', tasks, 'reuse_donors', donors);
end

function [manifest, cleanup] = fixture_group_peak_manifest()
[manifest, cleanup] = fixture_manifest(2);
subjectDir = manifest.tasks(1).task.subject_dir;
source = fixture_task(subjectDir, 'source-task', 'group-phase', ...
    'alternating_source', {});
peak = fixture_task(subjectDir, 'peak-task', 'group-phase', ...
    'alternating_group_peak', {'source-task'});
manifest.tasks(1) = manifest_entry(source);
manifest.tasks(2) = manifest_entry(peak);
manifest.reuse_donors(1) = donor_entry(source);
manifest.reuse_donors(2) = donor_entry(peak);
end

function entry = manifest_entry(task)
leaves = task.output_leaves;
entry = struct('task', rmfield(task, {'run_id', 'output_leaves'}), ...
    'output_leaves', leaves, 'reuse_candidate_ids', {{}});
end

function donor = donor_entry(task)
donor = struct('donor_id', task.task_id, ...
    'output_leaves', task.output_leaves);
end

function task = fixture_task(subjectDir, taskId, phaseId, kind, dependencies)
deliveryMode = 'continuous';
if startsWith(kind, 'alternating_')
    deliveryMode = 'alternating';
end
task = struct( ...
    'task_id', taskId, ...
    'kind', kind, ...
    'subject_id', 'S001', ...
    'subject_dir', subjectDir, ...
    'reconstruction_path', fullfile(subjectDir, 'reconstruction.mat'), ...
    'phase_id', phaseId, ...
    'program_id', 1, ...
    'electrode_id', 'lead-R', ...
    'hemisphere', 'R', ...
    'electrode_model', 'Fixture electrode', ...
    'reconstruction_lead_id', 1, ...
    'frequency_group_id', 'group-1', ...
    'delivery_mode', deliveryMode, ...
    'sources', fixture_sources(), ...
    'dependencies', {dependencies}, ...
    'model', fixture_model(), ...
    'run_id', 'run-001');
task.output_leaves = struct( ...
    'native', mh_vta_canonical_leaf_path(task, 'native'), ...
    'MNI152NLin2009bAsym', ...
        mh_vta_canonical_leaf_path(task, 'MNI152NLin2009bAsym'));
end

function sources = fixture_sources()
sources = struct( ...
    'source_id', 'source-1', ...
    'frequency_hz', 130, ...
    'control_mode', 'voltage', ...
    'amplitude', 2.0, ...
    'pulse_width_us', 60, ...
    'contacts', [ ...
        struct('contact', 1, 'polarity', 'cathode', 'fraction', 1.0), ...
        struct('contact', 'case', 'polarity', 'anode', 'fraction', 1.0)]);
end

function model = fixture_model()
model = struct( ...
    'gray_matter_s_per_m', 0.33, ...
    'white_matter_s_per_m', 0.14, ...
    'atlas_set', 'Fixture atlas', ...
    'spaces', {{'native', 'MNI152NLin2009bAsym'}}, ...
    'thresholds_v_per_m', [180, 200, 220]);
end

function donor = donor_for_task(task, donorId, leafToken)
donor = struct('donor_id', donorId, 'output_leaves', struct());
spaces = cellstr(string(task.model.spaces));
for spaceIndex = 1:numel(spaces)
    donor.output_leaves.(spaces{spaceIndex}) = fullfile( ...
        task.subject_dir, 'stimulations', 'reuse', leafToken, ...
        spaces{spaceIndex});
end
end

function task = runtime_task(manifest, taskIndex)
task = manifest.tasks(taskIndex).task;
task.run_id = manifest.run_id;
task.output_leaves = manifest.tasks(taskIndex).output_leaves;
end

function write_all_artifacts(task, content)
spaces = cellstr(string(task.model.spaces));
names = mh_vta_expected_artifact_names(task.model.thresholds_v_per_m);
for spaceIndex = 1:numel(spaces)
    for nameIndex = 1:numel(names)
        write_text(fullfile(task.output_leaves.(spaces{spaceIndex}), ...
            char(names(nameIndex))), content);
    end
end
end

function write_all_donor_artifacts(donor, thresholds, content)
spaces = fieldnames(donor.output_leaves);
names = mh_vta_expected_artifact_names(thresholds);
for spaceIndex = 1:numel(spaces)
    for nameIndex = 1:numel(names)
        write_text(fullfile(donor.output_leaves.(spaces{spaceIndex}), ...
            char(names(nameIndex))), content);
    end
end
end

function path = write_manifest(manifest)
path = [tempname, '.json'];
write_text(path, jsonencode(manifest));
end

function write_text(path, content)
folder = fileparts(path);
if ~isfolder(folder)
    mkdir(folder);
end
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create subject-runner fixture.');
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, content, 'char');
end

function events = parse_events(output)
prefix = 'MH_VTA_EVENT ';
lines = splitlines(string(output));
lines = lines(startsWith(lines, prefix));
events = cell(1, numel(lines));
for lineIndex = 1:numel(lines)
    events{lineIndex} = jsondecode(extractAfter( ...
        lines(lineIndex), strlength(prefix)));
end
end

function types = event_types(events)
types = string(cellfun(@(event) event.event_type, ...
    events, 'UniformOutput', false));
end

function outcomes = task_outcomes(events)
types = event_types(events);
outcomes = events(types == "task_outcome");
end

function statuses = outcome_statuses(events)
outcomes = task_outcomes(events);
statuses = string(cellfun(@(event) event.status, ...
    outcomes, 'UniformOutput', false));
end

function taskIds = outcome_task_ids(events)
outcomes = task_outcomes(events);
taskIds = string(cellfun(@(event) event.task_id, ...
    outcomes, 'UniformOutput', false));
end

function counts = outcome_copied_counts(events)
outcomes = task_outcomes(events);
counts = cellfun(@(event) event.copied_artifact_count, outcomes);
end

function delete_if_present(path)
if isfile(path)
    delete(path);
end
end

function remove_tree(path)
if isfolder(path)
    rmdir(path, 's');
end
end
