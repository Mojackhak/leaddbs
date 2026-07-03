function value = mh_fiber_env_double(name, defaultValue, minValue, errorId)
% Read a scalar numeric environment variable with a default value.

if nargin < 3 || isempty(minValue)
    minValue = -inf;
end
if nargin < 4 || isempty(errorId)
    errorId = 'mh_fiber_env_double:InvalidEnvNumber';
end

rawValue = strtrim(string(getenv(name)));
if rawValue == ""
    value = defaultValue;
    return;
end

value = str2double(rawValue);
if isnan(value) || ~isscalar(value) || value < minValue
    error(errorId, 'Invalid numeric value for %s: %s', name, rawValue);
end
end
