function [Phi, currentControl, caseGrounding, stimCenter, activeContacts] = ...
        mh_oss_assemble_boundary(request, contactLocations)
% Assemble one direct right-canonical OSS stimulation boundary.
%
% REQUEST is a validated row request with common control_mode, frequency_hz,
% pulse_width_us, contact_count, and one or more source structures.
% CONTACTLOCATIONS is contact_count-by-3 template-space geometry in mm.
%
% PHI is a one-by-contact_count vector with NaN for inactive contacts.
% CURRENTCONTROL is zero for voltage control and one for current control.
% CASEGROUNDING identifies an explicit case return. STIMCENTER is the
% absolute-boundary-weighted contact center, and ACTIVECONTACTS contains the
% one-based local numeric contact indices used by the boundary.

if nargin ~= 2 || ~isstruct(request) || ~isscalar(request)
    error('mh_oss:InvalidBoundary', ...
        'Boundary assembly requires one scalar request struct and contact geometry.');
end

requiredFields = {'contact_count', 'control_mode', 'delivery_mode', ...
    'frequency_hz', 'pulse_width_us', 'sources'};
require_fields(request, requiredFields, 'request');

contactCount = finite_scalar(request.contact_count, 'contact_count');
if contactCount < 1 || contactCount ~= fix(contactCount)
    error('mh_oss:InvalidBoundary', ...
        'contact_count must be a positive integer.');
end
controlMode = lower(text_scalar(request.control_mode, 'control_mode'));
if ~ismember(controlMode, {'voltage', 'current'})
    error('mh_oss:InvalidBoundary', ...
        'control_mode must be voltage or current.');
end
deliveryMode = lower(text_scalar(request.delivery_mode, 'delivery_mode'));
if ~ismember(deliveryMode, {'continuous', 'alternating'})
    error('mh_oss:InvalidBoundary', ...
        'delivery_mode must be continuous or alternating.');
end
frequencyHz = positive_scalar(request.frequency_hz, 'frequency_hz');
pulseWidthUs = positive_scalar(request.pulse_width_us, 'pulse_width_us');

if ~isnumeric(contactLocations) || ~isequal(size(contactLocations), [contactCount, 3])
    error('mh_oss:InvalidBoundary', ...
        'contactLocations must be contact_count-by-3.');
end
contactLocations = double(contactLocations);
if any(~isfinite(contactLocations), 'all')
    error('mh_oss:InvalidBoundary', ...
        'contactLocations must contain only finite coordinates.');
end

sources = request.sources;
if ~isstruct(sources) || isempty(sources)
    error('mh_oss:InvalidBoundary', ...
        'sources must be a nonempty struct array.');
end
if strcmp(deliveryMode, 'alternating') && numel(sources) ~= 1
    error('mh_oss:InvalidBoundary', ...
        'An alternating row must contain exactly one source.');
end

Phi = nan(1, contactCount);
usedNumericContacts = false(1, contactCount);
sourceIds = cell(1, numel(sources));
voltageTopology = '';
caseGrounding = 0;

for sourceIndex = 1:numel(sources)
    source = sources(sourceIndex);
    exact_fields(source, {'source_id', 'control_mode', 'amplitude', ...
        'frequency_hz', 'pulse_width_us', 'contacts'}, 'source');

    sourceId = text_scalar(source.source_id, 'source_id');
    if any(strcmp(sourceIds(1:sourceIndex-1), sourceId))
        error('mh_oss:InvalidBoundary', ...
            'Source IDs must be unique; duplicate: %s.', sourceId);
    end
    sourceIds{sourceIndex} = sourceId;

    sourceMode = lower(text_scalar(source.control_mode, ...
        sprintf('source %s control_mode', sourceId)));
    sourceFrequency = positive_scalar(source.frequency_hz, ...
        sprintf('source %s frequency_hz', sourceId));
    sourcePulseWidth = positive_scalar(source.pulse_width_us, ...
        sprintf('source %s pulse_width_us', sourceId));
    if ~strcmpi(sourceMode, controlMode) || sourceFrequency ~= frequencyHz || ...
            sourcePulseWidth ~= pulseWidthUs
        error('mh_oss:InconsistentSourceSettings', ...
            ['All sources must match the row control mode, frequency, ' ...
             'and pulse width.']);
    end
    amplitude = positive_scalar(source.amplitude, ...
        sprintf('source %s amplitude', sourceId));

    contacts = source.contacts;
    if ~isstruct(contacts) || isempty(contacts)
        error('mh_oss:InvalidBoundary', ...
            'Source %s contacts must be a nonempty struct array.', sourceId);
    end

    numericContacts = zeros(1, 0);
    numericPolarities = cell(1, 0);
    numericFractions = zeros(1, 0);
    casePolarity = '';
    polarityTotals = struct('cathode', 0, 'anode', 0);

    for contactIndex = 1:numel(contacts)
        contact = contacts(contactIndex);
        exact_fields(contact, {'contact', 'polarity', 'fraction'}, 'contact');
        polarity = lower(text_scalar(contact.polarity, ...
            sprintf('source %s contact polarity', sourceId)));
        if ~ismember(polarity, {'cathode', 'anode'})
            error('mh_oss:InvalidBoundary', ...
                'Source %s contact polarity must be cathode or anode.', sourceId);
        end
        fraction = positive_scalar(contact.fraction, ...
            sprintf('source %s contact fraction', sourceId));
        if fraction > 1
            error('mh_oss:InvalidBoundary', ...
                'Source %s contact fractions cannot exceed one.', sourceId);
        end
        if strcmp(controlMode, 'voltage') && fraction ~= 1
            error('mh_oss:InvalidVoltageFraction', ...
                ['Every active voltage-controlled contact must have ' ...
                 'fraction 1.0 for source %s.'], sourceId);
        end
        polarityTotals.(polarity) = polarityTotals.(polarity) + fraction;

        [isCase, numericContact] = parse_contact(contact.contact, ...
            contactCount, sourceId);
        if isCase
            if ~isempty(casePolarity)
                error('mh_oss:InvalidBoundary', ...
                    'Source %s cannot declare case more than once.', sourceId);
            end
            casePolarity = polarity;
            caseGrounding = 1;
            continue;
        end
        if any(numericContacts == numericContact)
            error('mh_oss:InvalidBoundary', ...
                'Source %s cannot reuse numeric contact %d.', ...
                sourceId, numericContact);
        end
        if usedNumericContacts(numericContact)
            error('mh_oss:ReusedNumericContact', ...
                'Numeric contact %d is reused across sources.', numericContact);
        end
        usedNumericContacts(numericContact) = true;
        numericContacts(end+1) = numericContact; %#ok<AGROW>
        numericPolarities{end+1} = polarity; %#ok<AGROW>
        numericFractions(end+1) = fraction; %#ok<AGROW>
    end

    if polarityTotals.cathode <= 0 || polarityTotals.anode <= 0
        error('mh_oss:InvalidBoundary', ...
            'Source %s requires at least one cathode and one anode.', sourceId);
    end
    if strcmp(controlMode, 'current')
        for polarity = {'cathode', 'anode'}
            name = polarity{1};
            if abs(polarityTotals.(name) - 1) > 1e-9
                error('mh_oss:InvalidPolarityFraction', ...
                    'Source %s %s fractions must sum to one.', sourceId, name);
            end
        end
    end
    if isempty(numericContacts)
        error('mh_oss:InvalidBoundary', ...
            'Source %s must activate at least one numeric contact.', sourceId);
    end

    if isempty(casePolarity)
        topology = 'electrode';
        if ~any(strcmp(numericPolarities, 'cathode')) || ...
                ~any(strcmp(numericPolarities, 'anode'))
            error('mh_oss:InvalidPolarityFraction', ...
                ['Electrode-return source %s requires numeric contacts ' ...
                 'of both polarities.'], sourceId);
        end
    else
        topology = 'case';
        if ~strcmp(casePolarity, 'anode')
            error('mh_oss:InvalidCaseReturn', ...
                'Case-return source %s requires an anodic case.', sourceId);
        end
        if any(strcmp(numericPolarities, casePolarity))
            error('mh_oss:InvalidBoundary', ...
                ['Case-return source %s must use case as the sole contact ' ...
                 'of its return polarity.'], sourceId);
        end
    end

    if strcmp(controlMode, 'voltage')
        if isempty(voltageTopology)
            voltageTopology = topology;
        elseif ~strcmp(voltageTopology, topology)
            error('mh_oss:MixedReturnTopology', ...
                ['Continuous voltage sources cannot mix case-return and ' ...
                 'electrode-return topology.']);
        end
        for index = 1:numel(numericContacts)
            contactNumber = numericContacts(index);
            signValue = polarity_sign(numericPolarities{index});
            if strcmp(topology, 'case')
                Phi(contactNumber) = signValue * amplitude;
            else
                Phi(contactNumber) = signValue * amplitude / 2;
            end
        end
    else
        for index = 1:numel(numericContacts)
            contactNumber = numericContacts(index);
            Phi(contactNumber) = polarity_sign(numericPolarities{index}) * ...
                amplitude * numericFractions(index);
        end
    end
end

activeContacts = find(~isnan(Phi));
if isempty(activeContacts)
    error('mh_oss:InvalidBoundary', ...
        'The assembled boundary has no active numeric contacts.');
end
weights = abs(Phi(activeContacts));
weightSum = sum(weights);
if ~isfinite(weightSum) || weightSum <= 0
    error('mh_oss:InvalidBoundary', ...
        'The assembled boundary has no positive absolute amplitude.');
end
stimCenter = sum(contactLocations(activeContacts, :) .* weights(:), 1) / weightSum;
currentControl = double(strcmp(controlMode, 'current'));
end

function require_fields(value, required, label)
actual = fieldnames(value);
missing = setdiff(required, actual);
if ~isempty(missing)
    error('mh_oss:InvalidBoundary', ...
        '%s is missing fields: %s.', label, strjoin(missing, ', '));
end
end

function exact_fields(value, expected, label)
actual = sort(fieldnames(value));
expected = sort(expected(:));
if ~isequal(actual, expected)
    missing = setdiff(expected, actual);
    extra = setdiff(actual, expected);
    error('mh_oss:InvalidBoundary', ...
        '%s fields differ; missing=%s extra=%s.', label, ...
        strjoin(missing, ','), strjoin(extra, ','));
end
end

function value = finite_scalar(raw, label)
if ~(isnumeric(raw) || islogical(raw)) || ~isscalar(raw)
    error('mh_oss:InvalidBoundary', '%s must be a numeric scalar.', label);
end
value = double(raw);
if ~isfinite(value)
    error('mh_oss:InvalidBoundary', '%s must be finite.', label);
end
end

function value = positive_scalar(raw, label)
value = finite_scalar(raw, label);
if value <= 0
    error('mh_oss:InvalidBoundary', '%s must be positive.', label);
end
end

function value = text_scalar(raw, label)
if ischar(raw) && (isrow(raw) || isempty(raw))
    value = strtrim(raw);
elseif isstring(raw) && isscalar(raw) && ~ismissing(raw)
    value = strtrim(char(raw));
else
    error('mh_oss:InvalidBoundary', '%s must be a text scalar.', label);
end
if isempty(value)
    error('mh_oss:InvalidBoundary', '%s must be nonempty.', label);
end
end

function [isCase, numericContact] = parse_contact(raw, contactCount, sourceId)
isCase = false;
numericContact = nan;
if isnumeric(raw) && isscalar(raw) && isfinite(raw) && raw == fix(raw)
    numericContact = double(raw);
    if numericContact < 1 || numericContact > contactCount
        error('mh_oss:InvalidBoundary', ...
            'Source %s contact %g is outside 1..%d.', ...
            sourceId, numericContact, contactCount);
    end
    return;
end
if (ischar(raw) && isrow(raw)) || (isstring(raw) && isscalar(raw))
    token = strtrim(char(raw));
    if strcmpi(token, 'case')
        isCase = true;
        return;
    end
end
error('mh_oss:InvalidBoundary', ...
    'Source %s contacts must be positive local integers or case.', sourceId);
end

function value = polarity_sign(polarity)
if strcmp(polarity, 'cathode')
    value = -1;
else
    value = 1;
end
end
