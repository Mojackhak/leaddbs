function [headmodel, state, cacheStatus, key] = ...
        mh_vta_get_canonical_headmodel(task, context, S, runtime, stimulationLabel)
% Build/load and process-cache one validated canonical head model.

if nargin < 4 || isempty(runtime)
    runtime = mh_vta_create_subject_runtime(task.subject_id);
end
sideIndex = context.side_index;
path = mh_vta_canonical_headmodel_path( ...
    task.subject_dir, task.subject_id, sideIndex);
trajectory = double(context.trajectory{sideIndex});
baseKey = mh_vta_runtime_cache_key('headmodel', { ...
    context.subject_context_key, ...
    mh_vta_canonical_path(path), ...
    char(string(task.model.atlas_set)), ...
    double(task.model.gray_matter_s_per_m), ...
    double(task.model.white_matter_s_per_m), ...
    'canonical_mask_surface_v1', ...
    'simbio_onesolve_canonical_v1', ...
    char(string(task.electrode_model)), ...
    double(task.reconstruction_lead_id), ...
    trajectory, ...
    context.patient_gm_mask_signature});

pathKey = mh_vta_canonical_path(path);
[registeredKey, registered] = mh_vta_runtime_cache_lookup( ...
    runtime, 'headmodel_path_key', pathKey);
if registered && ~strcmp(registeredKey, baseKey)
    error('mh_vta:ConflictingCanonicalHeadmodelContext', ...
        'Canonical headmodel path has incompatible runtime inputs: %s', path);
end

[cached, hit] = mh_vta_runtime_cache_lookup(runtime, 'headmodel', baseKey);
currentSignature = mh_vta_file_signature(path);
if hit && isequal(cached.file_signature, currentSignature)
    headmodel = cached.headmodel;
    key = instance_key(baseKey, currentSignature);
    state = 'reused';
    cacheStatus = 'hit';
    return;
end
if hit
    remove(runtime.caches.headmodel, baseKey);
end

[~, state, headmodel] = mh_vta_prepare_canonical_headmodel( ...
    S, sideIndex, context.options, stimulationLabel);
currentSignature = mh_vta_file_signature(path);
entry = struct('headmodel', headmodel, ...
    'file_signature', {currentSignature});
mh_vta_runtime_cache_store(runtime, 'headmodel', baseKey, entry);
mh_vta_runtime_cache_store(runtime, 'headmodel_path_key', pathKey, baseKey);
key = instance_key(baseKey, currentSignature);
cacheStatus = 'miss';
end

function key = instance_key(baseKey, signature)
key = mh_vta_runtime_cache_key( ...
    'validated_headmodel_instance', {baseKey, signature});
end
