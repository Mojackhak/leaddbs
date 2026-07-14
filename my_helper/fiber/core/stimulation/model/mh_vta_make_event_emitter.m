function emit = mh_vta_make_event_emitter(runId, subjectId)
% Create a stateful stdout emitter for contiguous vta_event_v1 events.

runId = require_scalar_text(runId, 'runId');
subjectId = require_scalar_text(subjectId, 'subjectId');
sequence = 0;
emit = @emit_event;

    function emit_event(eventType, fields)
        eventType = require_scalar_text(eventType, 'eventType');
        supportedTypes = [ ...
            "subject_ready", "task_started", "stage_timing", ...
            "task_outcome", "subject_summary"];
        if ~ismember(string(eventType), supportedTypes)
            error('mh_vta:UnsupportedEventType', ...
                'Unsupported vta_event_v1 event type: %s.', eventType);
        end
        if nargin < 2 || isempty(fields)
            fields = struct();
        end
        if ~isstruct(fields) || ~isscalar(fields)
            error('mh_vta:InvalidEventFields', ...
                'Event fields must be a scalar struct.');
        end

        commonFields = { ...
            'schema_version', 'event_type', 'sequence', ...
            'run_id', 'subject_id'};
        if any(ismember(fieldnames(fields), commonFields))
            error('mh_vta:ReservedEventField', ...
                'Event fields cannot override vta_event_v1 common fields.');
        end

        sequence = sequence + 1;
        payload = struct( ...
            'schema_version', 'vta_event_v1', ...
            'event_type', eventType, ...
            'sequence', sequence, ...
            'run_id', runId, ...
            'subject_id', subjectId);
        names = fieldnames(fields);
        for fieldIndex = 1:numel(names)
            payload.(names{fieldIndex}) = fields.(names{fieldIndex});
        end
        fprintf('MH_VTA_EVENT %s\n', jsonencode(payload));
    end
end

function value = require_scalar_text(value, label)
if ~(ischar(value) && isrow(value)) && ...
        ~(isstring(value) && isscalar(value))
    error('mh_vta:InvalidEventIdentity', ...
        '%s must be nonempty scalar text.', label);
end
text = string(value);
if ~isscalar(text) || ismissing(text) || strlength(text) == 0
    error('mh_vta:InvalidEventIdentity', ...
        '%s must be nonempty scalar text.', label);
end
value = char(text);
end
