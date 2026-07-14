function result = mh_vta_run_canonical_subject_manifest( ...
        manifestJsonPath, repoRoot, varargin)
% Execute one validated VTA subject manifest in the current MATLAB process.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('SolveFunction', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('DerivedFunction', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.parse(varargin{:});

root = string(repoRoot);
if ~isscalar(root) || ismissing(root) || strlength(root) == 0 || ~isfolder(root)
    error('mh_vta:InvalidRepositoryRoot', ...
        'Repository root must name an existing directory.');
end
pathTimer = tic;
addpath(genpath(char(root)));
pathDuration = toc(pathTimer);

path = string(manifestJsonPath);
if ~isscalar(path) || ismissing(path) || strlength(path) == 0 || ~isfile(path)
    error('mh_vta:InvalidSubjectManifestPath', ...
        'Subject manifest JSON path must name an existing file.');
end

initializationTimer = tic;
try
    manifest = jsondecode(fileread(path));
catch ME
    wrapped = MException('mh_vta:InvalidSubjectManifestJson', ...
        'Could not decode subject manifest JSON: %s', path);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end
manifest = mh_vta_validate_subject_manifest(manifest);
initializationDuration = toc(initializationTimer);

emit = mh_vta_make_event_emitter(manifest.run_id, manifest.subject_id);
mh_vta_emit_stage_timing(emit, 'subject', '', ...
    'path_initialization', 'executed', pathDuration, '');
mh_vta_emit_stage_timing(emit, 'subject', '', ...
    'manifest_decode_validation', 'executed', initializationDuration, '');
emit('subject_ready', struct());

runtime = mh_vta_create_subject_runtime(manifest.subject_id);
outcomes = repmat(empty_outcome(), numel(manifest.tasks), 1);
for taskIndex = 1:numel(manifest.tasks)
    taskId = char(string(manifest.tasks(taskIndex).task.task_id));
    emit('task_started', struct('task_id', taskId));
    outcomes(taskIndex) = run_task( ...
        manifest, taskIndex, emit, parser.Results, runtime);
    emit('task_outcome', outcome_fields(outcomes(taskIndex)));
end

summary = make_summary(outcomes);
emit('subject_summary', summary);
result = struct('outcomes', outcomes, 'summary', summary);
end

function outcome = run_task(manifest, taskIndex, emit, options, runtime)
taskId = char(string(manifest.tasks(taskIndex).task.task_id));
resolutionTimer = tic;
try
    resolution = mh_vta_resolve_manifest_task(manifest, taskIndex);
catch ME
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'task_runtime_resolution', 'executed', toc(resolutionTimer), '');
    outcome = failed_outcome(taskId, 0, 0, ME);
    return;
end
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'task_runtime_resolution', 'executed', toc(resolutionTimer), '');

if ~strcmp(resolution.status, 'ready')
    outcome = empty_outcome();
    outcome.task_id = taskId;
    outcome.status = resolution.status;
    outcome.copied_artifact_count = resolution.copied_artifact_count;
    return;
end

try
    execute_task(resolution.task, emit, options, runtime);
    [~, remainingCount] = mh_vta_missing_task_artifacts(resolution.task);
    generatedCount = max(0, ...
        resolution.missing_artifact_count - remainingCount);
    if remainingCount == 0
        outcome = completed_outcome(resolution, 'generated', generatedCount);
    else
        incompleteError = MException('mh_vta:IncompleteTaskArtifacts', ...
            'Task %s returned without publishing all expected artifacts.', ...
            taskId);
        outcome = failed_outcome(taskId, ...
            resolution.copied_artifact_count, generatedCount, incompleteError);
    end
catch ME
    [~, remainingCount] = mh_vta_missing_task_artifacts(resolution.task);
    generatedCount = max(0, ...
        resolution.missing_artifact_count - remainingCount);
    outcome = failed_outcome(taskId, ...
        resolution.copied_artifact_count, generatedCount, ME);
end
end

function execute_task(task, emit, options, runtime)
callArguments = {'EventEmitter', emit, 'SubjectRuntime', runtime};
if ~isempty(options.SolveFunction)
    callArguments = [callArguments, ...
        {'SolveFunction', options.SolveFunction}];
end
if ~isempty(options.DerivedFunction)
    callArguments = [callArguments, ...
        {'DerivedFunction', options.DerivedFunction}];
end
mh_vta_execute_canonical_task(task, callArguments{:});
end

function outcome = completed_outcome(resolution, status, generatedCount)
outcome = empty_outcome();
outcome.task_id = char(string(resolution.task.task_id));
outcome.status = status;
outcome.copied_artifact_count = resolution.copied_artifact_count;
outcome.generated_artifact_count = generatedCount;
end

function outcome = failed_outcome(taskId, copiedCount, generatedCount, ME)
outcome = empty_outcome();
outcome.task_id = taskId;
outcome.status = 'failed';
outcome.copied_artifact_count = copiedCount;
outcome.generated_artifact_count = generatedCount;
outcome = attach_error(outcome, ME);
end

function outcome = attach_error(outcome, ME)
if ~isempty(ME.identifier)
    outcome.error_identifier = ME.identifier;
end
if ~isempty(ME.message)
    outcome.error_message = ME.message;
end
end

function outcome = empty_outcome()
outcome = struct( ...
    'task_id', '', ...
    'status', '', ...
    'copied_artifact_count', 0, ...
    'generated_artifact_count', 0, ...
    'error_identifier', '', ...
    'error_message', '');
end

function fields = outcome_fields(outcome)
fields = struct( ...
    'task_id', outcome.task_id, ...
    'status', outcome.status, ...
    'copied_artifact_count', outcome.copied_artifact_count, ...
    'generated_artifact_count', outcome.generated_artifact_count);
if ~isempty(outcome.error_identifier)
    fields.error_identifier = outcome.error_identifier;
end
if ~isempty(outcome.error_message)
    fields.error_message = outcome.error_message;
end
end

function summary = make_summary(outcomes)
statuses = { ...
    'generated', 'copied', 'skipped_existing', ...
    'recovered_complete', 'failed', 'skipped_dependency'};
summary = struct();
outcomeStatuses = string({outcomes.status});
for statusIndex = 1:numel(statuses)
    status = statuses{statusIndex};
    summary.(status) = nnz(outcomeStatuses == string(status));
end
summary.process_success = ...
    summary.failed == 0 && summary.skipped_dependency == 0;
end
