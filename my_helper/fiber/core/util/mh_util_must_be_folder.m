function mh_util_must_be_folder(path, description, errorId)
% Raise a consistent error when a required folder is missing.

if nargin < 3 || strlength(string(errorId)) == 0
    errorId = 'mh_util_must_be_folder:MissingFolder';
end
if ~isfolder(path)
    error(errorId, 'Missing %s: %s', description, path);
end
end
