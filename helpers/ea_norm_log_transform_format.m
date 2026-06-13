function format = ea_norm_log_transform_format(json)
% Resolve the transform format recorded in a normalization method log.

format = '';

if isfield(json, 'transform') && isstruct(json.transform) && ...
        isfield(json.transform, 'format') && ~isempty(json.transform.format)
    format = lower(json.transform.format);
    return;
end

if isfield(json, 'method') && ~isempty(json.method)
    format = ea_norm_method_transform_format(json.method);
end
