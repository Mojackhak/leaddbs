function mh_fiber_cleanup_temp_dir(path)
% Remove a temporary directory when it still exists.

if ~isempty(path) && isfolder(path)
    rmdir(path, 's');
end
end
