function S = mh_fiber_apply_source_contacts(S, sourceField, source, numContacts)
% Map one canonical contact array into a Lead-DBS stimulation source.

sourceField = char(string(sourceField));
if ~isfield(S, sourceField)
    error('mh_fiber_apply_source_contacts:MissingSourceField', ...
        'Lead-DBS stimulation is missing source field: %s', sourceField);
end
if nargin < 4 || isempty(numContacts)
    numContacts = S.numContacts;
end

S.(sourceField).case.perc = 0;
S.(sourceField).case.pol = 0;
for contactIndex = 1:numContacts
    contactField = ['k', num2str(contactIndex)];
    S.(sourceField).(contactField).perc = 0;
    S.(sourceField).(contactField).pol = 0;
end

for allocationIndex = 1:numel(source.contacts)
    allocation = source.contacts(allocationIndex);
    if isnumeric(allocation.contact)
        contactIndex = double(allocation.contact);
        if ~isscalar(contactIndex) || ~isfinite(contactIndex) || ...
                contactIndex < 1 || contactIndex > numContacts || ...
                contactIndex ~= fix(contactIndex)
            error('mh_fiber_apply_source_contacts:ContactOutOfRange', ...
                'Contact %g is outside electrode contact count %d.', ...
                contactIndex, numContacts);
        end
        targetField = ['k', num2str(contactIndex)];
    elseif strcmpi(char(string(allocation.contact)), 'case')
        targetField = 'case';
    else
        error('mh_fiber_apply_source_contacts:InvalidContact', ...
            'Contact identifiers must be positive integers or case.');
    end

    if strcmp(source.controlMode, 'voltage')
        percentage = 100;
    elseif strcmp(source.controlMode, 'current')
        percentage = 100 * double(allocation.fraction);
    else
        error('mh_fiber_apply_source_contacts:InvalidControlMode', ...
            'Unsupported control mode: %s', source.controlMode);
    end

    switch char(string(allocation.polarity))
        case 'cathode'
            polarityCode = 1;
        case 'anode'
            polarityCode = 2;
        otherwise
            error('mh_fiber_apply_source_contacts:InvalidPolarity', ...
                'Unsupported contact polarity: %s', allocation.polarity);
    end
    S.(sourceField).(targetField).perc = percentage;
    S.(sourceField).(targetField).pol = polarityCode;
end
end
