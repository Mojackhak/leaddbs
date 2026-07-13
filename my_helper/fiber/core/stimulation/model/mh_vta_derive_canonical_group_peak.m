function status = mh_vta_derive_canonical_group_peak(task)
% Derive an alternating group peak from completed source-level E-fields.

nativeLeaf = char(string(task.output_leaves.native));
mniLeaf = char(string(task.output_leaves.MNI152NLin2009bAsym));
alternatingRoot = fileparts(fileparts(nativeLeaf));
sourcePaths = cell(1, numel(task.sources));
for sourceIndex = 1:numel(task.sources)
    sourcePaths{sourceIndex} = fullfile(alternatingRoot, 'sources', ...
        ['source-', char(string(task.sources(sourceIndex).source_id))], ...
        'efield.nii.gz');
    if ~isfile(sourcePaths{sourceIndex})
        error('mh_vta:MissingGroupPeakDependency', ...
            'Alternating source E-field is missing: %s', sourcePaths{sourceIndex});
    end
end

nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
mniEfield = fullfile(mniLeaf, 'efield.nii.gz');
mh_vta_compose_group_peak(sourcePaths, nativeEfield);
write_thresholds(nativeEfield, nativeLeaf, task.model.thresholds_v_per_m);

options = ea_getptopts(char(string(task.subject_dir)), struct());
options.subj.recon.recon = char(string(task.reconstruction_path));
mniReference = fullfile(ea_space(options), 't1.nii');
mh_vta_transform_efield_to_mni(nativeEfield, options, mniReference, mniEfield);
write_thresholds(mniEfield, mniLeaf, task.model.thresholds_v_per_m);

status = struct( ...
    'task_id', task.task_id, ...
    'execution', 'derived', ...
    'native_efield', nativeEfield, ...
    'mni_efield', mniEfield);
end

function write_thresholds(efieldPath, leaf, thresholds)
for threshold = double(thresholds(:)')
    token = strrep(sprintf('%.2f', threshold / 1000), '.', 'p');
    output = fullfile(leaf, sprintf( ...
        'vta_threshold-%sVpermm.nii.gz', token));
    mh_vta_threshold_efield(efieldPath, threshold, output);
end
end
