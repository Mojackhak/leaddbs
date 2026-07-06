function row = mh_fiber_process_imported_dwi(jobSpec, opts)
% Process one imported DWI job from explicit paths and options.

if nargin < 2 || isempty(opts)
    opts = struct();
end
opts = normalize_processing_options(opts);
validate_job_spec(jobSpec);

subjectId = char(string(jobSpec.subjectId));
paths = jobSpec.paths;

row = empty_status_row();
row.subject = subjectId;
row.source_base = char(string(jobSpec.sourceBase));
row.status = 'started';

try
    row.raw_dwi = paths.rawDwiGz;
    row.staged_dwi = paths.dwi;
    row.b0 = paths.b0;
    row.qc_dir = paths.qcDir;
    row.anchor_modality = opts.AnchorModality;
    row.coregistration_method = opts.CoregistrationMethod;
    row.distortion_correction = opts.DistortionCorrection;
    row.anchor_anat = char(string(jobSpec.anchorAnat));
    row.normalization_forward = char(string(jobSpec.normalizationForward));

    validate_raw_inputs(paths);
    [nVolumes, bvals, bvecCount] = validate_gradients(paths.rawBval, paths.rawBvec, paths.rawDwiGz);
    row.dwi_volumes = nVolumes;
    row.bval_count = numel(bvals);
    row.bvec_count = bvecCount;
    row.b0_count = sum(bvals < 10);

    stage_dwi_derivatives(paths, opts.Force);
    if strcmp(opts.DistortionCorrection, 'synb0')
        [row.total_readout_time, row.total_readout_time_source] = ...
            resolve_total_readout_time_for_status(paths.json, opts.TotalReadoutTime, opts.DefaultTotalReadoutTime);
        row.phase_encoding_vector = sprintf('%g %g %g', opts.PhaseEncodingVector);
        row.synb0_status = 'started';
        row.eddy_status = 'not_started';
        t1Anat = char(string(jobSpec.t1Anat));
        dcResult = mh_fiber_dwi_distortion_correction(paths, t1Anat, ...
            'Force', opts.Force, ...
            'PhaseEncodingVector', opts.PhaseEncodingVector, ...
            'TotalReadoutTime', opts.TotalReadoutTime, ...
            'DefaultTotalReadoutTime', opts.DefaultTotalReadoutTime, ...
            'Synb0ContainerEngine', opts.Synb0ContainerEngine, ...
            'Synb0Image', opts.Synb0Image, ...
            'FreeSurferLicense', opts.FreeSurferLicense, ...
            'Synb0MinDockerMemoryGB', opts.Synb0MinDockerMemoryGB, ...
            'Synb0WorkRoot', opts.Synb0WorkRoot);
        paths.dwi = dcResult.dwi;
        paths.bval = dcResult.bval;
        paths.bvec = dcResult.bvec;
        paths.b0 = dcResult.b0;
        row.staged_dwi = paths.dwi;
        row.b0 = paths.b0;
        row.synb0_status = dcResult.synb0Status;
        row.eddy_status = dcResult.eddyStatus;
        row.rotated_bvec = dcResult.rotatedBvec;
        row.topup_field = dcResult.topupFieldcoef;
        row.total_readout_time = dcResult.totalReadoutTime;
        row.total_readout_time_source = dcResult.totalReadoutTimeSource;
        row.phase_encoding_vector = sprintf('%g %g %g', dcResult.phaseEncodingVector);
        row.fake_b0_preproc = dcResult.b0;
        row.fake_b0_coreg_target = paths.fakeB0Coreg;
        row.fake_b0_metadata = write_fake_b0_metadata(paths, dcResult);
        write_overlay_png(dcResult.distortedB0, dcResult.b0, ...
            fullfile(paths.qcDir, [subjectId, '_distorted_b0_vs_corrected_b0.png']), ...
            [subjectId, ' distorted b0 vs corrected b0']);
    else
        row.synb0_status = 'skipped';
        row.eddy_status = 'skipped';
        row.rotated_bvec = '';
        row.topup_field = '';
        row.total_readout_time = NaN;
        row.total_readout_time_source = '';
        row.phase_encoding_vector = '';
        row.fake_b0_preproc = '';
        row.fake_b0_coreg_target = '';
        row.fake_b0_metadata = '';
    end
    [row.dim_x, row.dim_y, row.dim_z, row.voxel_x, row.voxel_y, row.voxel_z] = ...
        read_dwi_geometry(paths.dwi);
    row.low_resolution_warning = row.voxel_z >= 4;

    mh_fiber_extract_mean_b0(paths.dwi, paths.b0, bvals, opts.Force);
    validate_b0_geometry(paths.dwi, paths.b0);

    if opts.GenerateOptionalDwiQc
        [row.fa_status, row.mask_status, paths.fa, paths.faOnAnchor] = generate_optional_dwi_qc(paths);
    else
        row.fa_status = 'skipped';
        row.mask_status = 'skipped';
    end

    if opts.RunCoregistration
        [row.dwi_to_anchor_transform, row.anchor_to_dwi_transform, row.b0_on_anchor, row.anchor_on_b0, paths.faOnAnchor] = ...
            mh_fiber_dwi_coregister_b0_to_anchor(paths, row.anchor_anat, opts.AnchorModality, ...
            opts.CoregistrationMethod, opts.Force);
        row.forward_transform_exists = isfile(row.dwi_to_anchor_transform);
        row.inverse_transform_exists = isfile(row.anchor_to_dwi_transform);
        row.coregistration_status = 'registered';
        write_qc_overlays(paths, row.anchor_anat, row.b0_on_anchor, row.anchor_on_b0, ...
            paths.faOnAnchor, opts.AnchorModality);
    else
        row.dwi_to_anchor_transform = '';
        row.anchor_to_dwi_transform = '';
        row.b0_on_anchor = '';
        row.anchor_on_b0 = '';
        row.forward_transform_exists = false;
        row.inverse_transform_exists = false;
        if strcmp(opts.DistortionCorrection, 'synb0')
            row.coregistration_status = 'pending_ui';
        else
            row.coregistration_status = 'skipped';
        end
    end

    if opts.RunCoregistration
        row.status = 'registered';
    elseif strcmp(opts.DistortionCorrection, 'synb0')
        row.status = 'pending_ui_coregistration';
    else
        row.status = 'staged';
    end
    row.message = 'ok';
catch ME
    row.status = 'registration_failed';
    row.message = mh_fiber_compact_message(ME.message, 240);
    if strcmp(row.distortion_correction, 'synb0')
        if strlength(string(row.synb0_status)) == 0 || strcmp(row.synb0_status, 'started')
            row.synb0_status = 'failed';
        end
        if strlength(string(row.eddy_status)) == 0
            row.eddy_status = 'not_started';
        end
    end
    fprintf(2, 'Subject %s failed: %s\n', subjectId, ME.message);
end

if ~isfolder(row.qc_dir) && strlength(string(row.qc_dir)) > 0
    mh_util_make_dir(row.qc_dir);
end
if strlength(string(row.qc_dir)) > 0
    write_subject_json(row, fullfile(row.qc_dir, [subjectId, '_dwi_registration_qc.json']));
end

end

function validate_job_spec(jobSpec)
required = {'subjectId', 'sourceBase', 'paths', 'anchorAnat', 't1Anat', 'normalizationForward'};
for i = 1:numel(required)
    if ~isfield(jobSpec, required{i})
        error('mh_fiber_process_imported_dwi:InvalidJobSpec', ...
            'Missing jobSpec field: %s', required{i});
    end
end
if ~isstruct(jobSpec.paths)
    error('mh_fiber_process_imported_dwi:InvalidJobSpec', ...
        'jobSpec.paths must be a struct.');
end
end

function opts = normalize_processing_options(opts)
opts = fill_option(opts, 'AnchorModality', 'T2w');
opts = fill_option(opts, 'CoregistrationMethod', 'ANTs');
opts = fill_option(opts, 'DistortionCorrection', 'none');
opts = fill_option(opts, 'PhaseEncodingVector', [0 1 0]);
opts = fill_option(opts, 'TotalReadoutTime', NaN);
opts = fill_option(opts, 'DefaultTotalReadoutTime', 0.05);
opts = fill_option(opts, 'Synb0ContainerEngine', 'auto');
opts = fill_option(opts, 'Synb0Image', 'leonyichencai/synb0-disco:v3.1');
opts = fill_option(opts, 'FreeSurferLicense', '');
opts = fill_option(opts, 'Synb0MinDockerMemoryGB', 12);
opts = fill_option(opts, 'Synb0WorkRoot', '');
opts = fill_option(opts, 'RunCoregistration', []);
opts = fill_option(opts, 'GenerateOptionalDwiQc', true);
opts = fill_option(opts, 'Force', false);

opts.AnchorModality = normalize_anchor_modality(opts.AnchorModality);
opts.CoregistrationMethod = normalize_coregistration_method(opts.CoregistrationMethod);
opts.DistortionCorrection = normalize_distortion_correction(opts.DistortionCorrection);
opts.PhaseEncodingVector = double(opts.PhaseEncodingVector(:)');
opts.TotalReadoutTime = double(opts.TotalReadoutTime);
opts.DefaultTotalReadoutTime = double(opts.DefaultTotalReadoutTime);
opts.Synb0ContainerEngine = char(string(opts.Synb0ContainerEngine));
opts.Synb0Image = char(string(opts.Synb0Image));
opts.FreeSurferLicense = char(string(opts.FreeSurferLicense));
opts.Synb0MinDockerMemoryGB = double(opts.Synb0MinDockerMemoryGB);
opts.Synb0WorkRoot = char(string(opts.Synb0WorkRoot));
opts.GenerateOptionalDwiQc = logical(opts.GenerateOptionalDwiQc);
opts.Force = logical(opts.Force);
if isempty(opts.RunCoregistration)
    opts.RunCoregistration = ~strcmp(opts.DistortionCorrection, 'synb0');
else
    opts.RunCoregistration = logical(opts.RunCoregistration);
end
end

function opts = fill_option(opts, fieldName, value)
if ~isfield(opts, fieldName)
    opts.(fieldName) = value;
end
end

function validate_raw_inputs(paths)
if ~isfolder(paths.subjectDir)
    error('Subject derivative directory does not exist: %s', paths.subjectDir);
end
if ~isfile(paths.rawDwiGz) && ~isfile(paths.rawDwiNii)
    error('Raw DWI image not found: %s', paths.rawDwiGz);
end
mh_util_must_be_file(paths.rawJson, 'raw DWI JSON');
mh_util_must_be_file(paths.rawBval, 'raw DWI bval');
mh_util_must_be_file(paths.rawBvec, 'raw DWI bvec');
end

function [nVolumes, bvals, bvecCount] = validate_gradients(bvalPath, bvecPath, dwiPath)
bvals = mh_fiber_load_bval(bvalPath);
bvecCount = mh_fiber_bvec_count(bvecPath);

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

cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(tempNii));
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
mh_util_make_dir(paths.dwiDir);
mh_util_make_dir(paths.coregDir);
mh_util_make_dir(paths.qcDir);

if force || ~isfile(paths.dwi)
    if isfile(paths.rawDwiGz)
        tempDir = tempname;
        mkdir(tempDir);
        cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(tempDir));
        extracted = gunzip(paths.rawDwiGz, tempDir);
        if isempty(extracted) || ~isfile(extracted{1})
            error('Could not decompress raw DWI: %s', paths.rawDwiGz);
        end
        copyfile(extracted{1}, paths.dwi, 'f');
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

function metadataPath = write_fake_b0_metadata(paths, dcResult)
metadata = struct();
metadata.FakeCoregisterVolume = true;
metadata.SourceImage = dcResult.b0;
metadata.GeneratedFrom = 'Synb0/topup/eddy corrected mean b0';
metadata.IntendedUse = 'coregistration_qc_only';
metadata.ExcludeFromNormalization = true;
metadata.CorrectedDwi = dcResult.dwi;
metadata.RotatedBvec = dcResult.rotatedBvec;
metadata.TopupField = dcResult.topupFieldcoef;
metadata.TotalReadoutTime = dcResult.totalReadoutTime;
metadata.TotalReadoutTimeSource = dcResult.totalReadoutTimeSource;
metadata.PhaseEncodingVector = sprintf('%g %g %g', dcResult.phaseEncodingVector);
metadata.ExpectedCoregisteredImage = paths.fakeB0Coreg;

metadataPath = sidecar_json_path(dcResult.b0);
write_subject_json(metadata, metadataPath);

mh_util_make_dir(paths.coregAnatDir);
write_subject_json(metadata, sidecar_json_path(paths.fakeB0Coreg));
end

function jsonPath = sidecar_json_path(imagePath)
imagePath = char(string(imagePath));
jsonPath = regexprep(imagePath, '\.nii(\.gz)?$', '.json');
if strcmp(jsonPath, imagePath)
    jsonPath = [imagePath, '.json'];
end
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
            mh_fiber_shell_quote(paths.dwi), mh_fiber_shell_quote(paths.brainMask), ...
            mh_fiber_shell_quote(paths.bvec), mh_fiber_shell_quote(paths.bval));
        [status, out] = system(cmd);
        if status == 0
            copy_if_missing(paths.brainMask, paths.trackingMask, false);
            maskStatus = 'generated';
        else
            maskStatus = ['failed: ', mh_fiber_compact_message(out, 240)];
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
            mh_fiber_shell_quote(paths.dwi), mh_fiber_shell_quote(tensorMif), ...
            mh_fiber_shell_quote(paths.bvec), mh_fiber_shell_quote(paths.bval));
        [status1, out1] = system(cmd1);
        if status1 == 0
            cmd2 = sprintf('tensor2metric %s -fa %s -force', ...
                mh_fiber_shell_quote(tensorMif), mh_fiber_shell_quote(faPath));
            [status2, out2] = system(cmd2);
            if status2 == 0
                faStatus = 'generated';
            else
                faStatus = ['failed: ', mh_fiber_compact_message(out2, 240)];
            end
        else
            faStatus = ['failed: ', mh_fiber_compact_message(out1, 240)];
        end
    else
        faStatus = 'exists';
    end
end
end

function write_qc_overlays(paths, anchorAnat, b0OnAnchor, anchorOnB0, faOnAnchor, anchorModality)
mh_util_make_dir(paths.qcDir);
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

function [totalReadoutTime, source] = resolve_total_readout_time_for_status(jsonPath, requestedValue, defaultValue)
if ~isnan(requestedValue)
    totalReadoutTime = requestedValue;
    source = 'parameter';
    return;
end
source = 'default';
totalReadoutTime = defaultValue;
try
    metadata = jsondecode(fileread(jsonPath));
    if isfield(metadata, 'TotalReadoutTime') && isnumeric(metadata.TotalReadoutTime) && metadata.TotalReadoutTime > 0
        totalReadoutTime = metadata.TotalReadoutTime;
        source = 'json';
    end
catch
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
    case {'flirt bbr', 'flirtbbr', 'bbr', 'fsl flirt bbr'}
        coregMethod = 'FLIRT BBR';
    otherwise
        error('Unsupported CoregistrationMethod: %s. Use ANTs, SPM, Hybrid SPM & ANTs, or FLIRT BBR.', coregMethod);
end
end

function distortionCorrection = normalize_distortion_correction(distortionCorrection)
distortionCorrection = lower(strtrim(char(string(distortionCorrection))));
switch distortionCorrection
    case {'', 'none', 'off', 'false', 'no'}
        distortionCorrection = 'none';
    case {'synb0', 'synb0-disco', 'synb0_disco'}
        distortionCorrection = 'synb0';
    otherwise
        error('Unsupported DistortionCorrection: %s. Use none or synb0.', distortionCorrection);
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
row.distortion_correction = '';
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
row.coregistration_status = '';
row.synb0_status = '';
row.eddy_status = '';
row.rotated_bvec = '';
row.topup_field = '';
row.total_readout_time = NaN;
row.total_readout_time_source = '';
row.phase_encoding_vector = '';
row.fake_b0_preproc = '';
row.fake_b0_coreg_target = '';
row.fake_b0_metadata = '';
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
    mh_util_write_json(path, row, 'mh_fiber_register_imported_dwi_batch:CannotWriteJson');
catch ME
    warning('mh_fiber_register_imported_dwi_batch:JsonWriteFailed', ...
        'Could not write JSON %s: %s', path, ME.message);
end
end
