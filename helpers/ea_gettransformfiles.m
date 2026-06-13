function transformfiles=ea_gettransformfiles(options)

try
    json = loadjson(options.subj.norm.log.method);
catch
    % Lead-Connectome mode: Use SPM deformation field (BIDS: normalization/transformations)
    directory = [options.root, options.patientname, filesep];
    normDir = ea_connectome_normparams_dir(directory);
    transformfiles.forward = fullfile(normDir, 'y_ea_normparams.nii');
    transformfiles.inverse = fullfile(normDir, 'y_ea_inv_normparams.nii');
    return;
end

if isfield(json, 'custom') && json.custom
    % Custom full path of the transformation supplied.
    warpSuffix = '';
else
    transformFormat = ea_norm_log_transform_format(json);
    switch transformFormat
        case 'ants'
            warpSuffix = 'ants.nii.gz';
        case 'ants_affine'
            warpSuffix = 'ants.mat';
        case 'fnirt'
            warpSuffix = get_existing_fnirt_suffix(options);
        otherwise
            warpSuffix = get_legacy_warp_suffix(json, options);
    end
end

transformfiles.forward=[options.subj.norm.transform.forwardBaseName,warpSuffix];
transformfiles.inverse=[options.subj.norm.transform.inverseBaseName,warpSuffix];


function warpSuffix = get_legacy_warp_suffix(json, options)

warpSuffix = 'ants.nii.gz';

if contains(json.method, 'ANTs')
    if isfield(json, 'custom') && json.custom
        % Custom full path of the transformation supplied.
        warpSuffix = '';
    elseif contains(json.method, 'affine')
        % Three-step affine normalization (Schonecker 2009) used
        warpSuffix = 'ants.mat';
    else
        warpSuffix = 'ants.nii.gz';
    end
elseif contains(json.method, 'FNIRT')
    warpSuffix=get_existing_fnirt_suffix(options);
elseif contains(json.method, 'SPM')
    warpSuffix='ants.nii.gz';
elseif contains(json.method, 'EasyReg')
    warpSuffix='ants.nii.gz';
elseif contains(json.method, 'SynthMorph')
    warpSuffix='ants.nii.gz';
end


function warpSuffix = get_existing_fnirt_suffix(options)

if isfile([options.subj.norm.transform.forwardBaseName, 'fnirt.nii.gz']) || ...
        isfile([options.subj.norm.transform.inverseBaseName, 'fnirt.nii.gz'])
    warpSuffix = 'fnirt.nii.gz';
else
    warpSuffix = 'fnirt.nii';
end
