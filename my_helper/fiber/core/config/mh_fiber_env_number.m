function value = mh_fiber_env_number(name, defaultValue, errorId)
% Read a positive integer environment variable with a default value.

if nargin < 3 || isempty(errorId)
    errorId = 'mh_fiber_env_number:InvalidEnvNumber';
end

rawValue = strtrim(string(getenv(name)));
if rawValue == ""
    value = defaultValue;
    return;
end

value = str2double(rawValue);
if isnan(value) || value < 1 || value ~= fix(value)
    error(errorId, 'Invalid positive integer for %s: %s', name, rawValue);
end
