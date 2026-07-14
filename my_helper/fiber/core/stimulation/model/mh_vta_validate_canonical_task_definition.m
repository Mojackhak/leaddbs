function task = mh_vta_validate_canonical_task_definition(task)
% Validate one canonical VTA task without requiring runtime artifact state.

if ~isstruct(task) || ~isscalar(task)
    invalid_task('Canonical task must be a scalar struct.');
end
requiredFields = { ...
    'task_id', 'kind', 'subject_id', 'subject_dir', ...
    'reconstruction_path', 'phase_id', 'program_id', 'electrode_id', ...
    'hemisphere', 'electrode_model', 'reconstruction_lead_id', ...
    'frequency_group_id', 'delivery_mode', 'sources', 'dependencies', ...
    'model'};
require_fields(task, requiredFields, 'task');
if isfield(task, 'backend')
    invalid_task('Canonical tasks must not select a backend.');
end

textFields = { ...
    'task_id', 'subject_id', 'subject_dir', 'reconstruction_path', ...
    'phase_id', 'electrode_id', 'electrode_model', 'frequency_group_id'};
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
validate_dependencies(task.dependencies);

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
    validate_contacts(source.contacts);
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

function validate_contacts(contacts)
requiredFields = {'contact', 'polarity', 'fraction'};
keys = strings(1, numel(contacts));
polarities = strings(1, numel(contacts));
fractions = zeros(1, numel(contacts));
for contactIndex = 1:numel(contacts)
    contact = contacts(contactIndex);
    require_fields(contact, requiredFields, 'contact');
    if ischar(contact.contact) || ...
            isstring(contact.contact) && isscalar(contact.contact)
        contactId = lower(string(contact.contact));
        if contactId ~= "case"
            invalid_task('Text contact identifiers must equal case.');
        end
    elseif isnumeric(contact.contact) && isscalar(contact.contact) && ...
            isfinite(contact.contact) && contact.contact > 0 && ...
            contact.contact == fix(contact.contact)
        contactId = string(contact.contact);
    else
        invalid_task('contact must be a positive integer or case.');
    end
    polarity = lower(string(contact.polarity));
    if ~isscalar(polarity) || ~ismember(polarity, ["cathode", "anode"])
        invalid_task('polarity must be cathode or anode.');
    end
    require_positive_finite(contact.fraction, 'contact fraction');
    keys(contactIndex) = contactId + ":" + polarity;
    polarities(contactIndex) = polarity;
    fractions(contactIndex) = double(contact.fraction);
end
if numel(unique(keys)) ~= numel(keys)
    invalid_task('contacts contain duplicate contact/polarity pairs.');
end
for polarity = ["cathode", "anode"]
    selected = polarities == polarity;
    if any(selected) && abs(sum(fractions(selected)) - 1) > 1e-9
        invalid_task('%s contact fractions must sum to 1.', polarity);
    end
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
spaces = spaces(:);
if isempty(spaces) || any(ismissing(spaces)) || any(strlength(spaces) == 0) || ...
        any(~ismember(spaces, ["native", "MNI152NLin2009bAsym"])) || ...
        numel(unique(spaces)) ~= numel(spaces)
    invalid_task('model.spaces contains invalid or duplicate output spaces.');
end
thresholds = double(model.thresholds_v_per_m);
if isempty(thresholds) || ~isvector(thresholds) || ...
        any(~isfinite(thresholds)) || any(thresholds <= 0)
    invalid_task('model.thresholds_v_per_m must contain positive finite values.');
end
artifactNames = mh_vta_expected_artifact_names(thresholds);
if numel(unique(artifactNames)) ~= numel(artifactNames)
    invalid_task('model thresholds produce colliding artifact file names.');
end
end

function validate_dependencies(value)
dependencies = string(value);
dependencies = dependencies(:);
if any(ismissing(dependencies)) || any(strlength(dependencies) == 0) || ...
        numel(unique(dependencies)) ~= numel(dependencies)
    invalid_task('dependencies must contain unique nonempty task IDs.');
end
end

function require_fields(value, fields, label)
missing = fields(~isfield(value, fields));
if ~isempty(missing)
    invalid_task('%s is missing required field %s.', label, missing{1});
end
end

function require_nonempty_text(value, label)
if ~(ischar(value) || isstring(value) && isscalar(value))
    invalid_task('%s must be text.', label);
end
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
