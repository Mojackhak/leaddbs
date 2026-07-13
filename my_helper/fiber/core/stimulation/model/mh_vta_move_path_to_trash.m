function destination = mh_vta_move_path_to_trash(path, varargin)
% Move an existing canonical VTA path to a recoverable filesystem Trash.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('TrashRoot', '', @(value) ischar(value) || isstring(value));
parser.parse(varargin{:});

path = char(string(path));
if ~isfile(path) && ~isfolder(path)
    destination = '';
    return;
end
trashRoot = char(string(parser.Results.TrashRoot));
if isempty(trashRoot)
    trashRoot = default_trash_root(path);
end
if ~isfolder(trashRoot)
    [created, message] = mkdir(trashRoot);
    if ~created
        error('mh_vta:TrashUnavailable', ...
            'Could not create filesystem Trash %s: %s', trashRoot, message);
    end
end

[~, token] = fileparts(tempname(trashRoot));
[~, name, extension] = fileparts(path);
destination = fullfile(trashRoot, sprintf('%s.%s%s', name, token, extension));
[moved, message] = movefile(path, destination);
if ~moved
    error('mh_vta:TrashMoveFailed', ...
        'Could not move %s to Trash: %s', path, message);
end
end

function root = default_trash_root(path)
volume = regexp(path, '^(/Volumes/[^/]+)(?:/|$)', 'tokens', 'once');
if isempty(volume)
    root = fullfile(getenv('HOME'), '.Trash');
    return;
end
[status, uid] = system('id -u');
if status ~= 0 || isempty(strtrim(uid))
    error('mh_vta:TrashUnavailable', ...
        'Could not resolve the current user ID for external-volume Trash.');
end
root = fullfile(volume{1}, '.Trashes', strtrim(uid));
end
