function result = mh_fiber_register_imported_dwi_batch(varargin)
% Stage imported BIDS DWI files and register b0 to anchorNative anatomy.

p = inputParser;
p.addParameter('StudyRoot', '/Volumes/VAL/STNSNr', @(x) ischar(x) || isstring(x));
p.addParameter('RepoDir', '/Users/mojackhu/Github/leaddbs', @(x) ischar(x) || isstring(x));
p.addParameter('ImportLog', fullfile('/Volumes/VAL/STNSNr', 'derivatives', 'leaddbs', ...
    'import_logs', 'dwi_import_20260701_013240.csv'), @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('AnchorModality', 'T2w', @(x) ischar(x) || isstring(x));
p.addParameter('CoregistrationTag', 'dwi_t2', @(x) ischar(x) || isstring(x));
p.addParameter('CoregistrationMethod', 'ANTs', @(x) ischar(x) || isstring(x));
p.addParameter('AllowT1Fallback', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('RunCoregistration', true, @(x) islogical(x) || isnumeric(x));
p.addParameter('GenerateOptionalDwiQc', true, @(x) islogical(x) || isnumeric(x));
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = p.Results;

opts.StudyRoot = char(string(opts.StudyRoot));
opts.RepoDir = char(string(opts.RepoDir));
opts.ImportLog = char(string(opts.ImportLog));
opts.AnchorModality = normalize_anchor_modality(opts.AnchorModality);
opts.CoregistrationTag = char(string(opts.CoregistrationTag));
opts.CoregistrationMethod = normalize_coregistration_method(opts.CoregistrationMethod);
opts.AllowT1Fallback = logical(opts.AllowT1Fallback);
opts.RunCoregistration = logical(opts.RunCoregistration);
opts.GenerateOptionalDwiQc = logical(opts.GenerateOptionalDwiQc);
opts.Force = logical(opts.Force);

if isempty(opts.CoregistrationTag)
    error('CoregistrationTag must not be empty.');
end

if ~isfolder(opts.StudyRoot)
    error('mh_fiber_register_imported_dwi_batch:MissingStudyRoot', ...
        'Study root does not exist: %s', opts.StudyRoot);
end
if ~isfolder(opts.RepoDir)
    error('mh_fiber_register_imported_dwi_batch:MissingRepoDir', ...
        'Lead-DBS repository does not exist: %s', opts.RepoDir);
end

addpath(genpath(opts.RepoDir));

derivativesRoot = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs');
importLogDir = fullfile(derivativesRoot, 'import_logs');
if ~isfolder(importLogDir)
    mkdir(importLogDir);
end

[subjects, sourceBases] = resolve_subjects(opts);
rows = repmat(empty_status_row(), numel(subjects), 1);

fprintf('Running STN/SNr DWI registration batch for %d subjects.\n', numel(subjects));
for i = 1:numel(subjects)
    subjectId = subjects{i};
    fprintf('\n[%d/%d] %s\n', i, numel(subjects), subjectId);
    rows(i) = register_one_subject(subjectId, sourceBases, opts, derivativesRoot);
end

summary = struct2table(rows, 'AsArray', true);
statusCsv = fullfile(importLogDir, status_filename_from_coreg_tag(opts.CoregistrationTag));
writetable(summary, statusCsv);

result = struct();
result.summary = summary;
result.statusCsv = statusCsv;
result.subjects = subjects;

fprintf('\nDWI registration batch summary written to:\n%s\n', statusCsv);
disp(summary(:, {'subject', 'status', 'message', 'anchor_modality', 'coregistration_method', 'low_resolution_warning'}));

end

function row = register_one_subject(subjectId, sourceBases, opts, derivativesRoot)
row = empty_status_row();
row.subject = subjectId;
row.source_base = lookup_source_base(sourceBases, subjectId);
row.status = 'started';

try
    paths = resolve_subject_paths(subjectId, opts, derivativesRoot);
    row.raw_dwi = paths.rawDwiGz;
    row.staged_dwi = paths.dwi;
    row.b0 = paths.b0;
    row.qc_dir = paths.qcDir;
    row.anchor_modality = opts.AnchorModality;
    row.coregistration_method = opts.CoregistrationMethod;
    row.anchor_anat = resolve_anchor_anat(paths.subjectDir, opts.AnchorModality, opts.AllowT1Fallback);
    row.normalization_forward = resolve_anchor_to_mni_transform(paths.subjectDir, paths.patientName);

    validate_raw_inputs(paths);
    [nVolumes, bvals, bvecCount] = validate_gradients(paths.rawBval, paths.rawBvec, paths.rawDwiGz);
    row.dwi_volumes = nVolumes;
    row.bval_count = numel(bvals);
    row.bvec_count = bvecCount;
    row.b0_count = sum(bvals < 10);

    stage_dwi_derivatives(paths, opts.Force);
    [row.dim_x, row.dim_y, row.dim_z, row.voxel_x, row.voxel_y, row.voxel_z] = ...
        read_dwi_geometry(paths.dwi);
    row.low_resolution_warning = row.voxel_z >= 4;

    extract_b0(paths.dwi, paths.b0, bvals, opts.Force);
    validate_b0_geometry(paths.dwi, paths.b0);

    if opts.GenerateOptionalDwiQc
        [row.fa_status, row.mask_status, paths.fa, paths.faOnAnchor] = generate_optional_dwi_qc(paths);
    else
        row.fa_status = 'skipped';
        row.mask_status = 'skipped';
    end

    if opts.RunCoregistration
        [row.dwi_to_anchor_transform, row.anchor_to_dwi_transform, row.b0_on_anchor, row.anchor_on_b0, paths.faOnAnchor] = ...
            ensure_b0_anchor_coregistration(paths, row.anchor_anat, opts.AnchorModality, ...
            opts.CoregistrationMethod, opts.Force);
        row.forward_transform_exists = isfile(row.dwi_to_anchor_transform);
        row.inverse_transform_exists = isfile(row.anchor_to_dwi_transform);
        write_qc_overlays(paths, row.anchor_anat, row.b0_on_anchor, row.anchor_on_b0, ...
            paths.faOnAnchor, opts.AnchorModality);
    else
        row.dwi_to_anchor_transform = '';
        row.anchor_to_dwi_transform = '';
        row.b0_on_anchor = '';
        row.anchor_on_b0 = '';
        row.forward_transform_exists = false;
        row.inverse_transform_exists = false;
    end

    if opts.RunCoregistration
        row.status = 'registered';
    else
        row.status = 'staged';
    end
    row.message = 'ok';
catch ME
    row.status = 'registration_failed';
    row.message = compact_message(ME.message);
    fprintf(2, 'Subject %s failed: %s\n', subjectId, ME.message);
end

if ~isfolder(row.qc_dir) && strlength(string(row.qc_dir)) > 0
    mkdir(row.qc_dir);
end
if strlength(string(row.qc_dir)) > 0
    write_subject_json(row, fullfile(row.qc_dir, [subjectId, '_dwi_registration_qc.json']));
end

end

function paths = resolve_subject_paths(subjectId, opts, derivativesRoot)
patientName = ['sub-', subjectId];
subjectDir = fullfile(derivativesRoot, patientName);
rawDwiDir = fullfile(opts.StudyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
dwiDir = fullfile(subjectDir, 'preprocessing', 'dwi');
coregDir = fullfile(subjectDir, 'coregistration', opts.CoregistrationTag);
qcDir = fullfile(subjectDir, 'qc', qc_tag_from_coreg_tag(opts.CoregistrationTag));

rawBase = [patientName, '_ses-preop_dwi'];
paths = struct();
paths.subjectId = subjectId;
paths.patientName = patientName;
paths.subjectDir = subjectDir;
paths.rawDwiDir = rawDwiDir;
paths.rawDwiGz = fullfile(rawDwiDir, [rawBase, '.nii.gz']);
paths.rawDwiNii = fullfile(rawDwiDir, [rawBase, '.nii']);
paths.rawJson = fullfile(rawDwiDir, [rawBase, '.json']);
paths.rawBval = fullfile(rawDwiDir, [rawBase, '.bval']);
paths.rawBvec = fullfile(rawDwiDir, [rawBase, '.bvec']);
paths.dwiDir = dwiDir;
paths.coregDir = coregDir;
paths.coregTag = opts.CoregistrationTag;
paths.qcDir = qcDir;
paths.dwi = fullfile(dwiDir, [rawBase, '.nii']);
paths.json = fullfile(dwiDir, [rawBase, '.json']);
paths.bval = fullfile(dwiDir, [rawBase, '.bval']);
paths.bvec = fullfile(dwiDir, [rawBase, '.bvec']);
paths.b0 = fullfile(dwiDir, [rawBase, '_b0.nii']);
paths.fa = fullfile(dwiDir, [rawBase, '_fa.nii']);
paths.faOnAnchor = '';
paths.brainMask = fullfile(dwiDir, 'brainmask.nii');
paths.trackingMask = fullfile(dwiDir, 'trackingmask.nii');
end

function validate_raw_inputs(paths)
if ~isfolder(paths.subjectDir)
    error('Subject derivative directory does not exist: %s', paths.subjectDir);
end
if ~isfile(paths.rawDwiGz) && ~isfile(paths.rawDwiNii)
    error('Raw DWI image not found: %s', paths.rawDwiGz);
end
must_be_file(paths.rawJson, 'raw DWI JSON');
must_be_file(paths.rawBval, 'raw DWI bval');
must_be_file(paths.rawBvec, 'raw DWI bvec');
end

function [nVolumes, bvals, bvecCount] = validate_gradients(bvalPath, bvecPath, dwiPath)
bvals = load_numeric_vector(bvalPath);
bvec = load(bvecPath);
if size(bvec, 1) == 3
    bvecCount = size(bvec, 2);
elseif size(bvec, 2) == 3
    bvecCount = size(bvec, 1);
else
    error('bvec file must be 3 x N or N x 3: %s', bvecPath);
end

dwiInfoPath = dwiPath;
tempNii = '';
if endsWith(dwiPath, '.gz')
    tempDir = tempname;
    mkdir(tempDir);
    gunzip(dwiPath, tempDir);
    [~, base] = fileparts(dwiPath);
    dwiInfoPath = fullfile(tempDir, base);
    tempNii = tempDir;
end

cleanupObj = onCleanup(@() cleanup_temp_dir(tempNii));
V = spm_vol(dwiInfoPath);
nVolumes = numel(V);
if numel(bvals) ~= nVolumes
    error('bval count (%d) does not match DWI volume count (%d).', numel(bvals), nVolumes);
end
if bvecCount ~= nVolumes
    error('bvec count (%d) does not match DWI volume count (%d).', bvecCount, nVolumes);
end
if ~any(bvals < 10)
    error('No b0 volume found with bval < 10.');
end
end

function stage_dwi_derivatives(paths, force)
ensure_dir(paths.dwiDir);
ensure_dir(paths.coregDir);
ensure_dir(paths.qcDir);

if force || ~isfile(paths.dwi)
    if isfile(paths.rawDwiGz)
        gunzip(paths.rawDwiGz, paths.dwiDir);
    else
        copyfile(paths.rawDwiNii, paths.dwi);
    end
end
copy_if_missing(paths.rawJson, paths.json, force);
copy_if_missing(paths.rawBval, paths.bval, force);
copy_if_missing(paths.rawBvec, paths.bvec, force);
end

function [dimX, dimY, dimZ, voxX, voxY, voxZ] = read_dwi_geometry(dwiPath)
V = spm_vol(dwiPath);
dimX = V(1).dim(1);
dimY = V(1).dim(2);
dimZ = V(1).dim(3);
vox = sqrt(sum(V(1).mat(1:3, 1:3).^2, 1));
voxX = vox(1);
voxY = vox(2);
voxZ = vox(3);
end

function extract_b0(dwiPath, b0Path, bvals, force)
if isfile(b0Path) && ~force
    return;
end

idx = find(bvals < 10);
if isempty(idx)
    error('Cannot extract b0 because no bval < 10 was found.');
end

V = spm_vol(dwiPath);
if numel(V) ~= numel(bvals)
    error('Staged DWI volume count no longer matches bval count.');
end

b0 = zeros(V(1).dim, 'double');
for i = 1:numel(idx)
    b0 = b0 + double(spm_read_vols(V(idx(i))));
end
b0 = b0 ./ numel(idx);

Vo = V(idx(1));
Vo.fname = b0Path;
Vo.n = [1, 1];
Vo.dt = [16, 0];
Vo.descrip = sprintf('Mean b0 extracted from %s without header recentering', get_file_name(dwiPath));
if V(1).dim(3) == 1
    write_single_slice_b0(dwiPath, b0Path, b0);
else
    spm_write_vol(Vo, b0);
end
end

function write_single_slice_b0(dwiPath, b0Path, b0)
info = niftiinfo(dwiPath);
info.ImageSize = info.ImageSize(1:3);
info.PixelDimensions = info.PixelDimensions(1:3);
info.Datatype = 'single';
info.BitsPerPixel = 32;
info.Filename = b0Path;
if isfile(b0Path)
    delete(b0Path);
end
niftiwrite(reshape(single(b0), info.ImageSize), b0Path, info, 'Compressed', false);
end

function validate_b0_geometry(dwiPath, b0Path)
Vd = spm_vol(dwiPath);
Vb = spm_vol(b0Path);
if ~isequal(Vd(1).dim, Vb.dim)
    error('b0 dimensions do not match DWI spatial dimensions.');
end
if max(abs(Vd(1).mat(:) - Vb.mat(:))) > 1e-5
    error('b0 affine/header does not match the source DWI first frame.');
end
end

function [faStatus, maskStatus, faPath, faOnAnchor] = generate_optional_dwi_qc(paths)
faStatus = 'skipped';
maskStatus = 'skipped';
faPath = paths.fa;
faOnAnchor = '';

if command_exists('dwi2mask')
    if ~isfile(paths.brainMask)
        cmd = sprintf('dwi2mask %s %s -fslgrad %s %s -force', ...
            q(paths.dwi), q(paths.brainMask), q(paths.bvec), q(paths.bval));
        [status, out] = system(cmd);
        if status == 0
            copy_if_missing(paths.brainMask, paths.trackingMask, false);
            maskStatus = 'generated';
        else
            maskStatus = ['failed: ', compact_message(out)];
        end
    else
        copy_if_missing(paths.brainMask, paths.trackingMask, false);
        maskStatus = 'exists';
    end
end

if command_exists('dwi2tensor') && command_exists('tensor2metric')
    tensorMif = fullfile(paths.dwiDir, [paths.patientName, '_ses-preop_dwi_tensor.mif']);
    if ~isfile(faPath)
        cmd1 = sprintf('dwi2tensor %s %s -fslgrad %s %s -force', ...
            q(paths.dwi), q(tensorMif), q(paths.bvec), q(paths.bval));
        [status1, out1] = system(cmd1);
        if status1 == 0
            cmd2 = sprintf('tensor2metric %s -fa %s -force', q(tensorMif), q(faPath));
            [status2, out2] = system(cmd2);
            if status2 == 0
                faStatus = 'generated';
            else
                faStatus = ['failed: ', compact_message(out2)];
            end
        else
            faStatus = ['failed: ', compact_message(out1)];
        end
    else
        faStatus = 'exists';
    end
end
end

function [dwiToAnchor, anchorToDwi, b0OnAnchor, anchorOnB0, faOnAnchor] = ensure_b0_anchor_coregistration(paths, anchorAnat, anchorModality, coregMethod, force)
ensure_dir(paths.coregDir);

if use_legacy_ants_outputs(paths, coregMethod)
    [dwiToAnchor, anchorToDwi, b0OnAnchor, anchorOnB0, faOnAnchor] = ...
        ensure_legacy_ants_coregistration(paths, anchorAnat, anchorModality, force);
    return;
end

outputs = ui_style_coreg_outputs(paths, anchorModality, coregMethod);
ensure_dir(outputs.workDir);
move_branch_root_intermediates_to_work(paths, outputs.workDir);

if force || ~isfile(outputs.dwiToAnchor) || ~isfile(outputs.anchorToDwi) || ...
        ~isfile(outputs.b0OnAnchor) || ~isfile(outputs.anchorOnB0)
    switch coregMethod
        case 'SPM'
            run_spm_coregistration_branch(paths, anchorAnat, outputs);
        case 'Hybrid SPM & ANTs'
            run_hybrid_spm_ants_coregistration_branch(paths, anchorAnat, outputs, anchorModality);
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
    faOnAnchor = fullfile(paths.coregDir, [strip_nii_ext(get_file_name(paths.fa)), '2', anchorName, '.nii']);
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
ensure_dir(outputs.workDir);
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
ensure_dir(outputs.workDir);
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
ensure_dir(fileparts(target));
copyfile(source, target, 'f');
end

function write_qc_overlays(paths, anchorAnat, b0OnAnchor, anchorOnB0, faOnAnchor, anchorModality)
ensure_dir(paths.qcDir);
anchorLabel = anchor_label(anchorModality);
write_overlay_png(anchorAnat, b0OnAnchor, ...
    fullfile(paths.qcDir, [paths.subjectId, '_b0_on_', anchorLabel, '.png']), ...
    [paths.subjectId, ' b0 on anchorNative ', anchorModality]);
write_overlay_png(paths.b0, anchorOnB0, ...
    fullfile(paths.qcDir, [paths.subjectId, '_', anchorLabel, '_on_b0.png']), ...
    [paths.subjectId, ' anchorNative ', anchorModality, ' on b0']);
if strlength(string(faOnAnchor)) > 0 && isfile(faOnAnchor)
    write_overlay_png(anchorAnat, faOnAnchor, ...
        fullfile(paths.qcDir, [paths.subjectId, '_fa_on_', anchorLabel, '.png']), ...
        [paths.subjectId, ' FA on anchorNative ', anchorModality]);
end
end

function write_overlay_png(backgroundPath, overlayPath, outputPng, titleText)
if ~isfile(backgroundPath) || ~isfile(overlayPath)
    return;
end
try
    Vb = spm_vol(backgroundPath);
    Vo = spm_vol(overlayPath);
    if numel(Vb) > 1
        Vb = Vb(1);
    end
    if numel(Vo) > 1
        Vo = Vo(1);
    end
    bg = double(spm_read_vols(Vb));
    ov = double(spm_read_vols(Vo));
    if ~isequal(size(bg), size(ov))
        return;
    end
    bg = normalize_volume(bg);
    ov = normalize_volume(ov);
    mask = bg > 0.05 | ov > 0.05;
    zIdx = select_slices(mask, 9);

    fig = figure('Visible', 'off', 'Color', 'w', 'Position', [100, 100, 1200, 900]);
    tiledlayout(3, 3, 'TileSpacing', 'compact', 'Padding', 'compact');
    for i = 1:numel(zIdx)
        nexttile;
        z = zIdx(i);
        bgSl = rot90(bg(:, :, z));
        ovSl = rot90(ov(:, :, z));
        rgb = repmat(bgSl, 1, 1, 3);
        alpha = 0.45 * (ovSl > 0.05);
        rgb(:, :, 1) = max(rgb(:, :, 1), ovSl);
        rgb(:, :, 2) = rgb(:, :, 2) .* (1 - alpha);
        rgb(:, :, 3) = rgb(:, :, 3) .* (1 - alpha);
        image(rgb);
        axis image off;
        title(sprintf('z=%d', z), 'Interpreter', 'none', 'FontSize', 8);
    end
    sgtitle(titleText, 'Interpreter', 'none');
    print(fig, outputPng, '-dpng', '-r150');
    close(fig);
catch ME
    warning('mh_fiber_register_imported_dwi_batch:QcPngFailed', ...
        'Failed to write QC PNG %s: %s', outputPng, ME.message);
    if exist('fig', 'var') && isvalid(fig)
        close(fig);
    end
end
end

function anchorAnat = resolve_anchor_anat(subjectDir, anchorModality, allowT1Fallback)
anatDir = fullfile(subjectDir, 'coregistration', 'anat');
patterns = anchor_patterns(anchorModality);
for p = 1:numel(patterns)
    d = dir(fullfile(anatDir, patterns{p}));
    d = d(~startsWith({d.name}, '._'));
    if ~isempty(d)
        [~, order] = sort({d.name});
        d = d(order);
        anchorAnat = fullfile(d(1).folder, d(1).name);
        return;
    end
end
if allowT1Fallback && ~strcmp(anchorModality, 'T1w')
    anchorAnat = resolve_anchor_anat(subjectDir, 'T1w', false);
    return;
end
error('No anchorNative %s found in %s', anchorModality, anatDir);
end

function transformPath = resolve_anchor_to_mni_transform(subjectDir, patientName)
transformPath = fullfile(subjectDir, 'normalization', 'transformations', ...
    [patientName, '_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz']);
if ~isfile(transformPath)
    d = dir(fullfile(subjectDir, 'normalization', 'transformations', ...
        '*from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz'));
    d = d(~startsWith({d.name}, '._'));
    if ~isempty(d)
        transformPath = fullfile(d(1).folder, d(1).name);
    end
end
if ~isfile(transformPath)
    error('Missing anchorNative-to-MNI transform for %s.', patientName);
end
end

function anchorModality = normalize_anchor_modality(anchorModality)
anchorModality = char(string(anchorModality));
switch lower(anchorModality)
    case {'t1', 't1w'}
        anchorModality = 'T1w';
    case {'t2', 't2w'}
        anchorModality = 'T2w';
    otherwise
        error('Unsupported AnchorModality: %s. Use T1w or T2w.', anchorModality);
end
end

function coregMethod = normalize_coregistration_method(coregMethod)
coregMethod = char(string(coregMethod));
switch lower(strtrim(coregMethod))
    case {'ants', 'ants (avants 2008)'}
        coregMethod = 'ANTs';
    case {'spm', 'spm (friston 2007)'}
        coregMethod = 'SPM';
    case {'hybrid spm & ants', 'hybridspmants', 'hybrid spm and ants'}
        coregMethod = 'Hybrid SPM & ANTs';
    otherwise
        error('Unsupported CoregistrationMethod: %s. Use ANTs, SPM, or Hybrid SPM & ANTs.', coregMethod);
end
end

function suffix = coregistration_transform_suffix(coregMethod)
switch coregMethod
    case 'SPM'
        suffix = 'spm';
    case {'ANTs', 'Hybrid SPM & ANTs'}
        suffix = 'ants';
    otherwise
        error('Unsupported CoregistrationMethod for transform suffix: %s', coregMethod);
end
end

function patterns = anchor_patterns(anchorModality)
patterns = { ...
    ['*space-anchorNative_desc-preproc*acq-iso*', anchorModality, '.nii'], ...
    ['*space-anchorNative_desc-preproc*acq-ax*', anchorModality, '.nii'], ...
    ['*space-anchorNative_desc-preproc*_', anchorModality, '.nii'], ...
    ['*', anchorModality, '.nii']};
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

function qcTag = qc_tag_from_coreg_tag(coregTag)
if strcmp(coregTag, 'dwi')
    qcTag = 'dwi_registration';
else
    suffix = regexprep(coregTag, '^dwi', '');
    qcTag = ['dwi_registration', suffix];
end
end

function statusName = status_filename_from_coreg_tag(coregTag)
if strcmp(coregTag, 'dwi')
    statusName = 'dwi_registration_status.csv';
else
    suffix = regexprep(coregTag, '^dwi', '');
    statusName = ['dwi_registration', suffix, '_status.csv'];
end
end

function [subjects, sourceBases] = resolve_subjects(opts)
if ~isempty(opts.SubjectIds)
    subjects = cellstr(string(opts.SubjectIds));
else
    subjects = default_subjects();
end

sourceBases = containers.Map('KeyType', 'char', 'ValueType', 'char');
if isfile(opts.ImportLog)
    try
        T = readtable(opts.ImportLog, 'TextType', 'string');
        if all(ismember(["phase", "subject", "status", "source_base", "extension"], string(T.Properties.VariableNames)))
            copied = T(strcmp(T.phase, "copy_result") & strcmp(T.status, "copied") & strcmp(T.extension, ".nii.gz"), :);
            if ~isempty(copied) && isempty(opts.SubjectIds)
                detected = cellstr(copied.subject);
                subjects = stable_intersect(default_subjects(), detected);
            end
            for i = 1:height(T)
                subjStr = string(T.subject(i));
                srcStr = string(T.source_base(i));
                if ~ismissing(subjStr) && ~ismissing(srcStr) && strlength(subjStr) > 0 && strlength(srcStr) > 0
                    sourceBases(char(subjStr)) = char(srcStr);
                end
            end
        end
    catch ME
        warning('mh_fiber_register_imported_dwi_batch:ImportLogReadFailed', ...
            'Could not parse import log %s: %s', opts.ImportLog, ME.message);
    end
end
end

function subjects = default_subjects()
subjects = {'LinJia', 'HuFengXian', 'YuDongJian', 'WuYueFen', ...
    'LiPing', 'MaoXiaoMing', 'ChenLingHua', 'FanDongDong', ...
    'HuangDan', 'ZhangMing', 'ZhangXiaoHong', 'ChenMeiJu'};
end

function out = stable_intersect(reference, detected)
out = {};
for i = 1:numel(reference)
    if any(strcmp(reference{i}, detected))
        out{end+1} = reference{i}; %#ok<AGROW>
    end
end
if isempty(out)
    out = reference;
end
end

function sourceBase = lookup_source_base(sourceBases, subjectId)
if isKey(sourceBases, subjectId)
    sourceBase = sourceBases(subjectId);
else
    sourceBase = '';
end
end

function row = empty_status_row()
row = struct();
row.subject = '';
row.source_base = '';
row.status = '';
row.message = '';
row.raw_dwi = '';
row.staged_dwi = '';
row.b0 = '';
row.anchor_modality = '';
row.coregistration_method = '';
row.anchor_anat = '';
row.normalization_forward = '';
row.dwi_to_anchor_transform = '';
row.anchor_to_dwi_transform = '';
row.b0_on_anchor = '';
row.anchor_on_b0 = '';
row.qc_dir = '';
row.dwi_volumes = NaN;
row.bval_count = NaN;
row.bvec_count = NaN;
row.b0_count = NaN;
row.dim_x = NaN;
row.dim_y = NaN;
row.dim_z = NaN;
row.voxel_x = NaN;
row.voxel_y = NaN;
row.voxel_z = NaN;
row.low_resolution_warning = false;
row.forward_transform_exists = false;
row.inverse_transform_exists = false;
row.fa_status = '';
row.mask_status = '';
end

function vals = load_numeric_vector(path)
vals = load(path);
vals = vals(:)';
if isempty(vals) || ~isnumeric(vals)
    error('Could not read numeric values from %s', path);
end
end

function ensure_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function must_be_file(path, label)
if ~isfile(path)
    error('Missing %s: %s', label, path);
end
end

function copy_if_missing(source, target, force)
if force || ~isfile(target)
    copyfile(source, target);
end
end

function tf = command_exists(commandName)
[status, ~] = system(sprintf('command -v %s', commandName));
tf = status == 0;
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

function name = get_file_name(path)
[~, name, ext] = fileparts(path);
name = [name, ext];
end

function stem = strip_nii_ext(name)
stem = regexprep(name, '\.nii(\.gz)?$', '');
end

function s = compact_message(s)
s = char(string(s));
s = regexprep(s, '\s+', ' ');
if numel(s) > 240
    s = [s(1:237), '...'];
end
end

function qpath = q(path)
qpath = ['''', strrep(path, '''', '''"''"'''), ''''];
end

function cleanup_temp_dir(path)
if strlength(string(path)) > 0 && isfolder(path)
    try
        rmdir(path, 's');
    catch
    end
end
end

function vol = normalize_volume(vol)
finiteVals = vol(isfinite(vol));
if isempty(finiteVals)
    vol = zeros(size(vol));
    return;
end
lo = percentile_value(finiteVals, 1);
hi = percentile_value(finiteVals, 99);
if hi <= lo
    hi = max(finiteVals);
    lo = min(finiteVals);
end
if hi <= lo
    vol = zeros(size(vol));
else
    vol = min(max((vol - lo) ./ (hi - lo), 0), 1);
end
end

function v = percentile_value(vals, pct)
vals = sort(vals(:));
idx = max(1, min(numel(vals), round((pct / 100) * numel(vals))));
v = vals(idx);
end

function zIdx = select_slices(mask, n)
zHas = squeeze(any(any(mask, 1), 2));
idx = find(zHas);
if isempty(idx)
    idx = 1:size(mask, 3);
end
if numel(idx) >= n
    pick = round(linspace(1, numel(idx), n));
    zIdx = idx(pick);
else
    zIdx = round(linspace(1, size(mask, 3), n));
end
zIdx = max(1, min(size(mask, 3), zIdx));
end

function write_subject_json(row, path)
try
    txt = jsonencode(row, 'PrettyPrint', true);
catch
    txt = jsonencode(row);
end
fid = fopen(path, 'w');
if fid < 0
    warning('Could not open QC JSON for writing: %s', path);
    return;
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', txt);
end
