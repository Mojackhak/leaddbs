function task = mh_vta_validate_canonical_task(task)
% Validate and resolve one canonical VTA task payload.

if ~isstruct(task) || ~isscalar(task)
    invalid_task('Canonical task must be a scalar struct.');
end

requiredFields = { ...
    'task_id', 'kind', 'subject_id', 'subject_dir', ...
    'reconstruction_path', 'phase_id', 'program_id', 'electrode_id', ...
    'hemisphere', 'electrode_model', 'reconstruction_lead_id', ...
    'frequency_group_id', 'delivery_mode', 'sources', 'dependencies', ...
    'model', 'run_id', 'output_leaves', 'missing_artifacts'};
require_fields(task, requiredFields, 'task');
if isfield(task, 'backend')
    invalid_task('Canonical tasks must not select a backend.');
end

textFields = { ...
    'task_id', 'subject_id', 'subject_dir', 'reconstruction_path', ...
    'phase_id', 'electrode_id', 'electrode_model', 'frequency_group_id', ...
    'run_id'};
for fieldIndex = 1:numel(textFields)
    require_nonempty_text(task.(textFields{fieldIndex}), textFields{fieldIndex});
end
require_nonnegative_integer(task.program_id, 'program_id');
require_positive_integer(task.reconstruction_lead_id, 'reconstruction_lead_id');

kind = lower(string(task.kind));
if ~isscalar(kind) || ~ismember(kind, ...
        ["continuous_joint", "alternating_source", "alternating_group_peak"])
    invalid_task('Unsupported task kind.');
end
deliveryMode = lower(string(task.delivery_mode));
if ~isscalar(deliveryMode) || ...
        ~ismember(deliveryMode, ["continuous", "alternating"])
    invalid_task('Unsupported delivery_mode.');
end
hemisphere = upper(string(task.hemisphere));
if ~isscalar(hemisphere) || ~ismember(hemisphere, ["L", "R"])
    invalid_task('hemisphere must be L or R.');
end

if kind == "continuous_joint" && deliveryMode ~= "continuous" || ...
        kind ~= "continuous_joint" && deliveryMode ~= "alternating"
    error('mh_vta:TaskKindDeliveryMismatch', ...
        'Task kind %s is incompatible with delivery mode %s.', ...
        kind, deliveryMode);
end

sources = task.sources;
if ~isstruct(sources) || isempty(sources)
    invalid_task('sources must be a nonempty struct array.');
end
validate_sources(sources);
validate_model(task.model);
validate_runtime_context(task);

task.kind = char(kind);
task.delivery_mode = char(deliveryMode);
task.hemisphere = char(hemisphere);
switch kind
    case "continuous_joint"
        task.solve_units = mh_vta_expand_delivery_group(deliveryMode, sources);
    case "alternating_source"
        if numel(sources) ~= 1
            invalid_task('alternating_source tasks must contain exactly one source.');
        end
        task.solve_units = mh_vta_expand_delivery_group(deliveryMode, sources);
    case "alternating_group_peak"
        task.solve_units = cell(0, 1);
end

function validate_runtime_context(task)
if ~isstruct(task.output_leaves) || ~isscalar(task.output_leaves)
    invalid_task('output_leaves must be a scalar struct.');
end
if ~isstruct(task.missing_artifacts) || ~isscalar(task.missing_artifacts)
    invalid_task('missing_artifacts must be a scalar struct.');
end
spaces = cellstr(string(task.model.spaces));
requestedCount = 0;
for spaceIndex = 1:numel(spaces)
    space = spaces{spaceIndex};
    if ~isfield(task.output_leaves, space)
        invalid_task('output_leaves is missing space %s.', space);
    end
    require_nonempty_text(task.output_leaves.(space), ...
        sprintf('output_leaves.%s', space));
    if ~isfield(task.missing_artifacts, space)
        continue;
    end
    names = string(task.missing_artifacts.(space));
    names = names(:);
    if isempty(names) || any(ismissing(names)) || any(strlength(names) == 0)
        invalid_task('missing_artifacts.%s must contain file names.', space);
    end
    allowed = expected_artifact_names(task.model.thresholds_v_per_m);
    if any(~ismember(names, allowed)) || numel(unique(names)) ~= numel(names)
        invalid_task('missing_artifacts.%s contains an invalid file name.', space);
    end
    requestedCount = requestedCount + numel(names);
end
unknownSpaces = setdiff(fieldnames(task.missing_artifacts), spaces);
if ~isempty(unknownSpaces)
    invalid_task('missing_artifacts contains unsupported space %s.', ...
        unknownSpaces{1});
end
if requestedCount == 0
    invalid_task('missing_artifacts must request at least one artifact.');
end
end
end

function names = expected_artifact_names(thresholds)
names = "efield.nii.gz";
for threshold = double(thresholds(:)')
    token = strrep(sprintf('%.2f', threshold / 1000), '.', 'p');
    names(end + 1) = "vta_threshold-" + token + "Vpermm.nii.gz"; %#ok<AGROW>
end
end

function validate_sources(sources)
requiredFields = { ...
    'source_id', 'frequency_hz', 'control_mode', 'amplitude', ...
    'pulse_width_us', 'contacts'};
sourceIds = strings(1, numel(sources));
for sourceIndex = 1:numel(sources)
    source = sources(sourceIndex);
    require_fields(source, requiredFields, 'source');
    require_nonempty_text(source.source_id, 'source_id');
    sourceIds(sourceIndex) = string(source.source_id);
    require_positive_finite(source.frequency_hz, 'frequency_hz');
    require_positive_finite(source.amplitude, 'amplitude');
    require_positive_finite(source.pulse_width_us, 'pulse_width_us');
    controlMode = lower(string(source.control_mode));
    if ~isscalar(controlMode) || ...
            ~ismember(controlMode, ["voltage", "current"])
        invalid_task('control_mode must be voltage or current.');
    end
    if ~isstruct(source.contacts) || isempty(source.contacts)
        invalid_task('contacts must be a nonempty struct array.');
    end
end
if numel(unique(sourceIds)) ~= numel(sourceIds)
    invalid_task('source_id values must be unique within a task.');
end

controlModes = lower(string({sources.control_mode}));
if numel(unique(controlModes)) ~= 1
    error('mh_vta:MixedControlMode', ...
        'A frequency group must use one control mode.');
end
frequencies = double([sources.frequency_hz]);
if any(frequencies ~= frequencies(1))
    error('mh_vta:MixedFrequency', ...
        'A frequency group must use one frequency.');
end
end

function validate_model(model)
if ~isstruct(model) || ~isscalar(model)
    invalid_task('model must be a scalar struct.');
end
require_fields(model, { ...
    'gray_matter_s_per_m', 'white_matter_s_per_m', 'atlas_set', ...
    'spaces', 'thresholds_v_per_m'}, 'model');
require_positive_finite(model.gray_matter_s_per_m, 'gray_matter_s_per_m');
require_positive_finite(model.white_matter_s_per_m, 'white_matter_s_per_m');
require_nonempty_text(model.atlas_set, 'atlas_set');

spaces = string(model.spaces);
if isempty(spaces) || any(strlength(spaces) == 0) || ...
        any(~ismember(spaces, ["native", "MNI152NLin2009bAsym"])) || ...
        numel(unique(spaces)) ~= numel(spaces)
    invalid_task('model.spaces contains invalid or duplicate output spaces.');
end
thresholds = double(model.thresholds_v_per_m);
if isempty(thresholds) || ~isvector(thresholds) || ...
        any(~isfinite(thresholds)) || any(thresholds <= 0)
    invalid_task('model.thresholds_v_per_m must contain positive finite values.');
end
end

function require_fields(value, fields, label)
missing = fields(~isfield(value, fields));
if ~isempty(missing)
    invalid_task('%s is missing required field %s.', label, missing{1});
end
end

function require_nonempty_text(value, label)
text = string(value);
if ~isscalar(text) || ismissing(text) || strlength(text) == 0
    invalid_task('%s must be nonempty text.', label);
end
end

function require_positive_finite(value, label)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || value <= 0
    invalid_task('%s must be a positive finite scalar.', label);
end
end

function require_nonnegative_integer(value, label)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || ...
        value < 0 || value ~= fix(value)
    invalid_task('%s must be a nonnegative integer.', label);
end
end

function require_positive_integer(value, label)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || ...
        value <= 0 || value ~= fix(value)
    invalid_task('%s must be a positive integer.', label);
end
end

function invalid_task(message, varargin)
error('mh_vta:InvalidCanonicalTask', message, varargin{:});
end
