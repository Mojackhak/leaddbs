function ea_apply_normalization(options)
% Wrapper to apply normalization to the unnormalized files.
% __________________________________________________________________________________
% Copyright (C) 2014 Charite University Medicine Berlin, Movement Disorders Unit
% Andreas Horn

if isfield(options, 'normalize') && isfield(options.normalize, 'deferApply') && options.normalize.deferApply
    return;
end

json = loadjson(options.subj.norm.log.method);

if ea_norm_log_uses_ants_transform(json)
    if contains(json.method, 'SPM')
        % Convert legacy SPM fields if the ANTs field has not been written yet.
        ea_convert_spm_warps(options.subj);
    end
    ea_ants_apply_transforms(options);
elseif contains(json.method, 'FNIRT')
    ea_fsl_apply_normalization(options);
end
