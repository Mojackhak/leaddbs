function [solveUnits, executionKind] = mh_vta_expand_delivery_group(deliveryMode, sources)
% Expand canonical sources into joint or independent FEM solve units.

mode = lower(string(deliveryMode));
if ~isscalar(mode) || ~ismember(mode, ["continuous", "alternating"])
    error('mh_vta_expand_delivery_group:InvalidDeliveryMode', ...
        'Unsupported delivery mode: %s', mode);
end
if ~isstruct(sources) || isempty(sources) || ...
        ~all(isfield(sources, {'frequency_hz', 'control_mode'}))
    error('mh_vta_expand_delivery_group:InvalidSources', ...
        'Sources must be a nonempty canonical source struct array.');
end

frequencies = double([sources.frequency_hz]);
if any(~isfinite(frequencies)) || any(frequencies <= 0) || ...
        any(frequencies ~= frequencies(1))
    error('mh_vta_expand_delivery_group:MixedFrequency', ...
        'All sources in one delivery group must have the same positive frequency.');
end
controlModes = lower(string({sources.control_mode}));
if any(~ismember(controlModes, ["voltage", "current"]))
    error('mh_vta_expand_delivery_group:InvalidControlMode', ...
        'Sources must use voltage or current control.');
end
if numel(unique(controlModes)) ~= 1
    error('mh_vta_expand_delivery_group:MixedControlMode', ...
        'All sources in one delivery group must use one control mode.');
end

switch mode
    case "continuous"
        solveUnits = {sources};
        executionKind = 'joint';
    case "alternating"
        solveUnits = arrayfun(@(source) source, sources, ...
            'UniformOutput', false);
        solveUnits = reshape(solveUnits, [], 1);
        executionKind = 'independent';
end
end
