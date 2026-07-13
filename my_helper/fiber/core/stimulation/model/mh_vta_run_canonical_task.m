function status = mh_vta_run_canonical_task(taskJsonPath)
% Read and validate one canonical VTA task JSON file.

path = string(taskJsonPath);
if ~isscalar(path) || ismissing(path) || strlength(path) == 0 || ~isfile(path)
    error('mh_vta:InvalidCanonicalTaskPath', ...
        'Canonical task JSON path must name an existing file.');
end

try
    task = jsondecode(fileread(path));
catch ME
    wrapped = MException('mh_vta:InvalidCanonicalTaskJson', ...
        'Could not decode canonical task JSON: %s', path);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end

status = mh_vta_validate_canonical_task(task);
end
