function [context, cacheStatus] = mh_vta_resolve_transform_context(task, runtime)
% Resolve the minimal subject context required for native-to-MNI repair.

if nargin < 2 || isempty(runtime)
    runtime = mh_vta_create_subject_runtime(task.subject_id);
end
key = mh_vta_runtime_cache_key('transform_context', { ...
    mh_vta_canonical_path(task.subject_dir), ...
    mh_vta_canonical_path(task.reconstruction_path)});
[context, hit] = mh_vta_runtime_cache_lookup( ...
    runtime, 'transform_context', key);
if hit
    cacheStatus = 'hit';
    return;
end

subjectDir = char(string(task.subject_dir));
options = ea_getptopts(subjectDir, struct());
options.subj.recon.recon = char(string(task.reconstruction_path));
context = struct( ...
    'options', options, ...
    'mni_reference', fullfile(ea_space(options), 't1.nii'), ...
    'transform_context_key', key);
mh_vta_runtime_cache_store(runtime, 'transform_context', key, context);
cacheStatus = 'miss';
end
