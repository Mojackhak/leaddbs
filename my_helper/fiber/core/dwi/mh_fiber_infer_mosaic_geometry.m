function geometry = mh_fiber_infer_mosaic_geometry(sourceNifti, sourceBval, sourceBvec, varargin)
% Infer Siemens SaveBySlc mosaic DWI tile geometry.

parser = inputParser;
parser.FunctionName = 'mh_fiber_infer_mosaic_geometry';
parser.addRequired('sourceNifti', @(x) ischar(x) || isstring(x));
parser.addRequired('sourceBval', @(x) ischar(x) || isstring(x));
parser.addRequired('sourceBvec', @(x) ischar(x) || isstring(x));
parser.addParameter('DicomDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('ReferenceNifti', '', @(x) ischar(x) || isstring(x));
parser.addParameter('TileSize', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 2));
parser.addParameter('TileGrid', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 2));
parser.addParameter('SliceCount', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.parse(sourceNifti, sourceBval, sourceBvec, varargin{:});
opts = parser.Results;

sourceNifti = char(string(sourceNifti));
sourceBval = char(string(sourceBval));
sourceBvec = char(string(sourceBvec));
dicomDir = char(string(opts.DicomDir));
referenceNifti = char(string(opts.ReferenceNifti));

must_be_file(sourceNifti, 'source NIfTI');
must_be_file(sourceBval, 'source bval');
must_be_file(sourceBvec, 'source bvec');

info = niftiinfo(sourceNifti);
imageSize = double(info.ImageSize);
if numel(imageSize) < 3
    error('mh_fiber_infer_mosaic_geometry:InvalidNifti', ...
        'Source NIfTI must have at least three dimensions: %s', sourceNifti);
end
if numel(imageSize) < 4
    imageSize(4) = 1;
end

bvals = load_numeric_vector(sourceBval);
bvecCount = bvec_volume_count(sourceBvec);
volumeCount = imageSize(4);
if numel(bvals) ~= volumeCount
    error('mh_fiber_infer_mosaic_geometry:BvalVolumeMismatch', ...
        'bval count (%d) does not match NIfTI volume count (%d): %s', ...
        numel(bvals), volumeCount, sourceBval);
end
if bvecCount ~= volumeCount
    error('mh_fiber_infer_mosaic_geometry:BvecVolumeMismatch', ...
        'bvec count (%d) does not match NIfTI volume count (%d): %s', ...
        bvecCount, volumeCount, sourceBvec);
end

geometry = base_geometry(sourceNifti, sourceBval, sourceBvec, imageSize, volumeCount);

if ~isempty(opts.TileSize) && ~isempty(opts.TileGrid) && ~isempty(opts.SliceCount)
    geometry.TileSize = round(double(opts.TileSize(:)'));
    geometry.TileGrid = round(double(opts.TileGrid(:)'));
    geometry.SliceCount = round(double(opts.SliceCount));
    geometry.GeometrySource = 'explicit';
elseif ~isempty(dicomDir)
    geometry = infer_from_dicom(geometry, dicomDir);
elseif ~isempty(referenceNifti)
    geometry = infer_from_reference(geometry, referenceNifti);
else
    error('mh_fiber_infer_mosaic_geometry:MissingGeometrySource', ...
        ['Provide DicomDir, ReferenceNifti, or explicit TileSize, TileGrid, ', ...
        'and SliceCount values.']);
end

geometry = validate_geometry(geometry);
end

function geometry = base_geometry(sourceNifti, sourceBval, sourceBvec, imageSize, volumeCount)
geometry = struct();
geometry.SourceNifti = sourceNifti;
geometry.SourceBval = sourceBval;
geometry.SourceBvec = sourceBvec;
geometry.SourceImageSize = imageSize;
geometry.MosaicSize = imageSize(1:2);
geometry.SourceSliceCount = imageSize(3);
geometry.VolumeCount = volumeCount;
geometry.TileSize = [];
geometry.TileGrid = [];
geometry.SliceCount = [];
geometry.TileSlotCount = [];
geometry.UnusedTileCount = [];
geometry.GeometrySource = '';
geometry.DicomDir = '';
geometry.ReferenceNifti = '';
geometry.Warning = '';
end

function geometry = infer_from_dicom(geometry, dicomDir)
if ~isfolder(dicomDir)
    error('mh_fiber_infer_mosaic_geometry:MissingDicomDir', ...
        'DICOM directory does not exist: %s', dicomDir);
end

[dicomInfo, dicomPath] = read_first_dicom(dicomDir);
if ~isfield(dicomInfo, 'Rows') || ~isfield(dicomInfo, 'Columns')
    error('mh_fiber_infer_mosaic_geometry:MissingDicomFrameSize', ...
        'DICOM Rows and Columns are required: %s', dicomPath);
end
if ~isfield(dicomInfo, 'AcquisitionMatrix')
    error('mh_fiber_infer_mosaic_geometry:MissingAcquisitionMatrix', ...
        'DICOM AcquisitionMatrix is required: %s', dicomPath);
end
if ~isfield(dicomInfo, 'NumberOfSlices')
    error('mh_fiber_infer_mosaic_geometry:MissingNumberOfSlices', ...
        'DICOM NumberOfSlices is required: %s', dicomPath);
end

mosaicWidth = double(dicomInfo.Columns);
mosaicHeight = double(dicomInfo.Rows);
if ~isequal([mosaicWidth, mosaicHeight], geometry.MosaicSize)
    error('mh_fiber_infer_mosaic_geometry:DicomNiftiSizeMismatch', ...
        ['DICOM mosaic size [%g %g] does not match source NIfTI in-plane ', ...
        'size [%g %g].'], mosaicWidth, mosaicHeight, geometry.MosaicSize(1), ...
        geometry.MosaicSize(2));
end

tileSize = tile_size_from_acquisition_matrix(double(dicomInfo.AcquisitionMatrix(:)'), ...
    mosaicWidth, mosaicHeight);
tileGrid = [mosaicWidth / tileSize(1), mosaicHeight / tileSize(2)];
numberOfSlices = double(dicomInfo.NumberOfSlices);
sliceCount = infer_slice_count(numberOfSlices, geometry.VolumeCount, prod(tileGrid));

geometry.TileSize = tileSize;
geometry.TileGrid = tileGrid;
geometry.SliceCount = sliceCount;
geometry.GeometrySource = 'dicom';
geometry.DicomDir = dicomDir;
geometry.DicomExample = dicomPath;
geometry.DicomRows = mosaicHeight;
geometry.DicomColumns = mosaicWidth;
geometry.DicomNumberOfSlices = numberOfSlices;
geometry.DicomAcquisitionMatrix = double(dicomInfo.AcquisitionMatrix(:)');
end

function geometry = infer_from_reference(geometry, referenceNifti)
must_be_file(referenceNifti, 'reference NIfTI');
refInfo = niftiinfo(referenceNifti);
refSize = double(refInfo.ImageSize);
if numel(refSize) < 3
    error('mh_fiber_infer_mosaic_geometry:InvalidReference', ...
        'Reference NIfTI must have at least three dimensions: %s', referenceNifti);
end

tileSize = refSize(1:2);
tileGrid = geometry.MosaicSize ./ tileSize;
geometry.TileSize = tileSize;
geometry.TileGrid = tileGrid;
geometry.SliceCount = refSize(3);
geometry.GeometrySource = 'reference_nifti';
geometry.ReferenceNifti = referenceNifti;
geometry.Warning = ['Geometry was inferred from a reference NIfTI rather than ', ...
    'subject DICOM metadata; review spatial orientation before downstream use.'];
end

function geometry = validate_geometry(geometry)
geometry.TileSize = round(double(geometry.TileSize(:)'));
geometry.TileGrid = round(double(geometry.TileGrid(:)'));
geometry.SliceCount = round(double(geometry.SliceCount));

if numel(geometry.TileSize) ~= 2 || any(geometry.TileSize <= 0)
    error('mh_fiber_infer_mosaic_geometry:InvalidTileSize', ...
        'TileSize must contain two positive values.');
end
if numel(geometry.TileGrid) ~= 2 || any(geometry.TileGrid <= 0)
    error('mh_fiber_infer_mosaic_geometry:InvalidTileGrid', ...
        'TileGrid must contain two positive values.');
end
if geometry.SliceCount <= 1
    error('mh_fiber_infer_mosaic_geometry:InvalidSliceCount', ...
        'SliceCount must be greater than one.');
end

expectedMosaicSize = geometry.TileSize .* geometry.TileGrid;
if ~isequal(expectedMosaicSize, geometry.MosaicSize)
    error('mh_fiber_infer_mosaic_geometry:InvalidMosaicGeometry', ...
        'TileSize .* TileGrid = [%g %g], but source mosaic size is [%g %g].', ...
        expectedMosaicSize(1), expectedMosaicSize(2), ...
        geometry.MosaicSize(1), geometry.MosaicSize(2));
end

geometry.TileSlotCount = prod(geometry.TileGrid);
if geometry.SliceCount > geometry.TileSlotCount
    error('mh_fiber_infer_mosaic_geometry:SliceCountExceedsTileGrid', ...
        'SliceCount (%d) exceeds available tile slots (%d).', ...
        geometry.SliceCount, geometry.TileSlotCount);
end

geometry.UnusedTileCount = geometry.TileSlotCount - geometry.SliceCount;
geometry.OutputImageSize = [geometry.TileSize, geometry.SliceCount, geometry.VolumeCount];
end

function tileSize = tile_size_from_acquisition_matrix(acquisitionMatrix, mosaicWidth, mosaicHeight)
positiveValues = acquisitionMatrix(acquisitionMatrix > 0);
positiveValues = unique(round(double(positiveValues(:)')), 'stable');
if numel(positiveValues) < 2
    error('mh_fiber_infer_mosaic_geometry:InvalidAcquisitionMatrix', ...
        'AcquisitionMatrix must contain at least two positive entries.');
end

candidateA = positiveValues(1:2);
candidateB = fliplr(candidateA);
if is_integer_division(mosaicWidth, candidateA(1)) && is_integer_division(mosaicHeight, candidateA(2))
    tileSize = candidateA;
elseif is_integer_division(mosaicWidth, candidateB(1)) && is_integer_division(mosaicHeight, candidateB(2))
    tileSize = candidateB;
else
    error('mh_fiber_infer_mosaic_geometry:AcquisitionMatrixNotDivisible', ...
        ['AcquisitionMatrix positive entries [%s] do not divide mosaic ', ...
        'size [%g %g].'], num2str(positiveValues), mosaicWidth, mosaicHeight);
end
end

function sliceCount = infer_slice_count(numberOfSlices, volumeCount, tileSlotCount)
if numberOfSlices <= tileSlotCount
    sliceCount = round(numberOfSlices);
elseif is_integer_division(numberOfSlices, volumeCount)
    sliceCount = round(numberOfSlices / volumeCount);
else
    error('mh_fiber_infer_mosaic_geometry:InvalidNumberOfSlices', ...
        'NumberOfSlices (%g) cannot be reconciled with %d DWI volumes.', ...
        numberOfSlices, volumeCount);
end

if sliceCount > tileSlotCount
    error('mh_fiber_infer_mosaic_geometry:TooManySlices', ...
        'Inferred SliceCount (%d) exceeds tile slot count (%d).', ...
        sliceCount, tileSlotCount);
end
end

function [info, path] = read_first_dicom(dicomDir)
files = list_files_recursive(dicomDir);
for i = 1:numel(files)
    path = files{i};
    [~, name] = fileparts(path);
    if startsWith(name, '._')
        continue;
    end
    try
        info = dicominfo(path);
        return;
    catch
    end
end
error('mh_fiber_infer_mosaic_geometry:NoReadableDicom', ...
    'No readable DICOM file was found under: %s', dicomDir);
end

function files = list_files_recursive(rootDir)
entries = dir(rootDir);
files = {};
for i = 1:numel(entries)
    name = entries(i).name;
    if entries(i).isdir
        if strcmp(name, '.') || strcmp(name, '..')
            continue;
        end
        files = [files, list_files_recursive(fullfile(rootDir, name))]; %#ok<AGROW>
    else
        files{end + 1} = fullfile(rootDir, name); %#ok<AGROW>
    end
end
end

function vals = load_numeric_vector(path)
vals = load(path);
vals = vals(:)';
if isempty(vals) || ~isnumeric(vals)
    error('mh_fiber_infer_mosaic_geometry:InvalidNumericVector', ...
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
    error('mh_fiber_infer_mosaic_geometry:InvalidBvec', ...
        'bvec file must be 3 x N or N x 3: %s', path);
end
end

function tf = is_integer_division(numerator, denominator)
tf = denominator ~= 0 && abs(numerator / denominator - round(numerator / denominator)) < 1e-8;
end

function must_be_file(path, label)
if ~isfile(path)
    error('mh_fiber_infer_mosaic_geometry:MissingFile', ...
        'Missing %s: %s', label, path);
end
end
