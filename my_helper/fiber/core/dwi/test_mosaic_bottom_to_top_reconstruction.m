% Validate bottom-to-top mosaic reconstruction and padding-tile exclusion.

repoDir = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
addpath(genpath(repoDir));

workDir = tempname;
mkdir(workDir);
cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(workDir));

tileSize = [2 3];
tileGrid = [9 9];
sliceCount = 78;
volumeCount = 2;
mosaicSize = tileSize .* tileGrid;
mosaic = zeros([mosaicSize 1 volumeCount], 'uint16');

coordinates = bottom_to_top_left_to_right_coordinates(tileGrid);
for sliceIndex = 1:sliceCount
    rowColumn = coordinates(sliceIndex, :);
    ranges = tile_ranges(tileSize, rowColumn);
    mosaic(ranges.x, ranges.y, 1, 1) = uint16(sliceIndex);
    mosaic(ranges.x, ranges.y, 1, 2) = uint16(sliceIndex + 100);
end

source = write_source_set(workDir, 'source', mosaic, volumeCount);
outputDir = fullfile(workDir, 'output');
result = mh_fiber_reconstruct_mosaic_dwi( ...
    'SourceNifti', source.nifti, ...
    'SourceJson', source.json, ...
    'SourceBval', source.bval, ...
    'SourceBvec', source.bvec, ...
    'OutputDir', outputDir, ...
    'OutputBase', 'sub-Test_ses-preop_dwi', ...
    'TileSize', tileSize, ...
    'TileGrid', tileGrid, ...
    'SliceCount', sliceCount, ...
    'TileOrder', 'bottom_to_top_left_to_right', ...
    'SkipPaddingTiles', true, ...
    'Force', true);

assert(strcmp(result.Status, 'reconstructed'), ...
    'Mosaic reconstruction did not complete.');
assert(result.SkipPaddingTiles, ...
    'Result does not record padding-tile exclusion.');
assert(isequal(result.SelectedTileCoordinatesRowColumn, coordinates(1:78, :)), ...
    'Selected tile coordinates do not preserve the requested traversal.');
assert(isequal(result.ExcludedTileCoordinatesRowColumn, [1 7; 1 8; 1 9]), ...
    'The three top-row padding tiles were not excluded.');

reconstructed = niftiread(result.OutputNifti);
assert(isequal(size(reconstructed), [tileSize sliceCount volumeCount]), ...
    'Reconstructed DWI has an unexpected shape.');
for sliceIndex = 1:sliceCount
    firstVolume = reconstructed(:, :, sliceIndex, 1);
    secondVolume = reconstructed(:, :, sliceIndex, 2);
    assert(all(firstVolume(:) == sliceIndex), ...
        'First volume has a missing, duplicated, or reordered slice.');
    assert(all(secondVolume(:) == sliceIndex + 100), ...
        'Second volume has a missing, duplicated, or reordered slice.');
end

metadata = jsondecode(fileread(result.OutputJson));
assert(metadata.MosaicSkipPaddingTiles, ...
    'Output JSON does not record padding-tile exclusion.');
assert(isequal(metadata.MosaicExcludedTileCoordinatesRowColumn, [1 7; 1 8; 1 9]), ...
    'Output JSON does not record the excluded tile coordinates.');

invalidMosaic = mosaic;
paddingRanges = tile_ranges(tileSize, coordinates(79, :));
invalidMosaic(paddingRanges.x, paddingRanges.y, 1, 1) = uint16(999);
invalidSource = write_source_set(workDir, 'invalid', invalidMosaic, volumeCount);
paddingMismatchBlocked = false;
try
    mh_fiber_reconstruct_mosaic_dwi( ...
        'SourceNifti', invalidSource.nifti, ...
        'SourceJson', invalidSource.json, ...
        'SourceBval', invalidSource.bval, ...
        'SourceBvec', invalidSource.bvec, ...
        'OutputDir', fullfile(workDir, 'invalid_output'), ...
        'OutputBase', 'sub-Test_ses-preop_dwi', ...
        'TileSize', tileSize, ...
        'TileGrid', tileGrid, ...
        'SliceCount', sliceCount, ...
        'TileOrder', 'bottom_to_top_left_to_right', ...
        'SkipPaddingTiles', true, ...
        'DryRun', true);
catch ME
    paddingMismatchBlocked = strcmp(ME.identifier, ...
        'mh_fiber_reconstruct_mosaic_dwi:PaddingTileCountMismatch');
end
assert(paddingMismatchBlocked, ...
    'Ambiguous padding detection must stop reconstruction.');

fprintf('Bottom-to-top mosaic reconstruction test passed.\n');

function coordinates = bottom_to_top_left_to_right_coordinates(tileGrid)
gridCols = tileGrid(1);
gridRows = tileGrid(2);
coordinates = zeros(prod(tileGrid), 2);
index = 0;
for row = gridRows:-1:1
    for column = 1:gridCols
        index = index + 1;
        coordinates(index, :) = [row column];
    end
end
end

function ranges = tile_ranges(tileSize, rowColumn)
tileRow = rowColumn(1) - 1;
tileColumn = rowColumn(2) - 1;
ranges = struct();
ranges.x = (tileColumn * tileSize(1) + 1):((tileColumn + 1) * tileSize(1));
ranges.y = (tileRow * tileSize(2) + 1):((tileRow + 1) * tileSize(2));
end

function paths = write_source_set(workDir, base, data, volumeCount)
paths = struct();
uncompressed = fullfile(workDir, [base, '.nii']);
niftiwrite(data, uncompressed, 'Compressed', false);
gzip(uncompressed);
delete(uncompressed);
paths.nifti = [uncompressed, '.gz'];

paths.json = fullfile(workDir, [base, '.json']);
fid = fopen(paths.json, 'w');
assert(fid > 0, 'Could not create source JSON.');
fprintf(fid, '{}\n');
fclose(fid);

paths.bval = fullfile(workDir, [base, '.bval']);
writematrix([0 repmat(1000, 1, volumeCount - 1)], paths.bval, ...
    'FileType', 'text', 'Delimiter', ' ');
paths.bvec = fullfile(workDir, [base, '.bvec']);
writematrix(zeros(3, volumeCount), paths.bvec, ...
    'FileType', 'text', 'Delimiter', ' ');
end
