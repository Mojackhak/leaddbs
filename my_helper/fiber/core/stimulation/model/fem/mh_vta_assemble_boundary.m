function boundary = mh_vta_assemble_boundary(sources, activeidx, controlMode)
% Assemble deterministic SimBio boundary groups for a continuous source set.

mode = normalize_text(controlMode, 'InvalidControlMode');
if ~ismember(mode, {'voltage', 'current'})
    error('mh_vta_assemble_boundary:InvalidControlMode', ...
        'Control mode must be voltage or current.');
end
if ~isstruct(sources) || isempty(sources)
    error('mh_vta_assemble_boundary:InvalidSources', ...
        'Sources must be a nonempty struct array.');
end
if ~isstruct(activeidx) || ~isfield(activeidx(1), 'con')
    error('mh_vta_assemble_boundary:InvalidActiveIndex', ...
        'Active contact indices must contain a con field.');
end

[sourceIds, sourceOrder] = sorted_source_ids(sources);
if numel(unique(sourceIds)) ~= numel(sourceIds)
    error('mh_vta_assemble_boundary:DuplicateSourceId', ...
        'Source identifiers must be unique within a continuous group.');
end

boundary = struct( ...
    'node_indices', zeros(0, 1), ...
    'values_and_groups', zeros(0, 2), ...
    'unipolar', false, ...
    'constvol', strcmp(mode, 'voltage'), ...
    'source_groups', empty_source_groups());
usedContacts = zeros(0, 1);
groupIndex = 0;

for sortedIndex = 1:numel(sourceOrder)
    sourceIndex = sourceOrder(sortedIndex);
    source = sources(sourceIndex);
    validate_source_mode(source, mode, sourceIds{sortedIndex});
    amplitude = source_amplitude(source, sourceIds{sortedIndex});
    contacts = validate_and_sort_contacts(source, sourceIds{sortedIndex});
    scale = mode_scale(mode);

    for contactIndex = 1:numel(contacts)
        contact = contacts(contactIndex);
        if is_case_contact(contact.contact)
            boundary.unipolar = true;
            continue;
        end

        contactNumber = contact.contact;
        if ismember(contactNumber, usedContacts)
            error('mh_vta_assemble_boundary:DuplicateContact', ...
                'Contact %d is used by more than one continuous source.', ...
                contactNumber);
        end
        usedContacts(end + 1, 1) = contactNumber; %#ok<AGROW>
        nodes = active_contact_nodes(activeidx, contactNumber);
        signedValue = amplitude * scale * contact.fraction;
        if strcmp(contact.polarity, 'cathode')
            signedValue = -signedValue;
        end

        groupIndex = groupIndex + 1;
        boundary.node_indices = [boundary.node_indices; nodes];
        boundary.values_and_groups = [boundary.values_and_groups; ...
            repmat([signedValue, groupIndex], numel(nodes), 1)];
        boundary.source_groups(end + 1) = struct( ... %#ok<AGROW>
            'source_index', sourceIndex, ...
            'source_id', sourceIds{sortedIndex}, ...
            'contact', contactNumber, ...
            'group_index', groupIndex, ...
            'signed_value', signedValue, ...
            'node_count', numel(nodes));
    end
end

if isempty(boundary.node_indices)
    error('mh_vta_assemble_boundary:MissingElectrodeContact', ...
        'At least one non-case contact is required.');
end
end

function groups = empty_source_groups()
groups = repmat(struct( ...
    'source_index', [], ...
    'source_id', '', ...
    'contact', [], ...
    'group_index', [], ...
    'signed_value', [], ...
    'node_count', []), 1, 0);
end

function [sourceIds, order] = sorted_source_ids(sources)
sourceIds = cell(1, numel(sources));
for index = 1:numel(sources)
    if ~isfield(sources(index), 'source_id')
        error('mh_vta_assemble_boundary:MissingSourceId', ...
            'Every source must define source_id.');
    end
    sourceIds{index} = normalize_text(sources(index).source_id, 'InvalidSourceId');
    if isempty(sourceIds{index})
        error('mh_vta_assemble_boundary:InvalidSourceId', ...
            'Source identifiers must be nonempty text.');
    end
end
[sourceIds, order] = sort(sourceIds);
end

function validate_source_mode(source, expectedMode, sourceId)
if isfield(source, 'control_mode')
    sourceMode = normalize_text(source.control_mode, 'InvalidControlMode');
elseif isfield(source, 'controlMode')
    sourceMode = normalize_text(source.controlMode, 'InvalidControlMode');
else
    error('mh_vta_assemble_boundary:MissingControlMode', ...
        'Source %s does not define control_mode.', sourceId);
end
if ~strcmp(sourceMode, expectedMode)
    error('mh_vta_assemble_boundary:MixedControlMode', ...
        'All sources must use the requested %s control mode.', expectedMode);
end

if isfield(source, 'unit')
    unit = normalize_text(source.unit, 'InvalidUnit');
    if (strcmp(expectedMode, 'voltage') && ~strcmpi(unit, 'v')) || ...
            (strcmp(expectedMode, 'current') && ~strcmpi(unit, 'ma'))
        error('mh_vta_assemble_boundary:InvalidUnit', ...
            'Source %s unit does not match control mode %s.', sourceId, expectedMode);
    end
end
end

function amplitude = source_amplitude(source, sourceId)
if isfield(source, 'amplitude')
    amplitude = source.amplitude;
elseif isfield(source, 'amp')
    amplitude = source.amp;
else
    error('mh_vta_assemble_boundary:MissingAmplitude', ...
        'Source %s does not define amplitude.', sourceId);
end
if ~isnumeric(amplitude) || ~isscalar(amplitude) || ...
        ~isfinite(amplitude) || amplitude <= 0
    error('mh_vta_assemble_boundary:InvalidAmplitude', ...
        'Source %s amplitude must be a positive finite scalar.', sourceId);
end
end

function contacts = validate_and_sort_contacts(source, sourceId)
if ~isfield(source, 'contacts') || ~isstruct(source.contacts) || ...
        isempty(source.contacts)
    error('mh_vta_assemble_boundary:InvalidContacts', ...
        'Source %s must define a nonempty contact array.', sourceId);
end
contacts = source.contacts;
sortKeys = zeros(1, numel(contacts));
caseCount = 0;

for index = 1:numel(contacts)
    requiredFields = {'contact', 'polarity', 'fraction'};
    if ~all(isfield(contacts(index), requiredFields))
        error('mh_vta_assemble_boundary:InvalidContact', ...
            'Every contact must define contact, polarity, and fraction.');
    end
    polarity = normalize_text(contacts(index).polarity, 'InvalidPolarity');
    if ~ismember(polarity, {'cathode', 'anode'})
        error('mh_vta_assemble_boundary:InvalidPolarity', ...
            'Contact polarity must be cathode or anode.');
    end
    contacts(index).polarity = polarity;
    fraction = contacts(index).fraction;
    if ~isnumeric(fraction) || ~isscalar(fraction) || ...
            ~isfinite(fraction) || fraction <= 0 || fraction > 1
        error('mh_vta_assemble_boundary:InvalidContactFraction', ...
            'Contact fractions must be finite values in (0, 1].');
    end
    if is_case_contact(contacts(index).contact)
        caseCount = caseCount + 1;
        contacts(index).contact = 'case';
        sortKeys(index) = inf;
    else
        contactNumber = contacts(index).contact;
        if ~isnumeric(contactNumber) || ~isscalar(contactNumber) || ...
                ~isfinite(contactNumber) || contactNumber < 1 || ...
                contactNumber ~= fix(contactNumber)
            error('mh_vta_assemble_boundary:InvalidContact', ...
                'Electrode contacts must be positive integer indices.');
        end
        sortKeys(index) = contactNumber;
    end
end

if caseCount > 1
    error('mh_vta_assemble_boundary:DuplicateContact', ...
        'Source %s defines case more than once.', sourceId);
end
numericKeys = sortKeys(isfinite(sortKeys));
if numel(unique(numericKeys)) ~= numel(numericKeys)
    error('mh_vta_assemble_boundary:DuplicateContact', ...
        'Source %s reuses an electrode contact.', sourceId);
end
validate_sign_fraction(contacts, 'cathode', sourceId);
validate_sign_fraction(contacts, 'anode', sourceId);
[~, order] = sort(sortKeys);
contacts = contacts(order);
end

function validate_sign_fraction(contacts, polarity, sourceId)
matching = strcmp({contacts.polarity}, polarity);
if ~any(matching)
    error('mh_vta_assemble_boundary:MissingPolarity', ...
        'Source %s must define at least one %s contact.', sourceId, polarity);
end
total = sum([contacts(matching).fraction]);
if abs(total - 1) > 1e-9
    error('mh_vta_assemble_boundary:InvalidContactFraction', ...
        'Source %s %s fractions must sum to 1.', sourceId, polarity);
end
end

function nodes = active_contact_nodes(activeidx, contactNumber)
connections = activeidx(1).con;
if contactNumber > numel(connections) || ...
        ~isfield(connections(contactNumber), 'ix') || ...
        isempty(connections(contactNumber).ix)
    error('mh_vta_assemble_boundary:MissingActiveNodes', ...
        'Active nodes are missing for contact %d.', contactNumber);
end
nodes = connections(contactNumber).ix(:);
if ~isnumeric(nodes) || any(~isfinite(nodes)) || any(nodes < 1) || ...
        any(nodes ~= fix(nodes))
    error('mh_vta_assemble_boundary:InvalidActiveNodes', ...
        'Active nodes for contact %d must be positive integer indices.', ...
        contactNumber);
end
end

function scale = mode_scale(mode)
if strcmp(mode, 'current')
    scale = 1e-3;
else
    scale = 1;
end
end

function result = is_case_contact(value)
result = (ischar(value) || (isstring(value) && isscalar(value))) && ...
    strcmpi(strtrim(char(value)), 'case');
end

function value = normalize_text(value, errorSuffix)
if ~(ischar(value) || (isstring(value) && isscalar(value)))
    error(['mh_vta_assemble_boundary:', errorSuffix], ...
        'Expected a scalar text value.');
end
value = lower(strtrim(char(value)));
end
