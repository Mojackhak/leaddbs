function result = mh_fiber_reconstruct_mosaic_dwi(varargin)
% Reconstruct one Siemens SaveBySlc mosaic DWI NIfTI into a 4D slice stack.

parser = inputParser;
parser.FunctionName = 'mh_fiber_reconstruct_mosaic_dwi';
parser.addParameter('SourceNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceJson', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceBval', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceBvec', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputBase', '', @(x) ischar(x) || isstring(x));
parser.addParameter('DicomDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('ReferenceNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('TileSize', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 2));
parser.addParameter('TileGrid', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 2));
parser.addParameter('SliceCount', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('TileOrder', 'row_major_right_to_left', @(x) ischar(x) || isstring(x));
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = normalize_options(parser.Results);

validate_required_options(opts);
geometry = mh_fiber_infer_mosaic_geometry(opts.SourceNifti, opts.SourceBval, opts.SourceBvec, ...
    'DicomDir', opts.DicomDir, ...
    'ReferenceNifti', opts.ReferenceNifti, ...
    'TileSize', opts.TileSize, ...
    'TileGrid', opts.TileGrid, ...
    'SliceCount', opts.SliceCount);
geometry.TileOrder = opts.TileOrder;

sourceInfo = niftiinfo(opts.SourceNifti);
sourceSize = double(sourceInfo.ImageSize);
if numel(sourceSize) < 4
    sourceSize(4) = 1;
end
if sourceSize(3) ~= 1
    error('mh_fiber_reconstruct_mosaic_dwi:NotSingleSliceMosaic', ...
        'Source NIfTI is not a single-slice mosaic candidate: %s', opts.SourceNifti);
end

paths = output_paths(opts.OutputDir, opts.OutputBase);
result = base_result(opts, paths, geometry);
if opts.DryRun
    result.Status = 'dry_run';
    result.Message = 'Mosaic reconstruction geometry inferred; no files written.';
    return;
end

ensure_output_available(paths, opts.Force);
mh_util_make_dir(opts.OutputDir);

mosaicData = niftiread(opts.SourceNifti);
if ndims(mosaicData) < 4
    mosaicData = reshape(mosaicData, size(mosaicData, 1), size(mosaicData, 2), size(mosaicData, 3), 1);
end

reconstructed = reconstruct_all_volumes(mosaicData, geometry, opts.Parallel, opts.ParallelWorkers);
write_reconstructed_nifti(reconstructed, sourceInfo, opts.ReferenceNifti, paths.Nifti, geometry);
copyfile(opts.SourceBval, paths.Bval, 'f');
copyfile(opts.SourceBvec, paths.Bvec, 'f');
write_augmented_json(opts.SourceJson, paths.Json, opts, geometry, paths);
write_qc_json(paths.QcJson, opts, geometry, paths);

validate_output(paths, geometry);
result.Status = 'reconstructed';
result.Message = 'ok';
result.OutputNifti = paths.Nifti;
result.OutputJson = paths.Json;
result.OutputBval = paths.Bval;
result.OutputBvec = paths.Bvec;
result.QcJson = paths.QcJson;
end

function opts = normalize_options(opts)
fields = {'SourceNifti', 'SourceJson', 'SourceBval', 'SourceBvec', 'OutputDir', ...
    'OutputBase', 'DicomDir', 'ReferenceNifti'};
for i = 1:numel(fields)
    opts.(fields{i}) = char(string(opts.(fields{i})));
end
opts.TileOrder = validatestring(char(string(opts.TileOrder)), ...
    {'row_major_right_to_left', 'row_major_left_to_right'}, ...
    'mh_fiber_reconstruct_mosaic_dwi', 'TileOrder');
opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
opts.Force = logical(opts.Force);
opts.DryRun = logical(opts.DryRun);
end

function validate_required_options(opts)
required = {'SourceNifti', 'SourceJson', 'SourceBval', 'SourceBvec', 'OutputDir', 'OutputBase'};
for i = 1:numel(required)
    if isempty(opts.(required{i}))
        error('mh_fiber_reconstruct_mosaic_dwi:MissingParameter', ...
            '%s must be provided.', required{i});
    end
end
mh_util_must_be_file(opts.SourceNifti, 'source NIfTI', ...
    'mh_fiber_reconstruct_mosaic_dwi:MissingFile');
mh_util_must_be_file(opts.SourceJson, 'source JSON', ...
    'mh_fiber_reconstruct_mosaic_dwi:MissingFile');
mh_util_must_be_file(opts.SourceBval, 'source bval', ...
    'mh_fiber_reconstruct_mosaic_dwi:MissingFile');
mh_util_must_be_file(opts.SourceBvec, 'source bvec', ...
    'mh_fiber_reconstruct_mosaic_dwi:MissingFile');
end

function paths = output_paths(outputDir, outputBase)
paths = struct();
paths.Nifti = fullfile(outputDir, [outputBase, '.nii.gz']);
paths.Json = fullfile(outputDir, [outputBase, '.json']);
paths.Bval = fullfile(outputDir, [outputBase, '.bval']);
paths.Bvec = fullfile(outputDir, [outputBase, '.bvec']);
paths.QcJson = fullfile(outputDir, [outputBase, '_mosaic_reconstruction_qc.json']);
end

function result = base_result(opts, paths, geometry)
result = struct();
result.Status = 'started';
result.Message = '';
result.SourceNifti = opts.SourceNifti;
result.SourceJson = opts.SourceJson;
result.SourceBval = opts.SourceBval;
result.SourceBvec = opts.SourceBvec;
result.DicomDir = opts.DicomDir;
result.ReferenceNifti = opts.ReferenceNifti;
result.OutputNifti = paths.Nifti;
result.OutputJson = paths.Json;
result.OutputBval = paths.Bval;
result.OutputBvec = paths.Bvec;
result.QcJson = paths.QcJson;
result.GeometrySource = geometry.GeometrySource;
result.TileSize = mat2str(geometry.TileSize);
result.TileGrid = mat2str(geometry.TileGrid);
result.TileOrder = geometry.TileOrder;
result.SliceCount = geometry.SliceCount;
result.VolumeCount = geometry.VolumeCount;
result.OutputImageSize = mat2str(geometry.OutputImageSize);
end

function ensure_output_available(paths, force)
targets = {paths.Nifti, paths.Json, paths.Bval, paths.Bvec, paths.QcJson};
for i = 1:numel(targets)
    if isfile(targets{i}) && ~force
        error('mh_fiber_reconstruct_mosaic_dwi:OutputExists', ...
            'Output already exists. Use Force=true to overwrite: %s', targets{i});
    end
end
end

function reconstructed = reconstruct_all_volumes(mosaicData, geometry, useParallel, workerCount)
outSize = geometry.OutputImageSize;
reconstructed = zeros(outSize, 'like', mosaicData);
volumeCount = geometry.VolumeCount;
useParallel = useParallel && volumeCount > 1 && mh_fiber_ensure_parallel_pool(workerCount);

if useParallel
    parfor volumeIndex = 1:volumeCount
        reconstructed(:, :, :, volumeIndex) = reconstruct_one_volume(mosaicData(:, :, 1, volumeIndex), geometry);
    end
else
    for volumeIndex = 1:volumeCount
        reconstructed(:, :, :, volumeIndex) = reconstruct_one_volume(mosaicData(:, :, 1, volumeIndex), geometry);
    end
end
end

function volume = reconstruct_one_volume(frame, geometry)
tileWidth = geometry.TileSize(1);
tileHeight = geometry.TileSize(2);
gridCols = geometry.TileGrid(1);
sliceCount = geometry.SliceCount;
volume = zeros(tileWidth, tileHeight, sliceCount, 'like', frame);

for sliceIndex = 1:sliceCount
    tileZero = sliceIndex - 1;
    tileRow = floor(tileZero / gridCols);
    switch geometry.TileOrder
        case 'row_major_right_to_left'
            tileCol = gridCols - 1 - mod(tileZero, gridCols);
        case 'row_major_left_to_right'
            tileCol = mod(tileZero, gridCols);
        otherwise
            error('mh_fiber_reconstruct_mosaic_dwi:InvalidTileOrder', ...
                'Unsupported TileOrder: %s', geometry.TileOrder);
    end
    xRange = (tileCol * tileWidth + 1):((tileCol + 1) * tileWidth);
    yRange = (tileRow * tileHeight + 1):((tileRow + 1) * tileHeight);
    volume(:, :, sliceIndex) = frame(xRange, yRange);
end
end

function write_reconstructed_nifti(data, sourceInfo, referenceNifti, outputPath, geometry)
outInfo = sourceInfo;
if ~isempty(referenceNifti)
    outInfo = niftiinfo(referenceNifti);
end

outInfo.Filename = outputPath;
outInfo.ImageSize = size(data);
outInfo.PixelDimensions = output_pixel_dimensions(sourceInfo, outInfo, geometry.VolumeCount);
outInfo.Datatype = class(data);
outInfo.BitsPerPixel = bits_per_pixel(class(data));
outInfo.Description = 'SaveBySlc mosaic reconstructed DWI';

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
    error('mh_fiber_reconstruct_mosaic_dwi:NiftiWriteFailed', ...
        'niftiwrite did not create expected file: %s', tempOutput);
end
movefile(tempOutput, outputPath, 'f');
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
error('mh_fiber_reconstruct_mosaic_dwi:NiftiWriteFailed', ...
    'niftiwrite did not create an uncompressed NIfTI near: %s', expectedPath);
end

function pixdim = output_pixel_dimensions(sourceInfo, outInfo, volumeCount)
sourcePixdim = double(sourceInfo.PixelDimensions);
if numel(sourcePixdim) < 3
    sourcePixdim(3) = sourcePixdim(min(numel(sourcePixdim), 1));
end
if numel(sourcePixdim) < 4
    sourcePixdim(4) = 1;
end

pixdim = sourcePixdim(1:4);
if isfield(outInfo, 'PixelDimensions') && numel(outInfo.PixelDimensions) >= 3
    refPixdim = double(outInfo.PixelDimensions);
    pixdim(1:min(numel(refPixdim), 4)) = refPixdim(1:min(numel(refPixdim), 4));
end
if volumeCount > 1 && numel(sourcePixdim) >= 4
    pixdim(4) = sourcePixdim(4);
end
end

function write_augmented_json(sourceJson, targetJson, opts, geometry, paths)
metadata = jsondecode(fileread(sourceJson));
metadata.MosaicReconstruction = true;
metadata.MosaicReconstructionSourceNifti = opts.SourceNifti;
metadata.MosaicReconstructionSourceJson = opts.SourceJson;
metadata.MosaicReconstructionSourceBval = opts.SourceBval;
metadata.MosaicReconstructionSourceBvec = opts.SourceBvec;
metadata.MosaicGeometrySource = geometry.GeometrySource;
metadata.MosaicTileSize = geometry.TileSize;
metadata.MosaicTileGrid = geometry.TileGrid;
metadata.MosaicTileOrder = geometry.TileOrder;
metadata.MosaicSliceCount = geometry.SliceCount;
metadata.MosaicVolumeCount = geometry.VolumeCount;
metadata.MosaicTileSlotCount = geometry.TileSlotCount;
metadata.MosaicUnusedTileCount = geometry.UnusedTileCount;
metadata.MosaicOutputImageSize = geometry.OutputImageSize;
metadata.MosaicReconstructionQcJson = paths.QcJson;
metadata.MosaicReconstructionWarning = geometry.Warning;
if isfield(geometry, 'DicomDir')
    metadata.MosaicDicomDir = geometry.DicomDir;
end
if isfield(geometry, 'ReferenceNifti')
    metadata.MosaicReferenceNifti = geometry.ReferenceNifti;
end
mh_util_write_json(targetJson, metadata, ...
    'mh_fiber_reconstruct_mosaic_dwi:CannotWriteJson');
end

function write_qc_json(qcJson, opts, geometry, paths)
qc = struct();
qc.Status = 'reconstructed';
qc.SourceNifti = opts.SourceNifti;
qc.SourceJson = opts.SourceJson;
qc.SourceBval = opts.SourceBval;
qc.SourceBvec = opts.SourceBvec;
qc.DicomDir = opts.DicomDir;
qc.ReferenceNifti = opts.ReferenceNifti;
qc.OutputNifti = paths.Nifti;
qc.OutputJson = paths.Json;
qc.OutputBval = paths.Bval;
qc.OutputBvec = paths.Bvec;
qc.GeometrySource = geometry.GeometrySource;
qc.SourceImageSize = geometry.SourceImageSize;
qc.OutputImageSize = geometry.OutputImageSize;
qc.TileSize = geometry.TileSize;
qc.TileGrid = geometry.TileGrid;
qc.TileOrder = geometry.TileOrder;
qc.SliceCount = geometry.SliceCount;
qc.VolumeCount = geometry.VolumeCount;
qc.TileSlotCount = geometry.TileSlotCount;
qc.UnusedTileCount = geometry.UnusedTileCount;
qc.Warning = geometry.Warning;
mh_util_write_json(qcJson, qc, ...
    'mh_fiber_reconstruct_mosaic_dwi:CannotWriteJson');
end

function validate_output(paths, geometry)
info = niftiinfo(paths.Nifti);
if ~isequal(double(info.ImageSize), geometry.OutputImageSize)
    error('mh_fiber_reconstruct_mosaic_dwi:OutputSizeMismatch', ...
        'Output size %s does not match expected %s.', ...
        mat2str(double(info.ImageSize)), mat2str(geometry.OutputImageSize));
end

bvals = mh_fiber_load_bval(paths.Bval);
bvecCount = mh_fiber_bvec_count(paths.Bvec);
if numel(bvals) ~= geometry.VolumeCount || bvecCount ~= geometry.VolumeCount
    error('mh_fiber_reconstruct_mosaic_dwi:OutputGradientMismatch', ...
        'Output gradient counts do not match reconstructed volume count.');
end
end

function bits = bits_per_pixel(className)
switch className
    case {'uint8', 'int8'}
        bits = 8;
    case {'uint16', 'int16'}
        bits = 16;
    case {'uint32', 'int32', 'single'}
        bits = 32;
    case {'uint64', 'int64', 'double'}
        bits = 64;
    otherwise
        bits = 32;
end
end
