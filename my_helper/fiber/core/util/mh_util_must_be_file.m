function mh_util_must_be_file(path, description, errorId)
% Raise a consistent error when a required file is missing.

if nargin < 3 || strlength(string(errorId)) == 0
    errorId = 'mh_util_must_be_file:MissingFile';
end
if ~isfile(path)
    error(errorId, 'Missing %s: %s', description, path);
end
end
