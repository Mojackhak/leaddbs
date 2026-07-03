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
    stimSpec.space = 'native_and_mni';
end

required = {'side', 'contact', 'amp', 'unit', 'pulseWidth', 'frequency', 'cathode', 'anode'};
for i = 1:numel(stimSpec.sources)
    for f = 1:numel(required)
        if ~isfield(stimSpec.sources(i), required{f})
            error('mh_fiber_set_stimulation:MissingSourceField', ...
                'Source %d is missing field: %s', i, required{f});
        end
    end
    stimSpec.sources(i).side = upper(char(string(stimSpec.sources(i).side)));
    stimSpec.sources(i).unit = normalize_unit(stimSpec.sources(i).unit);
    stimSpec.sources(i).anode = lower(char(string(stimSpec.sources(i).anode)));
end
end

function validate_sources(sources, maxSourcesPerSide)
validSides = ["L", "R"];
units = strings(numel(sources), 1);
counts = struct('L', 0, 'R', 0);

for i = 1:numel(sources)
    side = string(sources(i).side);
    if ~ismember(side, validSides)
        error('mh_fiber_set_stimulation:InvalidSide', 'Source %d side must be L or R.', i);
    end
    if sources(i).contact < 1 || sources(i).contact ~= fix(sources(i).contact)
        error('mh_fiber_set_stimulation:InvalidContact', 'Source %d contact must be a positive integer.', i);
    end
    if sources(i).amp <= 0 || isnan(sources(i).amp)
        error('mh_fiber_set_stimulation:InvalidAmplitude', 'Source %d amplitude must be positive.', i);
    end
    if sources(i).pulseWidth <= 0 || isnan(sources(i).pulseWidth)
        error('mh_fiber_set_stimulation:InvalidPulseWidth', 'Source %d pulseWidth must be positive.', i);
    end
    if sources(i).frequency <= 0 || isnan(sources(i).frequency)
        error('mh_fiber_set_stimulation:InvalidFrequency', 'Source %d frequency must be positive.', i);
    end
    if ~logical(sources(i).cathode)
        error('mh_fiber_set_stimulation:UnsupportedPolarity', ...
            'Only cathodic contacts with case anode are supported by this helper.');
    end
    if ~strcmpi(sources(i).anode, 'case')
        error('mh_fiber_set_stimulation:UnsupportedAnode', ...
            'Only case anode is supported by this helper.');
    end

    sideField = char(side);
    counts.(sideField) = counts.(sideField) + 1;
    if counts.(sideField) > maxSourcesPerSide
        error('mh_fiber_set_stimulation:TooManySources', ...
            'Side %s has more than %d sources.', sideField, maxSourcesPerSide);
    end
    units(i) = string(sources(i).unit);
end

if numel(unique(units)) > 1
    error('mh_fiber_set_stimulation:MixedUnits', 'Mixed voltage/current units are not supported.');
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
