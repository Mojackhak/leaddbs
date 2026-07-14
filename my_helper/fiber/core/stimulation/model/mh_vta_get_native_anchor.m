function [anchor, cacheStatus, key] = mh_vta_get_native_anchor(path, runtime)
% Load one native anchor header with process-local exact-file reuse.

if nargin < 2 || isempty(runtime)
    runtime = mh_vta_create_subject_runtime('');
end
signature = mh_vta_file_signature(path);
key = mh_vta_runtime_cache_key('native_anchor', signature);
[anchor, hit] = mh_vta_runtime_cache_lookup(runtime, 'native_anchor', key);
if hit
    cacheStatus = 'hit';
    return;
end
if ~isfile(char(string(path)))
    error('mh_vta_export_common_grid:MissingAnchor', ...
        'Native anchor NIfTI does not exist: %s', char(string(path)));
end
anchor = ea_load_nii(char(string(path)));
if isfield(anchor, 'img')
    anchor.img = [];
end
mh_vta_runtime_cache_store(runtime, 'native_anchor', key, anchor);
cacheStatus = 'miss';
end
