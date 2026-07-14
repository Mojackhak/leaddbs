function tests = test_vta_canonical_subject_manifest
% Solver-free tests for subject manifests and runtime artifact resolution.

tests = functiontests(localfunctions);
end

function testValidManifestNormalizesTasksAndLeaves(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
decoded = jsondecode(jsonencode(manifest));
validated = mh_vta_validate_subject_manifest(decoded);

verifyEqual(testCase, string(validated.schema_version), ...
    "vta_subject_manifest_v1");
verifyEqual(testCase, numel(validated.tasks), 2);
verifyTrue(testCase, isfield(validated.tasks(1).task, 'run_id'));
verifyFalse(testCase, isfield(validated.tasks(1).task, 'missing_artifacts'));
verifyEqual(testCase, string(validated.tasks(1).task.output_leaves.native), ...
    string(canonical_path(validated.tasks(1).task.output_leaves.native)));
end

function testManifestRejectsIdentityTopologyAndSubjectErrors(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifest.tasks(2).task.task_id = manifest.tasks(1).task.task_id;
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifest.tasks(1).task.dependencies = {manifest.tasks(2).task.task_id};
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.tasks(1).task.dependencies = {'unknown-task'};
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.tasks(1).task.subject_id = 'different-subject';
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.tasks(1).task.task_id = 123;
verify_manifest_error(testCase, manifest);
end

function testManifestRejectsMalformedEnvelopeAndDuplicateDonor(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.schema_version = 'unsupported';
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.tasks = 'not-a-task-array';
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.reuse_donors(2) = manifest.reuse_donors(1);
verify_manifest_error(testCase, manifest);
end

function testManifestRejectsPathDonorAndCandidateErrors(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifest.tasks(1).output_leaves.native = fullfile(tempdir, 'wrong-leaf');
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifest.tasks(2).task.phase_id = manifest.tasks(1).task.phase_id;
manifest.tasks(2).task.task_id = 'task-duplicate-leaf';
manifest.tasks(2).output_leaves = manifest.tasks(1).output_leaves;
manifest.reuse_donors(2).donor_id = 'task-duplicate-leaf';
manifest.reuse_donors(2).output_leaves = manifest.tasks(1).output_leaves;
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.reuse_donors(1).output_leaves.native = ...
    fullfile(tempdir, 'outside-subject');
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.tasks(1).reuse_candidate_ids = {'unknown-donor'};
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest.tasks(1).reuse_candidate_ids = {manifest.tasks(1).task.task_id};
verify_manifest_error(testCase, manifest);

[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
candidateId = manifest.reuse_donors(2).donor_id;
manifest.tasks(1).reuse_candidate_ids = {candidateId, candidateId};
verify_manifest_error(testCase, manifest);
end

function testManifestRejectsAncestorDescendantWritableLeaves(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
parent = manifest.tasks(1).task;
child = manifest.tasks(2).task;
child.phase_id = parent.phase_id;
child.frequency_group_id = ...
    [parent.frequency_group_id, '/delivery-continuous/joint/child'];
child.task_id = 'descendant-task';
childWithRuntime = child;
childWithRuntime.run_id = manifest.run_id;
childWithRuntime.output_leaves = struct( ...
    'native', mh_vta_canonical_leaf_path(childWithRuntime, 'native'), ...
    'MNI152NLin2009bAsym', ...
        mh_vta_canonical_leaf_path(childWithRuntime, 'MNI152NLin2009bAsym'));
manifest.tasks(2).task = child;
manifest.tasks(2).output_leaves = childWithRuntime.output_leaves;
manifest.reuse_donors(2).donor_id = child.task_id;
manifest.reuse_donors(2).output_leaves = childWithRuntime.output_leaves;

verify_manifest_error(testCase, manifest);
end

function testManifestRejectsSharedHeadmodelContextConflict(testCase)
[manifest, cleanup] = fixture_manifest(2); %#ok<ASGLU>
manifest.tasks(2).task.electrode_model = 'Different electrode';
verify_manifest_error(testCase, manifest);
end

function testCompleteTaskSkipsExistingArtifacts(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest = mh_vta_validate_subject_manifest(manifest);
write_all_artifacts(manifest.tasks(1).task, 'complete');

resolution = mh_vta_resolve_manifest_task(manifest, 1);

verifyEqual(testCase, string(resolution.status), "skipped_existing");
verifyEqual(testCase, resolution.copied_artifact_count, 0);
verifyEqual(testCase, resolution.missing_artifact_count, 0);
end

function testOrderedDonorCopyCompletesTask(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
task = manifest.tasks(1).task;
missingDonor = donor_for_task(task, 'missing-donor', 'donor-missing');
completeDonor = donor_for_task(task, 'complete-donor', 'donor-complete');
manifest.reuse_donors = [manifest.reuse_donors, missingDonor, completeDonor];
manifest.tasks(1).reuse_candidate_ids = ...
    {'missing-donor', 'complete-donor'};
write_all_donor_artifacts(completeDonor, task.model.thresholds_v_per_m, ...
    'copied');
manifest = mh_vta_validate_subject_manifest(manifest);
task = manifest.tasks(1).task;

resolution = mh_vta_resolve_manifest_task(manifest, 1);

verifyEqual(testCase, string(resolution.status), "copied");
verifyEqual(testCase, resolution.copied_artifact_count, 8);
verifyEqual(testCase, read_text(fullfile( ...
    task.output_leaves.native, 'efield.nii.gz')), "copied");
end

function testPartialCopyReturnsReadyWithCopiedCount(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
task = manifest.tasks(1).task;
donor = donor_for_task(task, 'partial-donor', 'donor-partial');
manifest.reuse_donors = [manifest.reuse_donors, donor];
manifest.tasks(1).reuse_candidate_ids = {'partial-donor'};
write_text(fullfile(donor.output_leaves.native, 'efield.nii.gz'), 'partial');
manifest = mh_vta_validate_subject_manifest(manifest);

resolution = mh_vta_resolve_manifest_task(manifest, 1);

verifyEqual(testCase, string(resolution.status), "ready");
verifyEqual(testCase, resolution.copied_artifact_count, 1);
verifyEqual(testCase, resolution.missing_artifact_count, 7);
verifyTrue(testCase, isfield(resolution.task, 'missing_artifacts'));
end

function testMissingTaskWithoutDonorIsReady(testCase)
[manifest, cleanup] = fixture_manifest(1); %#ok<ASGLU>
manifest = mh_vta_validate_subject_manifest(manifest);

resolution = mh_vta_resolve_manifest_task(manifest, 1);

verifyEqual(testCase, string(resolution.status), "ready");
verifyEqual(testCase, resolution.copied_artifact_count, 0);
verifyEqual(testCase, resolution.missing_artifact_count, 8);
end

function testGroupPeakDependencyIsArtifactSpecific(testCase)
[manifest, cleanup] = fixture_group_peak_manifest(); %#ok<ASGLU>
manifest = mh_vta_validate_subject_manifest(manifest);

blocked = mh_vta_resolve_manifest_task(manifest, 2);
verifyEqual(testCase, string(blocked.status), "skipped_dependency");
verifyEqual(testCase, string(blocked.blocked_dependency_ids), "source-task");

write_text(fullfile(manifest.tasks(2).task.output_leaves.native, ...
    'efield.nii.gz'), 'existing-peak');
ready = mh_vta_resolve_manifest_task(manifest, 2);
verifyEqual(testCase, string(ready.status), "ready");
verifyEmpty(testCase, ready.blocked_dependency_ids);
end

function testAtomicCopyDoesNotOverwriteOrDeleteSource(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() remove_tree(root));
source = fullfile(root, 'source.nii.gz');
destination = fullfile(root, 'destination.nii.gz');
write_text(source, 'source');
write_text(destination, 'destination');

copied = mh_vta_copy_artifact_atomic(source, destination);

verifyFalse(testCase, copied);
verifyEqual(testCase, read_text(source), "source");
verifyEqual(testCase, read_text(destination), "destination");
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
        sprintf('phase-%d', taskIndex), 'continuous_joint', {}, ...
        fixture_sources());
    leaves = task.output_leaves;
    staticTask = rmfield(task, {'run_id', 'output_leaves'});
    tasks(taskIndex) = struct('task', staticTask, ...
        'output_leaves', leaves, 'reuse_candidate_ids', {{}});
    donors(taskIndex) = struct('donor_id', staticTask.task_id, ...
        'output_leaves', leaves);
end
manifest = struct('schema_version', 'vta_subject_manifest_v1', ...
    'run_id', 'run-001', 'subject_id', 'S001', ...
    'tasks', tasks, 'reuse_donors', donors);
end

function [manifest, cleanup] = fixture_group_peak_manifest()
[manifest, cleanup] = fixture_manifest(2);
subjectDir = manifest.tasks(1).task.subject_dir;
source = fixture_task(subjectDir, 'source-task', 'group-phase', ...
    'alternating_source', {}, fixture_sources());
peak = fixture_task(subjectDir, 'peak-task', 'group-phase', ...
    'alternating_group_peak', {'source-task'}, fixture_sources());
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

function task = fixture_task(subjectDir, taskId, phaseId, kind, dependencies, sources)
if nargin < 6
    sources = fixture_sources();
end
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
    'sources', sources, ...
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

function write_text(path, content)
folder = fileparts(path);
if ~isfolder(folder)
    mkdir(folder);
end
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create fixture artifact.');
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, content, 'char');
end

function content = read_text(path)
content = string(fileread(path));
end

function verify_manifest_error(testCase, manifest)
verifyError(testCase, @() mh_vta_validate_subject_manifest(manifest), ...
    'mh_vta:InvalidSubjectManifest');
end

function path = canonical_path(value)
file = javaObject('java.io.File', char(string(value)));
path = char(file.getCanonicalPath());
end

function remove_tree(path)
if isfolder(path)
    rmdir(path, 's');
end
end
