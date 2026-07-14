function [geometry, cacheStatus, key] = mh_vta_get_export_geometry( ...
        task, mesh, trajectory, sideIndex, elspec, headmodelKey, runtime)
% Prepare and process-cache field-independent FEM export geometry.

if nargin < 7 || isempty(runtime)
    runtime = mh_vta_create_subject_runtime(task.subject_id);
end
if isempty(headmodelKey)
    midpoints = mh_vta_tetrahedron_midpoints_mm(mesh);
    geometry = mh_vta_prepare_electrode_export_geometry( ...
        mesh, midpoints, trajectory, sideIndex, elspec);
    cacheStatus = 'miss';
    key = '';
    return;
end
trajectoryCoordinates = double(trajectory{sideIndex});
key = mh_vta_runtime_cache_key('export_geometry', { ...
    headmodelKey, ...
    mh_vta_canonical_path(task.reconstruction_path), ...
    double(task.reconstruction_lead_id), ...
    char(string(task.electrode_model)), ...
    trajectoryCoordinates, ...
    double(elspec.lead_diameter)});
[geometry, hit] = mh_vta_runtime_cache_lookup( ...
    runtime, 'export_geometry', key);
if hit
    cacheStatus = 'hit';
    return;
end
midpoints = mh_vta_tetrahedron_midpoints_mm(mesh);
geometry = mh_vta_prepare_electrode_export_geometry( ...
    mesh, midpoints, trajectory, sideIndex, elspec);
mh_vta_runtime_cache_store(runtime, 'export_geometry', key, geometry);
cacheStatus = 'miss';
end
