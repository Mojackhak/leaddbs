function result = mh_fiber_reorient_dwi_image_content(varargin)
% Apply image-content orientation correction to a DWI NIfTI and sidecars.

parser = inputParser;
parser.addParameter('SourceNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceJson', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceBval', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceBvec', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputBase', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Transform', 'identity', @(x) ischar(x) || isstring(x));
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

sourceNifti = char(string(opts.SourceNifti));
sourceJson = char(string(opts.SourceJson));
sourceBval = char(string(opts.SourceBval));
sourceBvec = char(string(opts.SourceBvec));
outputDir = char(string(opts.OutputDir));
outputBase = char(string(opts.OutputBase));
transformName = validate_transform_name(opts.Transform);
force = logical(opts.Force);

mh_util_must_be_file(sourceNifti, 'source DWI NIfTI', ...
    'mh_fiber_reorient_dwi_image_content:MissingSource');
mh_util_must_be_file(sourceBval, 'source bval', ...
    'mh_fiber_reorient_dwi_image_content:MissingSource');
mh_util_must_be_file(sourceBvec, 'source bvec', ...
    'mh_fiber_reorient_dwi_image_content:MissingSource');
if ~isempty(sourceJson)
    mh_util_must_be_file(sourceJson, 'source JSON', ...
        'mh_fiber_reorient_dwi_image_content:MissingSource');
end
if isempty(outputDir) || isempty(outputBase)
    error('mh_fiber_reorient_dwi_image_content:MissingOutput', ...
        'OutputDir and OutputBase must not be empty.');
end

mh_util_make_dir(outputDir);
paths = output_paths(outputDir, outputBase, sourceNifti, sourceJson);
assert_outputs_available(paths, force);

niftiResult = mh_fiber_reorient_nifti_content( ...
    'SourceNifti', sourceNifti, ...
    'OutputNifti', paths.Nifti, ...
    'Transform', transformName, ...
    'Force', force);

copyfile(sourceBval, paths.Bval, 'f');
write_corrected_bvec(sourceBvec, paths.Bvec, transformName);
if ~isempty(sourceJson)
    write_corrected_json(sourceJson, paths.Json, opts, paths, transformName);
end

validate_counts(paths.Nifti, paths.Bval, paths.Bvec);

result = struct();
result.Nifti = paths.Nifti;
result.Json = paths.Json;
result.Bval = paths.Bval;
result.Bvec = paths.Bvec;
result.Transform = transformName;
result.BvecMatrix = bvec_transform_matrix(transformName);
result.SourceSha256 = niftiResult.SourceSha256;
result.OutputSha256 = niftiResult.OutputSha256;
end

function transformName = validate_transform_name(value)
transformName = validatestring(char(string(value)), ...
    {'identity', 'flipY', 'flipZ', 'rotX180'}, ...
    'mh_fiber_reorient_dwi_image_content', 'Transform');
end

function paths = output_paths(outputDir, outputBase, sourceNifti, sourceJson)
paths = struct();
if endsWith(sourceNifti, '.nii.gz')
    niiExt = '.nii.gz';
elseif endsWith(sourceNifti, '.nii')
    niiExt = '.nii';
else
    error('mh_fiber_reorient_dwi_image_content:UnsupportedNiftiExtension', ...
        'Source NIfTI must end with .nii or .nii.gz: %s', sourceNifti);
end
paths.Nifti = fullfile(outputDir, [outputBase, niiExt]);
paths.Bval = fullfile(outputDir, [outputBase, '.bval']);
paths.Bvec = fullfile(outputDir, [outputBase, '.bvec']);
if isempty(sourceJson)
    paths.Json = '';
else
    paths.Json = fullfile(outputDir, [outputBase, '.json']);
end
end

function assert_outputs_available(paths, force)
targets = {paths.Nifti, paths.Bval, paths.Bvec};
if ~isempty(paths.Json)
    targets{end + 1} = paths.Json;
end
for i = 1:numel(targets)
    if isfile(targets{i}) && ~force
        error('mh_fiber_reorient_dwi_image_content:OutputExists', ...
            'Output exists. Use Force=true to overwrite: %s', targets{i});
    end
end
end

function write_corrected_bvec(sourceBvec, targetBvec, transformName)
bvec = readmatrix(sourceBvec, 'FileType', 'text');
transposed = false;
if size(bvec, 1) ~= 3 && size(bvec, 2) == 3
    bvec = bvec';
    transposed = true;
end
if size(bvec, 1) ~= 3
    error('mh_fiber_reorient_dwi_image_content:InvalidBvec', ...
        'bvec file must be 3 x N or N x 3: %s', sourceBvec);
end

corrected = bvec_transform_matrix(transformName) * bvec;
if transposed
    corrected = corrected';
end
writematrix(corrected, targetBvec, 'FileType', 'text', 'Delimiter', ' ');
end

function matrix = bvec_transform_matrix(transformName)
switch transformName
    case 'identity'
        matrix = eye(3);
    case 'flipY'
        matrix = diag([1 -1 1]);
    case 'flipZ'
        matrix = diag([1 1 -1]);
    case 'rotX180'
        matrix = diag([1 -1 -1]);
    otherwise
        error('mh_fiber_reorient_dwi_image_content:UnsupportedTransform', ...
            'Unsupported transform: %s', transformName);
end
end

function write_corrected_json(sourceJson, targetJson, opts, paths, transformName)
metadata = jsondecode(fileread(sourceJson));
metadata.ImageContentOrientationCorrection = true;
metadata.OrientationCorrectionTransform = transformName;
metadata.OrientationCorrectionBvecMatrix = bvec_transform_matrix(transformName);
metadata.OrientationCorrectionSourceNifti = char(string(opts.SourceNifti));
metadata.OrientationCorrectionSourceJson = char(string(opts.SourceJson));
metadata.OrientationCorrectionSourceBval = char(string(opts.SourceBval));
metadata.OrientationCorrectionSourceBvec = char(string(opts.SourceBvec));
metadata.OrientationCorrectionSourceSha256 = struct( ...
    'Nifti', mh_fiber_file_sha256(opts.SourceNifti), ...
    'Json', mh_fiber_file_sha256(opts.SourceJson), ...
    'Bval', mh_fiber_file_sha256(opts.SourceBval), ...
    'Bvec', mh_fiber_file_sha256(opts.SourceBvec));
metadata.OrientationCorrectionOutputNifti = paths.Nifti;
metadata.OrientationCorrectionOutputBval = paths.Bval;
metadata.OrientationCorrectionOutputBvec = paths.Bvec;
metadata.OrientationCorrectionDateTime = char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss'));

fid = fopen(targetJson, 'w');
if fid < 0
    error('mh_fiber_reorient_dwi_image_content:JsonWriteFailed', ...
        'Could not write JSON: %s', targetJson);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(metadata, 'PrettyPrint', true));
end

function validate_counts(niftiPath, bvalPath, bvecPath)
info = niftiinfo(niftiPath);
imageSize = info.ImageSize;
if numel(imageSize) < 4
    error('mh_fiber_reorient_dwi_image_content:Not4D', ...
        'DWI must be 4D: %s', niftiPath);
end
volumeCount = imageSize(4);
bvals = mh_fiber_load_bval(bvalPath);
bvecCount = mh_fiber_bvec_count(bvecPath);
if numel(bvals) ~= volumeCount
    error('mh_fiber_reorient_dwi_image_content:BvalMismatch', ...
        'bval count (%d) does not match volume count (%d).', ...
        numel(bvals), volumeCount);
end
if bvecCount ~= volumeCount
    error('mh_fiber_reorient_dwi_image_content:BvecMismatch', ...
        'bvec count (%d) does not match volume count (%d).', ...
        bvecCount, volumeCount);
end
end
