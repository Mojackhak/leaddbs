function result = mh_fiber_convert_dicom_dwi_to_leaddbs(varargin)
% Convert one DWI DICOM folder to a Lead-DBS/BIDS DWI four-file set.

parser = inputParser;
parser.FunctionName = 'mh_fiber_convert_dicom_dwi_to_leaddbs';
parser.addParameter('DicomDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputBase', '', @(x) ischar(x) || isstring(x));
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('WorkDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('ReferenceNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('TileOrder', 'row_major_right_to_left', @(x) ischar(x) || isstring(x));
parser.addParameter('SliceCount', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('SkipPaddingTiles', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = normalize_options(parser.Results);

validate_required_options(opts);
paths = output_paths(opts.OutputDir, opts.OutputBase);
result = base_result(opts, paths);
if ~opts.DryRun
    ensure_output_available(paths, opts.Force);
    mh_util_make_dir(opts.OutputDir);
end

[workDir, cleanupObj] = prepare_work_dir(opts);
[dcm2niixPath, dcm2niixInfo] = mh_fiber_resolve_dcm2niix('RepoDir', opts.RepoDir);
result.Dcm2niixPath = dcm2niixPath;
result.Dcm2niixSource = dcm2niixInfo.Source;
result.WorkDir = workDir;

[cmd, status, output] = run_dcm2niix(dcm2niixPath, opts.DicomDir, workDir);
result.Dcm2niixCommand = cmd;
result.Dcm2niixStatus = status;
result.Dcm2niixOutput = mh_fiber_compact_message(output);
if status ~= 0
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:Dcm2niixFailed', ...
        'dcm2niix failed for %s: %s', opts.DicomDir, mh_fiber_compact_message(output));
end

candidate = select_dwi_candidate(workDir);
result.ConvertedNifti = candidate.Nifti;
result.ConvertedJson = candidate.Json;
result.ConvertedBval = candidate.Bval;
result.ConvertedBvec = candidate.Bvec;
result.ConvertedImageSize = mat2str(candidate.ImageSize);
result.ConvertedVolumeCount = candidate.VolumeCount;

if candidate.ImageSize(3) == 1
    result.Decision = 'mosaic_reconstruction';
    if opts.DryRun
        recon = mh_fiber_reconstruct_mosaic_dwi( ...
            'SourceNifti', candidate.Nifti, ...
            'SourceJson', candidate.Json, ...
            'SourceBval', candidate.Bval, ...
            'SourceBvec', candidate.Bvec, ...
            'DicomDir', opts.DicomDir, ...
            'ReferenceNifti', opts.ReferenceNifti, ...
            'SliceCount', opts.SliceCount, ...
            'TileOrder', opts.TileOrder, ...
            'SkipPaddingTiles', opts.SkipPaddingTiles, ...
            'OutputDir', opts.OutputDir, ...
            'OutputBase', opts.OutputBase, ...
            'Parallel', opts.Parallel, ...
            'ParallelWorkers', opts.ParallelWorkers, ...
            'DryRun', true);
        result.Status = 'dry_run_mosaic_reconstruction';
        result.Message = recon.Message;
        result.OutputImageSize = recon.OutputImageSize;
    else
        recon = mh_fiber_reconstruct_mosaic_dwi( ...
            'SourceNifti', candidate.Nifti, ...
            'SourceJson', candidate.Json, ...
            'SourceBval', candidate.Bval, ...
            'SourceBvec', candidate.Bvec, ...
            'DicomDir', opts.DicomDir, ...
            'ReferenceNifti', opts.ReferenceNifti, ...
            'SliceCount', opts.SliceCount, ...
            'TileOrder', opts.TileOrder, ...
            'SkipPaddingTiles', opts.SkipPaddingTiles, ...
            'OutputDir', opts.OutputDir, ...
            'OutputBase', opts.OutputBase, ...
            'Parallel', opts.Parallel, ...
            'ParallelWorkers', opts.ParallelWorkers, ...
            'Force', opts.Force);
        result.Status = 'converted_mosaic_reconstructed';
        result.Message = recon.Message;
        result.OutputImageSize = recon.OutputImageSize;
        augment_final_json(paths.Json, opts, result, false);
        write_qc_json(paths.QcJson, opts, result, candidate);
    end
else
    result.Decision = 'direct_dwi';
    result.OutputImageSize = mat2str(candidate.ImageSize);
    if opts.DryRun
        result.Status = 'dry_run_direct_dwi';
        result.Message = 'DWI DICOM conversion produced a multi-slice DWI; no files written.';
    else
        result.Status = 'converted_direct_dwi';
        result.Message = 'ok';
        copy_direct_candidate(candidate, paths);
        augment_final_json(paths.Json, opts, result, true);
        validate_final_outputs(paths);
        write_qc_json(paths.QcJson, opts, result, candidate);
    end
end

result.OutputNifti = paths.Nifti;
result.OutputJson = paths.Json;
result.OutputBval = paths.Bval;
result.OutputBvec = paths.Bvec;
result.QcJson = paths.QcJson;

if ~isempty(cleanupObj)
    delete(cleanupObj);
end
end

function opts = normalize_options(opts)
fields = {'DicomDir', 'OutputDir', 'OutputBase', 'RepoDir', 'WorkDir', 'ReferenceNifti'};
for i = 1:numel(fields)
    opts.(fields{i}) = char(string(opts.(fields{i})));
end
opts.TileOrder = validatestring(char(string(opts.TileOrder)), ...
    {'row_major_right_to_left', 'row_major_left_to_right', ...
    'bottom_to_top_left_to_right'}, ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs', 'TileOrder');
if ~isempty(opts.SliceCount)
    opts.SliceCount = round(double(opts.SliceCount));
end
opts.SkipPaddingTiles = logical(opts.SkipPaddingTiles);
opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
opts.Force = logical(opts.Force);
opts.DryRun = logical(opts.DryRun);
end

function validate_required_options(opts)
if isempty(opts.DicomDir)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:MissingDicomDir', ...
        'DicomDir must be provided.');
end
if isempty(opts.OutputDir)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:MissingOutputDir', ...
        'OutputDir must be provided.');
end
if isempty(opts.OutputBase)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:MissingOutputBase', ...
        'OutputBase must be provided.');
end
if ~isfolder(opts.DicomDir)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:MissingDicomDir', ...
        'DICOM directory does not exist: %s', opts.DicomDir);
end
end

function paths = output_paths(outputDir, outputBase)
paths = struct();
paths.Nifti = fullfile(outputDir, [outputBase, '.nii.gz']);
paths.Json = fullfile(outputDir, [outputBase, '.json']);
paths.Bval = fullfile(outputDir, [outputBase, '.bval']);
paths.Bvec = fullfile(outputDir, [outputBase, '.bvec']);
paths.QcJson = fullfile(outputDir, [outputBase, '_dicom_conversion_qc.json']);
end

function result = base_result(opts, paths)
result = struct();
result.Status = 'started';
result.Message = '';
result.DicomDir = opts.DicomDir;
result.OutputDir = opts.OutputDir;
result.OutputBase = opts.OutputBase;
result.TileOrder = opts.TileOrder;
result.SliceCount = opts.SliceCount;
result.SkipPaddingTiles = opts.SkipPaddingTiles;
result.OutputNifti = paths.Nifti;
result.OutputJson = paths.Json;
result.OutputBval = paths.Bval;
result.OutputBvec = paths.Bvec;
result.QcJson = paths.QcJson;
result.Decision = '';
result.WorkDir = '';
result.Dcm2niixPath = '';
result.Dcm2niixSource = '';
result.Dcm2niixCommand = '';
result.Dcm2niixStatus = NaN;
result.Dcm2niixOutput = '';
result.ConvertedNifti = '';
result.ConvertedJson = '';
result.ConvertedBval = '';
result.ConvertedBvec = '';
result.ConvertedImageSize = '';
result.ConvertedVolumeCount = NaN;
result.OutputImageSize = '';
end

function ensure_output_available(paths, force)
targets = {paths.Nifti, paths.Json, paths.Bval, paths.Bvec, paths.QcJson};
for i = 1:numel(targets)
    if isfile(targets{i}) && ~force
        error('mh_fiber_convert_dicom_dwi_to_leaddbs:OutputExists', ...
            'Output already exists. Use Force=true to overwrite: %s', targets{i});
    end
end
end

function [workDir, cleanupObj] = prepare_work_dir(opts)
cleanupObj = [];
if isempty(opts.WorkDir)
    workDir = tempname;
    mkdir(workDir);
    cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(workDir));
else
    workDir = opts.WorkDir;
    if isfolder(workDir) && opts.Force
        rmdir(workDir, 's');
    end
    mh_util_make_dir(workDir);
end
end

function [cmd, status, output] = run_dcm2niix(dcm2niixPath, dicomDir, workDir)
cmd = sprintf('%s -f converted_%%p_s%%s -i y -b y -ba n -z y -o %s %s', ...
    mh_fiber_shell_quote(dcm2niixPath), mh_fiber_shell_quote(workDir), ...
    mh_fiber_shell_quote(dicomDir));
[status, output] = system(cmd);
end

function candidate = select_dwi_candidate(workDir)
niiFiles = [dir(fullfile(workDir, '*.nii.gz')); dir(fullfile(workDir, '*.nii'))];
candidates = repmat(empty_candidate(), 0, 1);
for i = 1:numel(niiFiles)
    name = niiFiles(i).name;
    if startsWith(name, '._') || contains(name, '_ADC')
        continue;
    end
    niftiPath = fullfile(niiFiles(i).folder, name);
    base = mh_fiber_strip_nii_ext(name);
    paths = sidecar_paths(niiFiles(i).folder, base, niftiPath);
    if ~isfile(paths.Json) || ~isfile(paths.Bval) || ~isfile(paths.Bvec)
        continue;
    end
    try
        info = niftiinfo(niftiPath);
        imageSize = double(info.ImageSize);
        if numel(imageSize) < 4
            imageSize(4) = 1;
        end
        bvals = mh_fiber_load_bval(paths.Bval);
        bvecCount = mh_fiber_bvec_count(paths.Bvec);
        if numel(bvals) ~= imageSize(4) || bvecCount ~= imageSize(4) || ~any(bvals < 10)
            continue;
        end
        candidate = empty_candidate();
        candidate.Base = base;
        candidate.Nifti = niftiPath;
        candidate.Json = paths.Json;
        candidate.Bval = paths.Bval;
        candidate.Bvec = paths.Bvec;
        candidate.ImageSize = imageSize;
        candidate.VolumeCount = imageSize(4);
        candidate.SliceCount = imageSize(3);
        candidate.Score = imageSize(4) * 100000 + imageSize(3);
        candidates(end + 1) = candidate; %#ok<AGROW>
    catch
    end
end

if isempty(candidates)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:NoCompleteDwiSet', ...
        'dcm2niix did not produce a complete DWI NIfTI/JSON/bval/bvec set in %s.', workDir);
end

[~, idx] = max([candidates.Score]);
candidate = candidates(idx);
end

function candidate = empty_candidate()
candidate = struct();
candidate.Base = '';
candidate.Nifti = '';
candidate.Json = '';
candidate.Bval = '';
candidate.Bvec = '';
candidate.ImageSize = [];
candidate.VolumeCount = NaN;
candidate.SliceCount = NaN;
candidate.Score = -Inf;
end

function paths = sidecar_paths(folder, base, niftiPath)
paths = struct();
paths.Nifti = niftiPath;
paths.Json = fullfile(folder, [base, '.json']);
paths.Bval = fullfile(folder, [base, '.bval']);
paths.Bvec = fullfile(folder, [base, '.bvec']);
end

function copy_direct_candidate(candidate, paths)
copy_nifti_gz(candidate.Nifti, paths.Nifti);
copyfile(candidate.Json, paths.Json, 'f');
copyfile(candidate.Bval, paths.Bval, 'f');
copyfile(candidate.Bvec, paths.Bvec, 'f');
end

function copy_nifti_gz(source, target)
if endsWith(source, '.nii.gz')
    copyfile(source, target, 'f');
    return;
end
data = niftiread(source);
info = niftiinfo(source);
info.Filename = target;
tempDir = tempname;
mkdir(tempDir);
cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(tempDir));
tempBase = fullfile(tempDir, mh_fiber_nii_basename(target));
tempNii = [tempBase, '.nii'];
info.Filename = tempNii;
niftiwrite(data, tempNii, info, 'Compressed', false);
writtenNii = find_written_nifti(tempNii);
gzip(writtenNii);
tempOutput = [writtenNii, '.gz'];
if ~isfile(tempOutput)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:NiftiWriteFailed', ...
        'gzip did not create expected file: %s', tempOutput);
end
movefile(tempOutput, target, 'f');
clear cleanupObj;
mh_fiber_cleanup_temp_dir(tempDir);
end

function writtenNii = find_written_nifti(expectedPath)
candidates = {expectedPath, [expectedPath, '.nii']};
for i = 1:numel(candidates)
    if isfile(candidates{i})
        writtenNii = candidates{i};
        return;
    end
end
error('mh_fiber_convert_dicom_dwi_to_leaddbs:NiftiWriteFailed', ...
    'niftiwrite did not create an uncompressed NIfTI near: %s', expectedPath);
end

function augment_final_json(jsonPath, opts, result, directCopy)
metadata = jsondecode(fileread(jsonPath));
metadata.DicomDwiConversion = true;
metadata.DicomDwiConversionSource = opts.DicomDir;
metadata.DicomDwiConversionDecision = result.Decision;
metadata.DicomDwiConversionTileOrder = opts.TileOrder;
metadata.DicomDwiConversionSkipPaddingTiles = opts.SkipPaddingTiles;
metadata.DicomDwiConversionDirectCopy = directCopy;
metadata.DicomDwiConversionDcm2niixPath = result.Dcm2niixPath;
metadata.DicomDwiConversionDcm2niixSource = result.Dcm2niixSource;
metadata.DicomDwiConversionQcJson = result.QcJson;
metadata.DicomDwiConversionConvertedImageSize = result.ConvertedImageSize;
metadata.DicomDwiConversionOutputImageSize = result.OutputImageSize;
mh_util_write_json(jsonPath, metadata, ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs:CannotWriteJson');
end

function write_qc_json(qcJson, opts, result, candidate)
qc = struct();
qc.Status = result.Status;
qc.Message = result.Message;
qc.DicomDir = opts.DicomDir;
qc.OutputDir = opts.OutputDir;
qc.OutputBase = opts.OutputBase;
qc.TileOrder = opts.TileOrder;
qc.SkipPaddingTiles = opts.SkipPaddingTiles;
qc.OutputNifti = result.OutputNifti;
qc.OutputJson = result.OutputJson;
qc.OutputBval = result.OutputBval;
qc.OutputBvec = result.OutputBvec;
qc.Decision = result.Decision;
qc.Dcm2niixPath = result.Dcm2niixPath;
qc.Dcm2niixSource = result.Dcm2niixSource;
qc.Dcm2niixStatus = result.Dcm2niixStatus;
qc.Dcm2niixOutput = result.Dcm2niixOutput;
qc.ConvertedNifti = candidate.Nifti;
qc.ConvertedJson = candidate.Json;
qc.ConvertedBval = candidate.Bval;
qc.ConvertedBvec = candidate.Bvec;
qc.ConvertedImageSize = candidate.ImageSize;
qc.OutputImageSize = result.OutputImageSize;
mh_util_write_json(qcJson, qc, ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs:CannotWriteJson');
end

function validate_final_outputs(paths)
mh_util_must_be_file(paths.Nifti, 'output NIfTI', ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs:MissingFile');
mh_util_must_be_file(paths.Json, 'output JSON', ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs:MissingFile');
mh_util_must_be_file(paths.Bval, 'output bval', ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs:MissingFile');
mh_util_must_be_file(paths.Bvec, 'output bvec', ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs:MissingFile');

info = niftiinfo(paths.Nifti);
imageSize = double(info.ImageSize);
if numel(imageSize) < 4
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:OutputNot4D', ...
        'Output DWI is not 4D: %s', paths.Nifti);
end
bvals = mh_fiber_load_bval(paths.Bval);
bvecCount = mh_fiber_bvec_count(paths.Bvec);
if numel(bvals) ~= imageSize(4)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:BvalMismatch', ...
        'bval count (%d) does not match output volume count (%d).', ...
        numel(bvals), imageSize(4));
end
if bvecCount ~= imageSize(4)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:BvecMismatch', ...
        'bvec count (%d) does not match output volume count (%d).', ...
        bvecCount, imageSize(4));
end
if ~any(bvals < 10)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:MissingB0', ...
        'Output DWI has no b0 volume with bval < 10.');
end
end
