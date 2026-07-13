function status = mh_vta_derive_canonical_group_peak(task)
% Derive an alternating group peak from completed source-level E-fields.

nativeLeaf = char(string(task.output_leaves.native));
mniLeaf = char(string(task.output_leaves.MNI152NLin2009bAsym));
nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
mniEfield = fullfile(mniLeaf, 'efield.nii.gz');
actions = mh_vta_resolve_output_actions(task);

if actions.solve_native_efield
    alternatingRoot = fileparts(fileparts(nativeLeaf));
    sourcePaths = cell(1, numel(task.sources));
    for sourceIndex = 1:numel(task.sources)
        sourcePaths{sourceIndex} = fullfile(alternatingRoot, 'sources', ...
            ['source-', char(string(task.sources(sourceIndex).source_id))], ...
            'efield.nii.gz');
        if ~isfile(sourcePaths{sourceIndex})
            error('mh_vta:MissingGroupPeakDependency', ...
                'Alternating source E-field is missing: %s', ...
                sourcePaths{sourceIndex});
        end
    end
    mh_vta_publish_atomic(nativeEfield, @(temporaryPath) ...
        mh_vta_compose_group_peak(sourcePaths, temporaryPath));
end

write_requested_thresholds(nativeEfield, nativeLeaf, ...
    task.model.thresholds_v_per_m, actions.native_threshold_names);

if actions.transform_mni_efield
    require_file(nativeEfield, 'native group-peak E-field');
    options = ea_getptopts(char(string(task.subject_dir)), struct());
    options.subj.recon.recon = char(string(task.reconstruction_path));
    mniReference = fullfile(ea_space(options), 't1.nii');
    mh_vta_publish_atomic(mniEfield, @(temporaryPath) ...
        mh_vta_transform_efield_to_mni(nativeEfield, options, ...
            mniReference, temporaryPath));
end

write_requested_thresholds(mniEfield, mniLeaf, ...
    task.model.thresholds_v_per_m, actions.mni_threshold_names);

status = struct( ...
    'task_id', task.task_id, ...
    'execution', 'derived', ...
    'native_efield', nativeEfield, ...
    'mni_efield', mniEfield);
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
