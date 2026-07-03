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
    ensure_dir(opts.OutputDir);
end

[workDir, cleanupObj] = prepare_work_dir(opts);
[dcm2niixPath, dcm2niixInfo] = mh_fiber_resolve_dcm2niix('RepoDir', opts.RepoDir);
result.Dcm2niixPath = dcm2niixPath;
result.Dcm2niixSource = dcm2niixInfo.Source;
result.WorkDir = workDir;

[cmd, status, output] = run_dcm2niix(dcm2niixPath, opts.DicomDir, workDir);
result.Dcm2niixCommand = cmd;
result.Dcm2niixStatus = status;
result.Dcm2niixOutput = compact_message(output);
if status ~= 0
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:Dcm2niixFailed', ...
        'dcm2niix failed for %s: %s', opts.DicomDir, compact_message(output));
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
        copy_direct_candidate(candidate, paths);
        augment_final_json(paths.Json, opts, result, true);
        validate_final_outputs(paths);
        write_qc_json(paths.QcJson, opts, result, candidate);
        result.Status = 'converted_direct_dwi';
        result.Message = 'ok';
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
    cleanupObj = onCleanup(@() cleanup_temp_dir(workDir));
else
    workDir = opts.WorkDir;
    if isfolder(workDir) && opts.Force
        rmdir(workDir, 's');
    end
    ensure_dir(workDir);
end
end

function [cmd, status, output] = run_dcm2niix(dcm2niixPath, dicomDir, workDir)
cmd = sprintf('%s -f converted_%%p_s%%s -i y -b y -ba n -z y -o %s %s', ...
    shell_quote(dcm2niixPath), shell_quote(workDir), shell_quote(dicomDir));
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
    base = strip_nii_ext(name);
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
        bvals = load_numeric_vector(paths.Bval);
        bvecCount = bvec_volume_count(paths.Bvec);
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
cleanupObj = onCleanup(@() cleanup_temp_dir(tempDir));
tempBase = fullfile(tempDir, strip_nii_ext(get_file_name(target)));
niftiwrite(data, tempBase, info, 'Compressed', true);
movefile([tempBase, '.nii.gz'], target, 'f');
clear cleanupObj;
cleanup_temp_dir(tempDir);
end

function augment_final_json(jsonPath, opts, result, directCopy)
metadata = jsondecode(fileread(jsonPath));
metadata.DicomDwiConversion = true;
metadata.DicomDwiConversionSource = opts.DicomDir;
metadata.DicomDwiConversionDecision = result.Decision;
metadata.DicomDwiConversionDirectCopy = directCopy;
metadata.DicomDwiConversionDcm2niixPath = result.Dcm2niixPath;
metadata.DicomDwiConversionDcm2niixSource = result.Dcm2niixSource;
metadata.DicomDwiConversionQcJson = result.QcJson;
metadata.DicomDwiConversionConvertedImageSize = result.ConvertedImageSize;
metadata.DicomDwiConversionOutputImageSize = result.OutputImageSize;
write_json(jsonPath, metadata);
end

function write_qc_json(qcJson, opts, result, candidate)
qc = struct();
qc.Status = result.Status;
qc.Message = result.Message;
qc.DicomDir = opts.DicomDir;
qc.OutputDir = opts.OutputDir;
qc.OutputBase = opts.OutputBase;
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
write_json(qcJson, qc);
end

function validate_final_outputs(paths)
must_be_file(paths.Nifti, 'output NIfTI');
must_be_file(paths.Json, 'output JSON');
must_be_file(paths.Bval, 'output bval');
must_be_file(paths.Bvec, 'output bvec');

info = niftiinfo(paths.Nifti);
imageSize = double(info.ImageSize);
if numel(imageSize) < 4
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:OutputNot4D', ...
        'Output DWI is not 4D: %s', paths.Nifti);
end
bvals = load_numeric_vector(paths.Bval);
bvecCount = bvec_volume_count(paths.Bvec);
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

function vals = load_numeric_vector(path)
vals = load(path);
vals = vals(:)';
if isempty(vals) || ~isnumeric(vals)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:InvalidNumericVector', ...
        'Could not read numeric values from %s', path);
end
end

function count = bvec_volume_count(path)
bvec = load(path);
if size(bvec, 1) == 3
    count = size(bvec, 2);
elseif size(bvec, 2) == 3
    count = size(bvec, 1);
else
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:InvalidBvec', ...
        'bvec file must be 3 x N or N x 3: %s', path);
end
end

function write_json(path, data)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:CannotWriteJson', ...
        'Cannot write JSON: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
try
    txt = jsonencode(data, 'PrettyPrint', true);
catch
    txt = jsonencode(data);
end
fprintf(fid, '%s\n', txt);
clear cleanupObj;
end

function message = compact_message(message)
message = char(string(message));
message = regexprep(message, '\s+', ' ');
if numel(message) > 500
    message = [message(1:500), '...'];
end
end

function base = strip_nii_ext(name)
base = regexprep(name, '\.nii(\.gz)?$', '');
end

function name = get_file_name(path)
[~, name, ext] = fileparts(path);
if strcmp(ext, '.gz')
    [~, innerName, innerExt] = fileparts(name);
    name = [innerName, innerExt, ext];
else
    name = [name, ext];
end
end

function ensure_dir(path)
if ~isfolder(path)
    mkdir(path);
end
end

function cleanup_temp_dir(path)
if ~isempty(path) && isfolder(path)
    rmdir(path, 's');
end
end

function must_be_file(path, label)
if ~isfile(path)
    error('mh_fiber_convert_dicom_dwi_to_leaddbs:MissingFile', ...
        'Missing %s: %s', label, path);
end
end

function quoted = shell_quote(path)
quoted = ['''', strrep(path, '''', '''"''"'''), ''''];
end
