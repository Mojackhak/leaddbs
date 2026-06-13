function ea_norm_refine_cleanup_current(options)
% Remove existing transforms for the current subject/template transform base.

forwardBase = options.subj.norm.transform.forwardBaseName;
inverseBase = options.subj.norm.transform.inverseBaseName;

suffixes = {
    'ants.nii.gz'
    'ants.mat'
    'fnirt.nii.gz'
    'fnirt.nii'
    'spm.nii'
};

for suffixIndex = 1:numel(suffixes)
    ea_delete({[forwardBase, suffixes{suffixIndex}]; [inverseBase, suffixes{suffixIndex}]});
end

transformDir = fileparts(forwardBase);
ea_delete(fullfile(transformDir, 'antsout*'));
