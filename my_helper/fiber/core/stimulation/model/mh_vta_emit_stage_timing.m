function mh_vta_emit_stage_timing(emit, scope, taskId, stage, ...
        status, durationSeconds, cacheStatus)
% Validate and emit one vta_event_v1 stage timing event.

if isempty(emit)
    return;
end
if ~isa(emit, 'function_handle')
    error('mh_vta:InvalidEventEmitter', ...
        'Event emitter must be a function handle or empty.');
end
if nargin < 7
    cacheStatus = '';
end

scope = normalize_text(scope, 'scope');
if ~ismember(string(scope), ["subject", "task"])
    error('mh_vta:InvalidTimingScope', ...
        'Timing scope must be subject or task.');
end
stage = normalize_text(stage, 'stage');
allowedStages = [ ...
    "path_initialization", "manifest_decode_validation", ...
    "task_runtime_resolution", "subject_reconstruction_context", ...
    "headmodel_build_or_load", "active_contact_boundary", ...
    "fem_matrix_preparation", "fem_preconditioner", ...
    "fem_pcg_solve", "gradient_calculation", ...
    "electrode_removal_geometry", "native_grid_interpolation", ...
    "group_peak_composition", "threshold_generation", ...
    "native_to_mni_transform", "artifact_publication"];
if ~ismember(string(stage), allowedStages)
    error('mh_vta:InvalidTimingStage', ...
        'Unsupported VTA timing stage: %s.', stage);
end
status = normalize_text(status, 'status');
if ~ismember(string(status), ["executed", "not_applicable"])
    error('mh_vta:InvalidTimingStatus', ...
        'Timing status must be executed or not_applicable.');
end
if ~isnumeric(durationSeconds) || ~isscalar(durationSeconds) || ...
        ~isfinite(durationSeconds) || durationSeconds < 0
    error('mh_vta:InvalidTimingDuration', ...
        'Timing duration must be a nonnegative finite scalar.');
end

cacheStatus = optional_text(cacheStatus, 'cacheStatus');
if ~isempty(cacheStatus) && ...
        ~ismember(string(cacheStatus), ["hit", "miss"])
    error('mh_vta:InvalidCacheStatus', ...
        'Cache status must be hit, miss, or empty.');
end
if strcmp(status, 'not_applicable') && ...
        (durationSeconds ~= 0 || ~isempty(cacheStatus))
    error('mh_vta:InvalidNotApplicableTiming', ...
        'A not_applicable stage must have zero duration and no cache status.');
end

fields = struct( ...
    'scope', scope, ...
    'stage', stage, ...
    'stage_status', status, ...
    'duration_seconds', double(durationSeconds));
if strcmp(scope, 'task')
    fields.task_id = normalize_text(taskId, 'taskId');
elseif ~isempty(optional_text(taskId, 'taskId'))
    error('mh_vta:InvalidSubjectTimingTask', ...
        'Subject-scope timing cannot include a task ID.');
end
if ~isempty(cacheStatus)
    fields.cache_status = cacheStatus;
end
emit('stage_timing', fields);
end

function value = normalize_text(value, label)
if ~(ischar(value) && isrow(value)) && ...
        ~(isstring(value) && isscalar(value))
    error('mh_vta:InvalidTimingField', ...
        '%s must be nonempty scalar text.', label);
end
text = string(value);
if ~isscalar(text) || ismissing(text) || strlength(text) == 0
    error('mh_vta:InvalidTimingField', ...
        '%s must be nonempty scalar text.', label);
end
value = char(text);
end

function value = optional_text(value, label)
if isempty(value)
    value = '';
    return;
end
if ~(ischar(value) && isrow(value)) && ...
        ~(isstring(value) && isscalar(value))
    error('mh_vta:InvalidTimingField', ...
        '%s must be scalar text or empty.', label);
end
text = string(value);
if ~isscalar(text) || ismissing(text)
    error('mh_vta:InvalidTimingField', ...
        '%s must be scalar text or empty.', label);
end
value = char(text);
end
