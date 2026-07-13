function cfg = mh_fiber_set_stimulation(cfg, stimSpec)
% Attach a validated stimulation specification and stimulation label to cfg.

if nargin < 2 || ~isstruct(stimSpec)
    error('mh_fiber_set_stimulation:InvalidStimSpec', 'stimSpec must be a struct.');
end
if ~isfield(stimSpec, 'sources') || isempty(stimSpec.sources)
    error('mh_fiber_set_stimulation:EmptySources', 'stimSpec.sources must contain at least one source.');
end

stimSpec = normalize_stim_spec(stimSpec);
validate_sources(stimSpec.sources, cfg.maxSourcesPerSide);

if ~isfield(stimSpec, 'label') || strlength(string(stimSpec.label)) == 0
    stimSpec.label = mh_fiber_make_stim_label(stimSpec);
else
    stimSpec.label = mh_util_sanitize_label(stimSpec.label, ...
        'PreservePlus', true, ...
        'ErrorId', 'mh_fiber_set_stimulation:InvalidLabel');
end

if ~isfield(stimSpec, 'model') || strlength(string(stimSpec.model)) == 0
    stimSpec.model = cfg.vta.modelKey;
end
cfg.vta.modelKey = char(lower(string(stimSpec.model)));
cfg.vta.model = mh_fiber_model_name(stimSpec.model);

if isfield(stimSpec, 'space') && strlength(string(stimSpec.space)) > 0
    cfg.vta.space = char(string(stimSpec.space));
end

cfg.stimSpec = stimSpec;
cfg.stimLabel = stimSpec.label;
cfg.outputDir = fullfile(cfg.outputRoot, cfg.stimLabel);

end

function stimSpec = normalize_stim_spec(stimSpec)
if ~isfield(stimSpec, 'label')
    stimSpec.label = '';
end
if ~isfield(stimSpec, 'model')
    stimSpec.model = '';
end
if ~isfield(stimSpec, 'space')
    stimSpec.space = mh_vta_default_config_space();
end

required = {'side', 'amp', 'unit', 'pulseWidth', 'frequency'};
normalized = repmat(empty_source(), numel(stimSpec.sources), 1);
for i = 1:numel(stimSpec.sources)
    inputSource = stimSpec.sources(i);
    for f = 1:numel(required)
        if ~isfield(inputSource, required{f})
            error('mh_fiber_set_stimulation:MissingSourceField', ...
                'Source %d is missing field: %s', i, required{f});
        end
    end
    source = empty_source();
    source.side = upper(char(string(inputSource.side)));
    source.amp = double(inputSource.amp);
    source.unit = normalize_unit(inputSource.unit);
    source.pulseWidth = double(inputSource.pulseWidth);
    source.frequency = double(inputSource.frequency);
    source.controlMode = unit_to_control_mode(source.unit);
    if isfield(inputSource, 'controlMode') && ...
            ~strcmpi(char(string(inputSource.controlMode)), source.controlMode)
        error('mh_fiber_set_stimulation:ControlModeUnitMismatch', ...
            'Source %d controlMode does not match unit %s.', i, source.unit);
    end
    if isfield(inputSource, 'contacts')
        source.contacts = normalize_contacts(inputSource.contacts, i);
    else
        source.contacts = legacy_contacts(inputSource, i);
    end
    normalized(i) = source;
end
stimSpec.sources = normalized;
end

function validate_sources(sources, maxSourcesPerSide)
validSides = ["L", "R"];
counts = struct('L', 0, 'R', 0);

for i = 1:numel(sources)
    side = string(sources(i).side);
    if ~ismember(side, validSides)
        error('mh_fiber_set_stimulation:InvalidSide', 'Source %d side must be L or R.', i);
    end
    if ~isscalar(sources(i).amp) || ~isfinite(sources(i).amp) || sources(i).amp <= 0
        error('mh_fiber_set_stimulation:InvalidAmplitude', 'Source %d amplitude must be positive.', i);
    end
    if ~isscalar(sources(i).pulseWidth) || ~isfinite(sources(i).pulseWidth) || sources(i).pulseWidth <= 0
        error('mh_fiber_set_stimulation:InvalidPulseWidth', 'Source %d pulseWidth must be positive.', i);
    end
    if ~isscalar(sources(i).frequency) || ~isfinite(sources(i).frequency) || sources(i).frequency <= 0
        error('mh_fiber_set_stimulation:InvalidFrequency', 'Source %d frequency must be positive.', i);
    end
    validate_contacts(sources(i).contacts, sources(i).controlMode, i);

    sideField = char(side);
    counts.(sideField) = counts.(sideField) + 1;
    if counts.(sideField) > maxSourcesPerSide
        error('mh_fiber_set_stimulation:TooManySources', ...
            'Side %s has more than %d sources.', sideField, maxSourcesPerSide);
    end
end
end

function source = empty_source()
source = struct( ...
    'side', '', ...
    'amp', NaN, ...
    'unit', 'V', ...
    'pulseWidth', NaN, ...
    'frequency', NaN, ...
    'controlMode', 'voltage', ...
    'contacts', repmat(empty_contact(), 0, 1));
end

function contact = empty_contact()
contact = struct('contact', NaN, 'polarity', '', 'fraction', NaN);
end

function contacts = legacy_contacts(source, sourceIndex)
required = {'contact', 'cathode', 'anode'};
for i = 1:numel(required)
    if ~isfield(source, required{i})
        error('mh_fiber_set_stimulation:MissingSourceField', ...
            'Source %d is missing field: %s', sourceIndex, required{i});
    end
end
if ~logical(source.cathode)
    error('mh_fiber_set_stimulation:UnsupportedPolarity', ...
        'Legacy source %d must use a cathodic active contact.', sourceIndex);
end
contacts = [ ...
    struct('contact', source.contact, 'polarity', 'cathode', 'fraction', 1.0), ...
    struct('contact', source.anode, 'polarity', 'anode', 'fraction', 1.0)];
contacts = normalize_contacts(contacts, sourceIndex);
end

function contacts = normalize_contacts(inputContacts, sourceIndex)
if ~isstruct(inputContacts) || isempty(inputContacts)
    error('mh_fiber_set_stimulation:InvalidContacts', ...
        'Source %d contacts must be a nonempty struct array.', sourceIndex);
end
required = {'contact', 'polarity', 'fraction'};
contacts = repmat(empty_contact(), numel(inputContacts), 1);
for i = 1:numel(inputContacts)
    for f = 1:numel(required)
        if ~isfield(inputContacts(i), required{f})
            error('mh_fiber_set_stimulation:MissingContactField', ...
                'Source %d contact %d is missing field: %s', ...
                sourceIndex, i, required{f});
        end
    end
    contact = empty_contact();
    contact.contact = normalize_contact_id(inputContacts(i).contact, sourceIndex, i);
    contact.polarity = lower(char(string(inputContacts(i).polarity)));
    contact.fraction = double(inputContacts(i).fraction);
    contacts(i) = contact;
end
end

function identifier = normalize_contact_id(value, sourceIndex, contactIndex)
if ischar(value) || (isstring(value) && isscalar(value))
    identifier = lower(char(string(value)));
    if ~strcmp(identifier, 'case')
        error('mh_fiber_set_stimulation:InvalidContact', ...
            'Source %d contact %d text identifier must be case.', sourceIndex, contactIndex);
    end
    return;
end
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || ...
        value < 1 || value ~= fix(value)
    error('mh_fiber_set_stimulation:InvalidContact', ...
        'Source %d contact %d must be a positive integer or case.', sourceIndex, contactIndex);
end
identifier = double(value);
end

function validate_contacts(contacts, controlMode, sourceIndex)
keys = strings(numel(contacts), 1);
polarities = strings(numel(contacts), 1);
fractions = zeros(numel(contacts), 1);
for i = 1:numel(contacts)
    if isnumeric(contacts(i).contact)
        keys(i) = "contact:" + string(contacts(i).contact);
    else
        keys(i) = "case";
    end
    polarities(i) = string(contacts(i).polarity);
    if ~ismember(polarities(i), ["cathode", "anode"])
        error('mh_fiber_set_stimulation:InvalidPolarity', ...
            'Source %d contact %d polarity must be cathode or anode.', sourceIndex, i);
    end
    fractions(i) = contacts(i).fraction;
    if ~isfinite(fractions(i)) || fractions(i) <= 0 || fractions(i) > 1
        error('mh_fiber_set_stimulation:InvalidContactFraction', ...
            'Source %d contact fractions must be in (0, 1].', sourceIndex);
    end
end
if numel(unique(keys)) ~= numel(keys)
    error('mh_fiber_set_stimulation:DuplicateContact', ...
        'Source %d contains a duplicate contact.', sourceIndex);
end
if ~any(polarities == "cathode") || ~any(polarities == "anode")
    error('mh_fiber_set_stimulation:MissingPolarity', ...
        'Source %d must contain at least one cathode and one anode.', sourceIndex);
end
caseIndex = find(keys == "case");
if ~isempty(caseIndex) && ...
        (numel(caseIndex) ~= 1 || polarities(caseIndex) ~= "anode" || sum(polarities == "anode") ~= 1)
    error('mh_fiber_set_stimulation:InvalidCaseReturn', ...
        'Source %d case must be the sole anode.', sourceIndex);
end
if strcmp(controlMode, 'voltage')
    if any(abs(fractions - 1.0) > 1e-9)
        error('mh_fiber_set_stimulation:InvalidContactFraction', ...
            'Voltage source %d contact fractions must equal 1.0.', sourceIndex);
    end
else
    for polarity = ["cathode", "anode"]
        if abs(sum(fractions(polarities == polarity)) - 1.0) > 1e-9
            error('mh_fiber_set_stimulation:InvalidContactFraction', ...
                'Current source %d %s fractions must sum to 1.0.', ...
                sourceIndex, polarity);
        end
    end
end
end

function mode = unit_to_control_mode(unit)
if strcmp(unit, 'V')
    mode = 'voltage';
else
    mode = 'current';
end
end

function unit = normalize_unit(unit)
unit = char(string(unit));
switch lower(unit)
    case {'v', 'volt', 'voltage'}
        unit = 'V';
    case {'ma', 'mamp', 'milliamp', 'current'}
        unit = 'mA';
    otherwise
        error('mh_fiber_set_stimulation:InvalidUnit', 'Unsupported stimulation unit: %s', unit);
end
end
