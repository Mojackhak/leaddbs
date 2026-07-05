function hash = mh_fiber_file_sha256(path)
% Return the SHA-256 hash for a local file.

path = char(string(path));
if isempty(path) || ~isfile(path)
    error('mh_fiber_file_sha256:MissingFile', ...
        'File does not exist: %s', path);
end

[status, output] = system(sprintf('shasum -a 256 %s', mh_fiber_shell_quote(path)));
if status ~= 0
    error('mh_fiber_file_sha256:CommandFailed', ...
        'Could not compute SHA-256 for %s:\n%s', path, output);
end

tokens = regexp(strtrim(output), '^([0-9a-fA-F]{64})\s+', 'tokens', 'once');
if isempty(tokens)
    error('mh_fiber_file_sha256:ParseFailed', ...
        'Could not parse SHA-256 output for %s:\n%s', path, output);
end

hash = lower(tokens{1});
end
