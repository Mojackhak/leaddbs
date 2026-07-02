function value = mh_fiber_getenv_default(name, defaultValue)
% Read an environment variable and return a character default when empty.

rawValue = string(getenv(name));
if strlength(rawValue) == 0
    value = defaultValue;
else
    value = char(rawValue);
end
