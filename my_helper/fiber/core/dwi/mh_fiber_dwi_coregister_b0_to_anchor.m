function [dwiToAnchor, anchorToDwi, b0OnAnchor, anchorOnB0, faOnAnchor] = mh_fiber_dwi_coregister_b0_to_anchor(paths, anchorAnat, anchorModality, coregMethod, force)
% Coregister a DWI b0 image to the Lead-DBS anchorNative anatomy.

mh_util_make_dir(paths.coregDir);

if use_legacy_ants_outputs(paths, coregMethod)
    [dwiToAnchor, anchorToDwi, b0OnAnchor, anchorOnB0, faOnAnchor] = ...
        ensure_legacy_ants_coregistration(paths, anchorAnat, anchorModality, force);
    return;
end

outputs = ui_style_coreg_outputs(paths, anchorModality, coregMethod);
mh_util_make_dir(outputs.workDir);
move_branch_root_intermediates_to_work(paths, outputs.workDir);

if force || ~isfile(outputs.dwiToAnchor) || ~isfile(outputs.anchorToDwi) || ...
        ~isfile(outputs.b0OnAnchor) || ~isfile(outputs.anchorOnB0)
    switch coregMethod
        case 'SPM'
            run_spm_coregistration_branch(paths, anchorAnat, outputs);
        case 'Hybrid SPM & ANTs'
            run_hybrid_spm_ants_coregistration_branch(paths, anchorAnat, outputs, anchorModality);
        case 'FLIRT BBR'
            try
                run_flirtbbr_coregistration_branch(paths, anchorAnat, outputs);
            catch ME
                warning('mh_fiber_dwi_coregister_b0_to_anchor:FlirtBbrFailed', ...
                    'FLIRT BBR failed for %s: %s. Falling back to ANTs linear registration.', ...
                    paths.patientName, ME.message);
                run_ants_ui_coregistration_branch(paths, anchorAnat, outputs);
            end
        otherwise
            error('Unsupported UI-style DWI coregistration method: %s', coregMethod);
    end
end

dwiToAnchor = outputs.dwiToAnchor;
anchorToDwi = outputs.anchorToDwi;
b0OnAnchor = outputs.b0OnAnchor;
anchorOnB0 = outputs.anchorOnB0;
faOnAnchor = outputs.faOnAnchor;

if ~isfile(dwiToAnchor)
    error('Missing b0-to-anchorNative %s %s transform after registration.', anchorModality, coregMethod);
end
if ~isfile(anchorToDwi)
    error('Missing anchorNative %s-to-b0 %s transform after registration.', anchorModality, coregMethod);
end
if ~isfile(b0OnAnchor)
    error('Missing b0-on-anchorNative %s image after registration.', anchorModality);
end
if ~isfile(anchorOnB0)
    error('Missing anchorNative %s-on-b0 image after registration.', anchorModality);
end
end

function [dwiToAnchor, anchorToDwi, b0OnAnchor, anchorOnB0, faOnAnchor] = ensure_legacy_ants_coregistration(paths, anchorAnat, anchorModality, force)
[~, b0Name] = ea_niifileparts(paths.b0);
[~, anchorName] = ea_niifileparts(anchorAnat);

dwiToAnchorPattern = fullfile(paths.coregDir, [b0Name, '2', anchorName, '_ants*.mat']);
anchorToDwiPattern = fullfile(paths.coregDir, [anchorName, '2', b0Name, '_ants*.mat']);
dwiToAnchor = latest_file(dwiToAnchorPattern);
anchorToDwi = latest_file(anchorToDwiPattern);
b0OnAnchor = fullfile(paths.coregDir, [b0Name, '2', anchorName, '.nii']);
anchorOnB0 = fullfile(paths.coregDir, [anchorName, '2', b0Name, '.nii']);

if force || ~isfile(dwiToAnchor) || ~isfile(anchorToDwi)
    options = struct();
    options.coregmr.method = 'ANTs';
    options.coregb0.addSyN = 0;
    ea_coregimages(options, paths.b0, anchorAnat, b0OnAnchor, {}, 1, [], 1);
    dwiToAnchor = latest_file(dwiToAnchorPattern);
    anchorToDwi = latest_file(anchorToDwiPattern);
end

if ~isfile(dwiToAnchor)
    error('Missing b0-to-anchorNative %s transform after registration.', anchorModality);
end
if ~isfile(anchorToDwi)
    error('Missing anchorNative %s-to-b0 transform after registration.', anchorModality);
end

if force || ~isfile(b0OnAnchor)
    ea_ants_apply_transforms([], paths.b0, b0OnAnchor, 0, anchorAnat, dwiToAnchor, 'Linear');
end
if force || ~isfile(anchorOnB0)
    ea_ants_apply_transforms([], anchorAnat, anchorOnB0, 0, paths.b0, anchorToDwi, 'Linear');
end

faOnAnchor = '';
if isfile(paths.fa)
    faOnAnchor = fullfile(paths.coregDir, [mh_fiber_nii_basename(paths.fa), '2', anchorName, '.nii']);
    if force || ~isfile(faOnAnchor)
        ea_ants_apply_transforms([], paths.fa, faOnAnchor, 0, anchorAnat, dwiToAnchor, 'Linear');
    end
end
end

function tf = use_legacy_ants_outputs(paths, coregMethod)
tf = strcmp(coregMethod, 'ANTs') && strcmp(paths.coregTag, 'dwi_t2');
end

function outputs = ui_style_coreg_outputs(paths, anchorModality, coregMethod)
anchorLabel = anchor_label(anchorModality);
suffix = coregistration_transform_suffix(coregMethod);
outputs = struct();
outputs.dwiToAnchor = fullfile(paths.coregDir, ...
    sprintf('%s_from-b0_to-anchorNative_desc-%s.mat', paths.patientName, suffix));
outputs.anchorToDwi = fullfile(paths.coregDir, ...
    sprintf('%s_from-anchorNative_to-b0_desc-%s.mat', paths.patientName, suffix));
outputs.b0OnAnchor = fullfile(paths.coregDir, ...
    sprintf('%s_b0_on_%s.nii', paths.patientName, anchorLabel));
outputs.anchorOnB0 = fullfile(paths.coregDir, ...
    sprintf('%s_%s_on_b0.nii', paths.patientName, anchorLabel));
outputs.faOnAnchor = fullfile(paths.coregDir, ...
    sprintf('%s_fa_on_%s.nii', paths.patientName, anchorLabel));
outputs.workDir = fullfile(paths.coregDir, 'work');
outputs.spmInitDwiToAnchor = fullfile(paths.coregDir, ...
    sprintf('%s_from-b0_to-anchorNative_desc-spm-init.mat', paths.patientName));
outputs.spmInitAnchorToDwi = fullfile(paths.coregDir, ...
    sprintf('%s_from-anchorNative_to-b0_desc-spm-init.mat', paths.patientName));
end

function run_spm_coregistration_branch(paths, anchorAnat, outputs)
mh_util_make_dir(outputs.workDir);
workB0 = fullfile(outputs.workDir, [paths.patientName, '_work_b0_spm.nii']);
copyfile(paths.b0, workB0, 'f');

options = struct();
options.coregmr.method = 'SPM';
options.coregb0.addSyN = 0;
affineFiles = ea_coregimages(options, workB0, anchorAnat, outputs.b0OnAnchor, {}, 1, [], 1);
copy_transform_file(affineFiles{1}, outputs.dwiToAnchor);
copy_transform_file(affineFiles{2}, outputs.anchorToDwi);

ea_apply_coregistration(paths.b0, anchorAnat, outputs.anchorOnB0, outputs.anchorToDwi, 'linear');
if isfile(paths.fa)
    ea_apply_coregistration(anchorAnat, paths.fa, outputs.faOnAnchor, outputs.dwiToAnchor, 'linear');
end
end

function run_hybrid_spm_ants_coregistration_branch(paths, anchorAnat, outputs, anchorModality)
mh_util_make_dir(outputs.workDir);
anchorLabel = anchor_label(anchorModality);
spmInitB0 = fullfile(outputs.workDir, [paths.patientName, '_b0_spm_init.nii']);
copyfile(paths.b0, spmInitB0, 'f');

spmInitFiles = ea_spm_coreg(struct(), spmInitB0, anchorAnat, 'nmi', 0, {}, 1, 1);
copy_transform_file(spmInitFiles{1}, outputs.spmInitDwiToAnchor);
copy_transform_file(spmInitFiles{2}, outputs.spmInitAnchorToDwi);

options = struct();
options.coregmr.method = 'ANTs';
options.coregb0.addSyN = 0;
antsB0OnAnchor = fullfile(outputs.workDir, ...
    sprintf('%s_b0_on_%s_antswork.nii', paths.patientName, anchorLabel));
antsFiles = ea_coregimages(options, spmInitB0, anchorAnat, antsB0OnAnchor, {}, 1, [], 1);
copy_transform_file(antsFiles{1}, outputs.dwiToAnchor);
copy_transform_file(antsFiles{2}, outputs.anchorToDwi);
copyfile(antsB0OnAnchor, outputs.b0OnAnchor, 'f');

anchorOnSpmInit = fullfile(outputs.workDir, ...
    sprintf('%s_%s_on_spmInitB0.nii', paths.patientName, anchorLabel));
ea_apply_coregistration(spmInitB0, anchorAnat, anchorOnSpmInit, outputs.anchorToDwi, 'linear');
ea_spm_apply_coregistration(paths.b0, anchorOnSpmInit, outputs.anchorOnB0, ...
    outputs.spmInitAnchorToDwi, 1);

if isfile(paths.fa)
    faOnSpmInit = fullfile(outputs.workDir, ...
        sprintf('%s_fa_on_spmInitB0.nii', paths.patientName));
    ea_spm_apply_coregistration(spmInitB0, paths.fa, faOnSpmInit, ...
        outputs.spmInitDwiToAnchor, 1);
    ea_apply_coregistration(anchorAnat, faOnSpmInit, outputs.faOnAnchor, ...
        outputs.dwiToAnchor, 'linear');
end
end

function run_flirtbbr_coregistration_branch(paths, anchorAnat, outputs)
mh_util_make_dir(outputs.workDir);
affineFiles = ea_flirtbbr(anchorAnat, paths.b0, outputs.b0OnAnchor, 1);
copy_transform_file(affineFiles{1}, outputs.dwiToAnchor);
copy_transform_file(affineFiles{2}, outputs.anchorToDwi);

ea_fsl_apply_coregistration(paths.b0, anchorAnat, outputs.anchorOnB0, ...
    outputs.anchorToDwi, 'spline');
if isfile(paths.fa)
    ea_fsl_apply_coregistration(anchorAnat, paths.fa, outputs.faOnAnchor, ...
        outputs.dwiToAnchor, 'spline');
end
end

function run_ants_ui_coregistration_branch(paths, anchorAnat, outputs)
mh_util_make_dir(outputs.workDir);
options = struct();
options.coregmr.method = 'ANTs';
options.coregb0.addSyN = 0;
affineFiles = ea_coregimages(options, paths.b0, anchorAnat, outputs.b0OnAnchor, {}, 1, [], 1);
copy_transform_file(affineFiles{1}, outputs.dwiToAnchor);
copy_transform_file(affineFiles{2}, outputs.anchorToDwi);

ea_ants_apply_transforms([], anchorAnat, outputs.anchorOnB0, 0, ...
    paths.b0, outputs.anchorToDwi, 'Linear');
if isfile(paths.fa)
    ea_ants_apply_transforms([], paths.fa, outputs.faOnAnchor, 0, ...
        anchorAnat, outputs.dwiToAnchor, 'Linear');
end
end

function move_branch_root_intermediates_to_work(paths, workDir)
patterns = { ...
    [paths.patientName, '_work_b0_spm*'], ...
    [paths.patientName, '_b0_spm_init*'], ...
    [paths.patientName, '_b0_on_anchor*_antswork*'], ...
    [paths.patientName, '_anchor*_on_spmInitB0*'], ...
    [paths.patientName, '_fa_on_spmInitB0*'], ...
    [paths.patientName, '_ses-preop_space-anchorNative*2', paths.patientName, '_work_b0_spm*'], ...
    [paths.patientName, '_ses-preop_space-anchorNative*2', paths.patientName, '_b0_spm_init*']};
for i = 1:numel(patterns)
    d = dir(fullfile(paths.coregDir, patterns{i}));
    d = d(~startsWith({d.name}, '._'));
    for j = 1:numel(d)
        source = fullfile(d(j).folder, d(j).name);
        target = fullfile(workDir, d(j).name);
        if ~strcmp(source, target)
            movefile(source, target, 'f');
        end
    end
end
end

function copy_transform_file(source, target)
if isempty(source) || ~isfile(source)
    error('Transform source file does not exist: %s', source);
end
mh_util_make_dir(fileparts(target));
copyfile(source, target, 'f');
end

function suffix = coregistration_transform_suffix(coregMethod)
switch coregMethod
    case 'SPM'
        suffix = 'spm';
    case {'ANTs', 'Hybrid SPM & ANTs'}
        suffix = 'ants';
    case 'FLIRT BBR'
        suffix = 'flirtbbr';
    otherwise
        error('Unsupported CoregistrationMethod for transform suffix: %s', coregMethod);
end
end

function label = anchor_label(anchorModality)
switch anchorModality
    case 'T1w'
        label = 'anchorT1';
    case 'T2w'
        label = 'anchorT2';
    otherwise
        label = ['anchor', anchorModality];
end
end

function path = latest_file(pattern)
d = dir(pattern);
d = d(~startsWith({d.name}, '._'));
if isempty(d)
    path = '';
    return;
end
[~, order] = sort([d.datenum]);
d = d(order);
path = fullfile(d(end).folder, d(end).name);
end
