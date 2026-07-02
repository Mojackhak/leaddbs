function value = mh_fiber_env_flag(name, defaultValue, errorId)
% Read a logical environment variable with a default value.

if nargin < 3 || isempty(errorId)
    errorId = 'mh_fiber_env_flag:InvalidEnvFlag';
end

rawValue = lower(strtrim(string(getenv(name))));
if rawValue == ""
    value = defaultValue;
elseif ismember(rawValue, ["1", "true", "yes", "on"])
    value = true;
elseif ismember(rawValue, ["0", "false", "no", "off"])
    value = false;
else
    error(errorId, 'Invalid logical value for %s: %s', name, rawValue);
end
