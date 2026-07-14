function path = mh_vta_canonical_path(value)
% Resolve one nonempty path without requiring the target to exist.

if ~(ischar(value) || isstring(value) && isscalar(value)) || ...
        ismissing(string(value)) || strlength(string(value)) == 0
    error('mh_vta:InvalidCanonicalPath', ...
        'Canonical path input must be nonempty scalar text.');
end
file = javaObject('java.io.File', char(string(value)));
path = char(file.getCanonicalPath());
end
