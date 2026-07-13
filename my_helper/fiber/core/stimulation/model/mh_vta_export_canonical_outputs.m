function status = mh_vta_export_canonical_outputs(task, options, sideIndex, ...
        mesh, gradient, activeNodeIndices, nativeAnchorPath, headmodelState)
% Publish canonical native/MNI E-fields and thresholded VTAs.

nativeLeaf = char(string(task.output_leaves.native));
mniLeaf = char(string(task.output_leaves.MNI152NLin2009bAsym));
nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
mniEfield = fullfile(mniLeaf, 'efield.nii.gz');
actions = mh_vta_resolve_output_actions(task);

if actions.solve_native_efield
    fieldValues = sqrt(sum(double(gradient).^2, 2));
    meshPointsMm = tetrahedron_midpoints_mm(mesh);
    [~, trajectory] = ea_load_reconstruction(options);
    [meshPointsMm, fieldValues] = ...
        mh_vta_remove_electrode_export_samples(mesh, meshPointsMm, ...
            fieldValues, trajectory, sideIndex, options.elspec);
    mh_vta_publish_atomic(nativeEfield, @(temporaryPath) ...
        mh_vta_export_common_grid(meshPointsMm, fieldValues, ...
            nativeAnchorPath, temporaryPath));
end

write_requested_thresholds(nativeEfield, nativeLeaf, ...
    task.model.thresholds_v_per_m, actions.native_threshold_names);

if actions.transform_mni_efield
    require_file(nativeEfield, 'native E-field');
    [transformOptions, mniReference] = transform_context(task);
    mh_vta_publish_atomic(mniEfield, @(temporaryPath) ...
        mh_vta_transform_efield_to_mni(nativeEfield, transformOptions, ...
            mniReference, temporaryPath));
end

write_requested_thresholds(mniEfield, mniLeaf, ...
    task.model.thresholds_v_per_m, actions.mni_threshold_names);

status = struct( ...
    'task_id', task.task_id, ...
    'execution', 'solve', ...
    'headmodel_state', headmodelState, ...
    'native_efield', nativeEfield, ...
    'mni_efield', mniEfield);
end

function [options, mniReference] = transform_context(task)
options = ea_getptopts(char(string(task.subject_dir)), struct());
options.subj.recon.recon = char(string(task.reconstruction_path));
mniReference = fullfile(ea_space(options), 't1.nii');
end

function points = tetrahedron_midpoints_mm(mesh)
points = mean(cat(3, ...
    mesh.pnt(mesh.tet(:, 1), :), ...
    mesh.pnt(mesh.tet(:, 2), :), ...
    mesh.pnt(mesh.tet(:, 3), :), ...
    mesh.pnt(mesh.tet(:, 4), :)), 3);
if isfield(mesh, 'unit') && strcmpi(mesh.unit, 'm')
    points = points * 1000;
end
end

function write_requested_thresholds(efieldPath, leaf, thresholds, requestedNames)
if isempty(requestedNames)
    return;
end
require_file(efieldPath, 'threshold source E-field');
for threshold = double(thresholds(:)')
    token = strrep(sprintf('%.2f', threshold / 1000), '.', 'p');
    name = "vta_threshold-" + token + "Vpermm.nii.gz";
    if ~any(requestedNames == name)
        continue;
    end
    output = fullfile(leaf, char(name));
    mh_vta_publish_atomic(output, @(temporaryPath) ...
        mh_vta_threshold_efield(efieldPath, threshold, temporaryPath));
end
end

function require_file(path, label)
if ~isfile(path)
    error('mh_vta:MissingCanonicalDependency', ...
        'Missing %s: %s', label, path);
end
end
