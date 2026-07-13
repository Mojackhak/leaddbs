function [stimSpecs, executionKind] = mh_vta_expand_delivery_group(group, backendEntry)
% Expand one same-frequency delivery group into physical stimulation states.

if ~isstruct(group) || ~isscalar(group) || ...
        ~isfield(group, 'delivery_mode') || ~isfield(group, 'sources') || ...
        isempty(group.sources)
    error('mh_vta_expand_delivery_group:InvalidGroup', ...
        'Delivery group must contain delivery_mode and nonempty sources.');
end
mode = lower(char(string(group.delivery_mode)));
sources = group.sources;
frequencies = [sources.frequency];
if any(~isfinite(frequencies)) || any(frequencies <= 0) || ...
        any(frequencies ~= frequencies(1))
    error('mh_vta_expand_delivery_group:MixedFrequency', ...
        'All sources in one delivery group must have the same positive frequency.');
end

controlModes = lower(string({sources.controlMode}));
if any(~ismember(controlModes, ["voltage", "current"]))
    error('mh_vta_expand_delivery_group:InvalidControlMode', ...
        'Sources must use voltage or current control.');
end
require_backend_modes(backendEntry, controlModes);

switch mode
    case 'continuous'
        if numel(sources) > 1
            require_joint_backend(backendEntry, controlModes);
        end
        stimSpecs = struct( ...
            'delivery_mode', 'continuous', ...
            'source_index', 0, ...
            'sources', sources);
        executionKind = 'joint';
    case 'alternating'
        if numel(sources) < 2
            error('mh_vta_expand_delivery_group:InvalidAlternatingGroup', ...
                'Alternating delivery requires at least two sources.');
        end
        template = struct( ...
            'delivery_mode', 'alternating', ...
            'source_index', 0, ...
            'sources', sources(1));
        stimSpecs = repmat(template, numel(sources), 1);
        for sourceIndex = 1:numel(sources)
            stimSpecs(sourceIndex).source_index = sourceIndex;
            stimSpecs(sourceIndex).sources = sources(sourceIndex);
        end
        executionKind = 'independent';
    otherwise
        error('mh_vta_expand_delivery_group:InvalidDeliveryMode', ...
            'Unsupported delivery mode: %s', mode);
end
end

function require_backend_modes(entry, modes)
if any(modes == "voltage") && ...
        (~isfield(entry, 'supportsVoltage') || ~logical(entry.supportsVoltage))
    unsupported(entry, 'voltage');
end
if any(modes == "current") && ...
        (~isfield(entry, 'supportsCurrent') || ~logical(entry.supportsCurrent))
    unsupported(entry, 'current');
end
end

function require_joint_backend(entry, modes)
if numel(unique(modes)) > 1
    unsupported(entry, 'joint mixed voltage/current');
end
if modes(1) == "voltage" && ...
        (~isfield(entry, 'supportsJointVoltage') || ~logical(entry.supportsJointVoltage))
    unsupported(entry, 'joint voltage');
end
if modes(1) == "current" && ...
        (~isfield(entry, 'supportsJointCurrent') || ~logical(entry.supportsJointCurrent))
    unsupported(entry, 'joint current');
end
end

function unsupported(entry, capability)
key = '<unknown>';
if isfield(entry, 'key')
    key = char(string(entry.key));
end
error('mh_vta_expand_delivery_group:UnsupportedBackendCapability', ...
    'VTA backend %s does not support %s stimulation.', key, capability);
end
