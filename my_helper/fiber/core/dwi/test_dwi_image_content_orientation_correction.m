% Validate image-content DWI orientation correction and bvec synchronization.

repoDir = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
addpath(genpath(repoDir));

workDir = tempname;
mkdir(workDir);
cleanupObj = onCleanup(@() mh_fiber_cleanup_temp_dir(workDir));

sourceData = reshape(single(1:(2 * 3 * 4 * 2)), [2 3 4 2]);
sourceNii = fullfile(workDir, 'source.nii');
niftiwrite(sourceData, sourceNii, 'Compressed', false);
gzip(sourceNii);
sourceNiiGz = [sourceNii, '.gz'];

sourceJson = fullfile(workDir, 'source.json');
fid = fopen(sourceJson, 'w');
assert(fid > 0, 'Could not create source JSON.');
fprintf(fid, '{"ExistingField":"kept"}');
fclose(fid);

sourceBval = fullfile(workDir, 'source.bval');
writematrix([0 1000], sourceBval, 'FileType', 'text', 'Delimiter', ' ');

sourceBvec = fullfile(workDir, 'source.bvec');
sourceBvecMatrix = [0 1; 0 2; 0 3];
writematrix(sourceBvecMatrix, sourceBvec, 'FileType', 'text', 'Delimiter', ' ');

outputDir = fullfile(workDir, 'out');
result = mh_fiber_reorient_dwi_image_content( ...
    'SourceNifti', sourceNiiGz, ...
    'SourceJson', sourceJson, ...
    'SourceBval', sourceBval, ...
    'SourceBvec', sourceBvec, ...
    'OutputDir', outputDir, ...
    'OutputBase', 'sub-Test_ses-preop_dwi', ...
    'Transform', 'rotX180', ...
    'Force', true);

assert(isfile(result.Nifti), 'Corrected NIfTI was not written.');
assert(isfile(result.Json), 'Corrected JSON was not written.');
assert(isfile(result.Bval), 'Corrected bval was not written.');
assert(isfile(result.Bvec), 'Corrected bvec was not written.');

correctedData = niftiread(result.Nifti);
expectedData = flip(flip(sourceData, 2), 3);
assert(isequal(correctedData, expectedData), ...
    'rotX180 did not flip voxel dimensions 2 and 3.');

correctedBvec = readmatrix(result.Bvec, 'FileType', 'text');
expectedBvec = [0 1; 0 -2; 0 -3];
assert(isequal(size(correctedBvec), size(expectedBvec)), ...
    'Corrected bvec size changed unexpectedly.');
assert(max(abs(correctedBvec(:) - expectedBvec(:))) < 1e-12, ...
    'rotX180 did not apply diag([1 -1 -1]) to bvec.');

correctedBval = readmatrix(result.Bval, 'FileType', 'text');
assert(isequal(correctedBval(:)', [0 1000]), 'bval changed unexpectedly.');

metadata = jsondecode(fileread(result.Json));
assert(isfield(metadata, 'ExistingField'), 'Existing JSON fields were not preserved.');
assert(metadata.ImageContentOrientationCorrection, ...
    'JSON does not record ImageContentOrientationCorrection=true.');
assert(strcmp(metadata.OrientationCorrectionTransform, 'rotX180'), ...
    'JSON does not record the transform name.');
assert(isequal(metadata.OrientationCorrectionBvecMatrix, [1 0 0; 0 -1 0; 0 0 -1]), ...
    'JSON does not record the bvec transform matrix.');

fprintf('DWI image-content orientation correction test passed.\n');
