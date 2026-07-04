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
geometry = attach_dicom_orientation_metadata(geometry, opts);

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
result.AffineSource = geometry.MosaicAffineSource;
result.AffineOriginPolicy = geometry.AffineOriginPolicy;
result.BvecValidationMedianError = geometry.BvecValidationMedianError;
result.BvecValidationMaxError = geometry.BvecValidationMaxError;
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

function geometry = attach_dicom_orientation_metadata(geometry, opts)
geometry.MosaicAffineSource = 'source_header';
geometry.AffineOriginPolicy = 'source_header';
geometry.ImageOrientationPatient = [];
geometry.VoxelSpacing = [];
geometry.SliceNormal = [];
geometry.VoxelToWorldTransform = [];
geometry.BvecTransformApplied = [];
geometry.BvecValidationMedianError = NaN;
geometry.BvecValidationMaxError = NaN;
geometry.BvecValidationStatus = 'not_run';

if isempty(opts.DicomDir)
    return;
end

dicomMeta = read_dicom_metadata(opts.DicomDir);
validate_dicom_geometry(geometry, dicomMeta);
geometry.ImageOrientationPatient = [dicomMeta.RowDirection, dicomMeta.ColumnDirection];
geometry.VoxelSpacing = dicomMeta.VoxelSpacing;
geometry.SliceNormal = dicomMeta.SliceNormal;
geometry.VoxelToWorldTransform = dicom_voxel_to_world_transform(geometry, dicomMeta);
geometry.MosaicAffineSource = 'dicom_orientation';
geometry.AffineOriginPolicy = dicomMeta.AffineOriginPolicy;
geometry.BvecTransformApplied = dicomMeta.BvecTransform;

validation = validate_bvec_against_dicom(opts.SourceBvec, geometry, dicomMeta);
geometry.BvecValidationMedianError = validation.MedianError;
geometry.BvecValidationMaxError = validation.MaxError;
geometry.BvecValidationStatus = validation.Status;
end

function dicomMeta = read_dicom_metadata(dicomDir)
files = list_files_recursive(dicomDir);
firstInfo = [];
firstPath = '';
rows = [];
for i = 1:numel(files)
    path = files{i};
    [~, name] = fileparts(path);
    if startsWith(name, '._')
        continue;
    end
    try
        info = dicominfo(path);
    catch
        continue;
    end
    if isempty(firstInfo)
        firstInfo = info;
        firstPath = path;
    end
    if isfield(info, 'InstanceNumber') && isfield(info, 'DiffusionBValue') && ...
            isfield(info, 'DiffusionGradientOrientation')
        gradient = double(info.DiffusionGradientOrientation(:)');
        if numel(gradient) >= 3
            rows(end + 1, :) = [double(info.InstanceNumber), ...
                double(info.DiffusionBValue), gradient(1:3)]; %#ok<AGROW>
        end
    end
end

if isempty(firstInfo)
    error('mh_fiber_reconstruct_mosaic_dwi:NoReadableDicom', ...
        'No readable DICOM file was found under: %s', dicomDir);
end
if isempty(rows)
    error('mh_fiber_reconstruct_mosaic_dwi:MissingDiffusionGradients', ...
        'No DICOM diffusion gradients were found under: %s', dicomDir);
end
rows = sortrows(rows, 1);

if ~isfield(firstInfo, 'ImageOrientationPatient')
    error('mh_fiber_reconstruct_mosaic_dwi:MissingImageOrientation', ...
        'ImageOrientationPatient is required to reconstruct mosaic affine: %s', firstPath);
end

iop = double(firstInfo.ImageOrientationPatient(:));
rowDirection = normalize_vector(iop(1:3));
columnDirection = normalize_vector(iop(4:6));
sliceNormal = normalize_vector(cross(rowDirection, columnDirection));
voxelSpacing = dicom_voxel_spacing(firstInfo);
[transform, originPolicy] = bvec_transform_from_dicom(rowDirection, columnDirection, sliceNormal);

dicomMeta = struct();
dicomMeta.DicomDir = dicomDir;
dicomMeta.DicomExample = firstPath;
dicomMeta.RowDirection = rowDirection(:)';
dicomMeta.ColumnDirection = columnDirection(:)';
dicomMeta.SliceNormal = sliceNormal(:)';
dicomMeta.VoxelSpacing = voxelSpacing;
dicomMeta.DiffusionRows = rows;
dicomMeta.BvecTransform = transform;
dicomMeta.HasImagePositionPatient = isfield(firstInfo, 'ImagePositionPatient');
if dicomMeta.HasImagePositionPatient
    dicomMeta.ImagePositionPatient = double(firstInfo.ImagePositionPatient(:)');
    dicomMeta.AffineOriginPolicy = 'dicom_ipp_first_voxel';
else
    dicomMeta.ImagePositionPatient = [];
    dicomMeta.AffineOriginPolicy = originPolicy;
end
if isfield(firstInfo, 'Private_0065_1050')
    dicomMeta.PrivateSliceCount = double(firstInfo.Private_0065_1050);
else
    dicomMeta.PrivateSliceCount = NaN;
end
if isfield(firstInfo, 'Private_0065_1071')
    dicomMeta.PrivateVolumeCount = double(firstInfo.Private_0065_1071);
else
    dicomMeta.PrivateVolumeCount = NaN;
end
end

function files = list_files_recursive(rootDir)
entries = dir(rootDir);
files = {};
for i = 1:numel(entries)
    name = entries(i).name;
    if strcmp(name, '.') || strcmp(name, '..')
        continue;
    end
    path = fullfile(entries(i).folder, name);
    if entries(i).isdir
        files = [files, list_files_recursive(path)]; %#ok<AGROW>
    else
        files{end + 1} = path; %#ok<AGROW>
    end
end
end

function voxelSpacing = dicom_voxel_spacing(info)
if isfield(info, 'PixelSpacing')
    spacing2d = double(info.PixelSpacing(:)');
else
    error('mh_fiber_reconstruct_mosaic_dwi:MissingPixelSpacing', ...
        'PixelSpacing is required to reconstruct mosaic affine.');
end

if isfield(info, 'SpacingBetweenSlices')
    sliceSpacing = double(info.SpacingBetweenSlices);
elseif isfield(info, 'SliceThickness')
    sliceSpacing = double(info.SliceThickness);
elseif isfield(info, 'Private_0065_1049')
    privateSpacing = double(info.Private_0065_1049(:)');
    sliceSpacing = privateSpacing(min(3, numel(privateSpacing)));
else
    error('mh_fiber_reconstruct_mosaic_dwi:MissingSliceSpacing', ...
        'SpacingBetweenSlices or SliceThickness is required to reconstruct mosaic affine.');
end

voxelSpacing = [spacing2d(2), spacing2d(1), sliceSpacing];
end

function validate_dicom_geometry(geometry, dicomMeta)
if ~isnan(dicomMeta.PrivateSliceCount) && round(dicomMeta.PrivateSliceCount) ~= geometry.SliceCount
    error('mh_fiber_reconstruct_mosaic_dwi:DicomSliceCountMismatch', ...
        'DICOM private slice count (%g) does not match inferred slice count (%d).', ...
        dicomMeta.PrivateSliceCount, geometry.SliceCount);
end
if ~isnan(dicomMeta.PrivateVolumeCount) && round(dicomMeta.PrivateVolumeCount) ~= geometry.VolumeCount
    error('mh_fiber_reconstruct_mosaic_dwi:DicomVolumeCountMismatch', ...
        'DICOM private volume count (%g) does not match inferred volume count (%d).', ...
        dicomMeta.PrivateVolumeCount, geometry.VolumeCount);
end
if size(dicomMeta.DiffusionRows, 1) ~= geometry.VolumeCount
    error('mh_fiber_reconstruct_mosaic_dwi:DicomGradientCountMismatch', ...
        'DICOM diffusion gradient count (%d) does not match volume count (%d).', ...
        size(dicomMeta.DiffusionRows, 1), geometry.VolumeCount);
end
end

function transform = dicom_voxel_to_world_transform(geometry, dicomMeta)
rowRas = lps_to_ras(dicomMeta.RowDirection);
columnRas = lps_to_ras(dicomMeta.ColumnDirection);
normalRas = lps_to_ras(dicomMeta.SliceNormal);
spacing = dicomMeta.VoxelSpacing;

axis1 = spacing(1) .* rowRas;
axis2 = -spacing(2) .* columnRas;
axis3 = spacing(3) .* normalRas;

if dicomMeta.HasImagePositionPatient
    firstVoxelWorld = lps_to_ras(dicomMeta.ImagePositionPatient);
    origin = firstVoxelWorld - axis1 - axis2 - axis3;
else
    imageSize = geometry.OutputImageSize(1:3);
    centerVoxel = (double(imageSize) + 1) ./ 2;
    origin = -centerVoxel(1) .* axis1 - centerVoxel(2) .* axis2 - ...
        centerVoxel(3) .* axis3;
end

transform = [axis1(:)', 0; axis2(:)', 0; axis3(:)', 0; origin(:)', 1];
end

function [transform, originPolicy] = bvec_transform_from_dicom(rowDirection, columnDirection, sliceNormal)
transform = diag([1, -1, 1]) * [rowDirection(:), columnDirection(:), sliceNormal(:)]';
originPolicy = 'centered_no_dicom_ipp';
end

function validation = validate_bvec_against_dicom(sourceBvec, geometry, dicomMeta)
bvec = load_bvec_matrix(sourceBvec);
if size(bvec, 2) ~= geometry.VolumeCount
    error('mh_fiber_reconstruct_mosaic_dwi:BvecVolumeMismatch', ...
        'bvec count (%d) does not match volume count (%d).', ...
        size(bvec, 2), geometry.VolumeCount);
end

bvals = dicomMeta.DiffusionRows(:, 2)';
dicomGradients = dicomMeta.DiffusionRows(:, 3:5)';
expected = dicomMeta.BvecTransform * dicomGradients;
expected = normalize_columns(expected);
bvec = normalize_columns(bvec);
nonB0 = bvals >= 10 & sqrt(sum(dicomGradients.^2, 1)) > 0.5;
errors = sqrt(sum((expected(:, nonB0) - bvec(:, nonB0)).^2, 1));
validation = struct();
validation.MedianError = median(errors);
validation.MaxError = max(errors);
validation.Status = 'passed';
if validation.MedianError > 1e-5 || validation.MaxError > 1e-4
    error('mh_fiber_reconstruct_mosaic_dwi:BvecDicomMismatch', ...
        ['DICOM gradient to bvec validation failed: median error %.6g, ', ...
        'max error %.6g.'], validation.MedianError, validation.MaxError);
end
end

function bvec = load_bvec_matrix(path)
bvec = readmatrix(path, 'FileType', 'text');
if size(bvec, 1) ~= 3 && size(bvec, 2) == 3
    bvec = bvec';
end
if size(bvec, 1) ~= 3
    error('mh_fiber_reconstruct_mosaic_dwi:InvalidBvec', ...
        'bvec file must contain a 3 x N direction matrix: %s', path);
end
end

function matrix = normalize_columns(matrix)
norms = sqrt(sum(matrix.^2, 1));
idx = norms > 0;
matrix(:, idx) = matrix(:, idx) ./ norms(idx);
end

function vector = normalize_vector(vector)
vector = double(vector(:)');
normValue = norm(vector);
if normValue == 0
    error('mh_fiber_reconstruct_mosaic_dwi:InvalidDirectionVector', ...
        'DICOM direction vector has zero length.');
end
vector = vector ./ normValue;
end

function ras = lps_to_ras(lps)
lps = double(lps(:)');
ras = [-lps(1), -lps(2), lps(3)];
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
outInfo.PixelDimensions = output_pixel_dimensions(sourceInfo, outInfo, geometry);
outInfo.Datatype = class(data);
outInfo.BitsPerPixel = bits_per_pixel(class(data));
outInfo.Description = 'SaveBySlc mosaic reconstructed DWI';
if ~isempty(geometry.VoxelToWorldTransform)
    outInfo.Transform = affine3d(geometry.VoxelToWorldTransform);
end

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

function pixdim = output_pixel_dimensions(sourceInfo, outInfo, geometry)
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
if isfield(geometry, 'VoxelSpacing') && numel(geometry.VoxelSpacing) >= 3
    pixdim(1:3) = geometry.VoxelSpacing(1:3);
end
if geometry.VolumeCount > 1 && numel(sourcePixdim) >= 4
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
metadata.MosaicAffineSource = geometry.MosaicAffineSource;
metadata.AffineOriginPolicy = geometry.AffineOriginPolicy;
metadata.ImageOrientationPatient = geometry.ImageOrientationPatient;
metadata.VoxelSpacing = geometry.VoxelSpacing;
metadata.SliceNormal = geometry.SliceNormal;
metadata.VoxelToWorldTransform = geometry.VoxelToWorldTransform;
metadata.BvecTransformApplied = geometry.BvecTransformApplied;
metadata.BvecValidationStatus = geometry.BvecValidationStatus;
metadata.BvecValidationMedianError = geometry.BvecValidationMedianError;
metadata.BvecValidationMaxError = geometry.BvecValidationMaxError;
metadata.InPlaneTransform = 'identity';
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
qc.MosaicAffineSource = geometry.MosaicAffineSource;
qc.AffineOriginPolicy = geometry.AffineOriginPolicy;
qc.ImageOrientationPatient = geometry.ImageOrientationPatient;
qc.VoxelSpacing = geometry.VoxelSpacing;
qc.SliceNormal = geometry.SliceNormal;
qc.VoxelToWorldTransform = geometry.VoxelToWorldTransform;
qc.BvecTransformApplied = geometry.BvecTransformApplied;
qc.BvecValidationStatus = geometry.BvecValidationStatus;
qc.BvecValidationMedianError = geometry.BvecValidationMedianError;
qc.BvecValidationMaxError = geometry.BvecValidationMaxError;
qc.InPlaneTransform = 'identity';
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
