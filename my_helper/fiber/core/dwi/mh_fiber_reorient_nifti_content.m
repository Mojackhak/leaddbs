function result = mh_fiber_reorient_nifti_content(varargin)
% Apply a same-grid image-content orientation correction to a NIfTI image.

parser = inputParser;
parser.addParameter('SourceNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Transform', 'identity', @(x) ischar(x) || isstring(x));
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

sourceNifti = char(string(opts.SourceNifti));
outputNifti = char(string(opts.OutputNifti));
transformName = validate_transform_name(opts.Transform);
force = logical(opts.Force);

mh_util_must_be_file(sourceNifti, 'source NIfTI', ...
    'mh_fiber_reorient_nifti_content:MissingSource');
if isempty(outputNifti)
    error('mh_fiber_reorient_nifti_content:MissingOutput', ...
        'OutputNifti must not be empty.');
end
if isfile(outputNifti) && ~force
    error('mh_fiber_reorient_nifti_content:OutputExists', ...
        'Output NIfTI already exists. Use Force=true to overwrite: %s', outputNifti);
end

info = niftiinfo(sourceNifti);
data = niftiread(info);
data = apply_content_transform(data, transformName);
write_nifti_like(data, info, outputNifti, transformName);

result = struct();
result.SourceNifti = sourceNifti;
result.OutputNifti = outputNifti;
result.Transform = transformName;
result.SourceSha256 = mh_fiber_file_sha256(sourceNifti);
result.OutputSha256 = mh_fiber_file_sha256(outputNifti);
end

function transformName = validate_transform_name(value)
transformName = validatestring(char(string(value)), ...
    {'identity', 'flipY', 'flipZ', 'rotX180', 'rotZ180'}, ...
    'mh_fiber_reorient_nifti_content', 'Transform');
end

function data = apply_content_transform(data, transformName)
switch transformName
    case 'identity'
        return;
    case 'flipY'
        data = flip(data, 2);
    case 'flipZ'
        data = flip(data, 3);
    case 'rotX180'
        data = flip(flip(data, 2), 3);
    case 'rotZ180'
        data = flip(flip(data, 1), 2);
    otherwise
        error('mh_fiber_reorient_nifti_content:UnsupportedTransform', ...
            'Unsupported transform: %s', transformName);
end
end

function write_nifti_like(data, sourceInfo, outputPath, transformName)
mh_util_make_dir(fileparts(outputPath));

outInfo = sourceInfo;
outInfo.Filename = outputPath;
outInfo.ImageSize = size(data);
outInfo.Datatype = class(data);
outInfo.BitsPerPixel = bits_per_pixel(class(data));
outInfo.Description = sprintf('Image-content orientation correction: %s', transformName);

if endsWith(outputPath, '.nii.gz')
    tempDir = tempname;
    mkdir(tempDir);
    cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(tempDir));
    tempBase = fullfile(tempDir, mh_fiber_nii_basename(outputPath));
    tempNii = [tempBase, '.nii'];
    outInfo.Filename = tempNii;
    niftiwrite(data, tempNii, outInfo, 'Compressed', false);
    writtenNii = find_written_nifti(tempNii);
    gzip(writtenNii);
    tempOutput = [writtenNii, '.gz'];
    if ~isfile(tempOutput)
        error('mh_fiber_reorient_nifti_content:NiftiWriteFailed', ...
            'niftiwrite did not create expected file: %s', tempOutput);
    end
    movefile(tempOutput, outputPath, 'f');
    clear cleanupObj;
    mh_fiber_cleanup_temp_dir(tempDir);
else
    outInfo.Filename = outputPath;
    niftiwrite(data, outputPath, outInfo, 'Compressed', false);
end
end

function writtenNii = find_written_nifti(expectedPath)
candidates = {expectedPath, [expectedPath, '.nii']};
for i = 1:numel(candidates)
    if isfile(candidates{i})
        writtenNii = candidates{i};
        return;
    end
end
error('mh_fiber_reorient_nifti_content:NiftiWriteFailed', ...
    'niftiwrite did not create an uncompressed NIfTI near: %s', expectedPath);
end

function bits = bits_per_pixel(datatype)
switch datatype
    case {'uint8', 'int8', 'logical'}
        bits = 8;
    case {'uint16', 'int16'}
        bits = 16;
    case {'uint32', 'int32', 'single'}
        bits = 32;
    case {'uint64', 'int64', 'double'}
        bits = 64;
    otherwise
        bits = 0;
end
end
