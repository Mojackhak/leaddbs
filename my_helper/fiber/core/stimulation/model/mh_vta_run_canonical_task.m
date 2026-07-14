function status = mh_vta_run_canonical_task(taskJsonPath, varargin)
% Read, validate, and execute one canonical VTA task JSON file.

path = string(taskJsonPath);
if ~isscalar(path) || ismissing(path) || strlength(path) == 0 || ~isfile(path)
    error('mh_vta:InvalidCanonicalTaskPath', ...
        'Canonical task JSON path must name an existing file.');
end

initializationTimer = tic;
try
    task = jsondecode(fileread(path));
catch ME
    wrapped = MException('mh_vta:InvalidCanonicalTaskJson', ...
        'Could not decode canonical task JSON: %s', path);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end

task = mh_vta_validate_canonical_task(task);
initializationDuration = toc(initializationTimer);
emit = mh_vta_make_event_emitter(task.run_id, task.subject_id);
mh_vta_emit_stage_timing(emit, 'subject', '', ...
    'manifest_decode_validation', 'executed', initializationDuration, '');
emit('subject_ready', struct());
emit('task_started', struct('task_id', task.task_id));

try
    status = mh_vta_execute_canonical_task(task, varargin{:}, ...
        'EventEmitter', emit);
    generatedCount = requested_artifact_count(task.missing_artifacts);
    emit('task_outcome', struct( ...
        'task_id', task.task_id, ...
        'status', 'generated', ...
        'copied_artifact_count', 0, ...
        'generated_artifact_count', generatedCount));
    emit_summary(emit, true, 'generated');
catch ME
    failureFields = struct( ...
        'task_id', task.task_id, ...
        'status', 'failed', ...
        'copied_artifact_count', 0, ...
        'generated_artifact_count', 0);
    if ~isempty(ME.identifier)
        failureFields.error_identifier = ME.identifier;
    end
    if ~isempty(ME.message)
        failureFields.error_message = ME.message;
    end
    emit('task_outcome', failureFields);
    emit_summary(emit, false, 'failed');
    rethrow(ME);
end
end

function count = requested_artifact_count(missingArtifacts)
count = 0;
spaces = fieldnames(missingArtifacts);
for spaceIndex = 1:numel(spaces)
    count = count + numel(missingArtifacts.(spaces{spaceIndex}));
end
end

function emit_summary(emit, processSuccess, outcomeStatus)
statuses = { ...
    'generated', 'copied', 'skipped_existing', ...
    'recovered_complete', 'failed', 'skipped_dependency'};
fields = struct();
for statusIndex = 1:numel(statuses)
    status = statuses{statusIndex};
    fields.(status) = double(strcmp(status, outcomeStatus));
end
fields.process_success = logical(processSuccess);
emit('subject_summary', fields);
end
