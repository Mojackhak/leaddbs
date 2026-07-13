function actions = mh_vta_resolve_output_actions(task)
% Resolve requested path repairs into FEM, transform, and threshold actions.

nativeNames = requested_names(task, 'native');
mniNames = requested_names(task, 'MNI152NLin2009bAsym');
actions = struct( ...
    'solve_native_efield', any(nativeNames == "efield.nii.gz"), ...
    'native_threshold_names', nativeNames(nativeNames ~= "efield.nii.gz"), ...
    'transform_mni_efield', any(mniNames == "efield.nii.gz"), ...
    'mni_threshold_names', mniNames(mniNames ~= "efield.nii.gz"));
end

function names = requested_names(task, space)
if ~isfield(task.missing_artifacts, space)
    names = strings(0, 1);
    return;
end
names = string(task.missing_artifacts.(space));
names = names(:);
end
