function tests = test_vta_common_grid_export
% Validate canonical head-model preparation and fixed-grid VTA exports.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.repoDir = repoDir;
end

function testThresholdUsesInclusiveIndicatorAndUint8(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));

inputPath = fullfile(testRoot, 'efield.nii');
outputPath = fullfile(testRoot, 'vta.nii');
write_fixture_nifti(inputPath, single(reshape([179, 180, 220, 221, NaN], [5, 1, 1])), eye(4));

mh_vta_threshold_efield(inputPath, 180, outputPath);

nii = ea_load_nii(outputPath);
verifyEqual(testCase, uint8(nii.img), uint8(reshape([0, 1, 1, 1, 0], [5, 1, 1])));
header = spm_vol(outputPath);
verifyEqual(testCase, header.dt(1), 2);
end

function testExportMatchesAnchorGeometryAndPreservesOutsideNaN(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));

anchorPath = fullfile(testRoot, 'anchor.nii');
outputPath = fullfile(testRoot, 'efield.nii');
anchorAffine = [2, 0, 0, -2; 0, 3, 0, -3; 0, 0, 4, -4; 0, 0, 0, 1];
write_fixture_nifti(anchorPath, zeros(3, 3, 3, 'single'), anchorAffine);

[x, y, z] = ndgrid(1:2, 1:2, 1:2);
meshVoxels = [x(:), y(:), z(:)];
meshPoints = ea_vox2mm(meshVoxels, anchorAffine);
fieldValues = sum(meshVoxels, 2);

mh_vta_export_common_grid(meshPoints, fieldValues, anchorPath, outputPath);

anchor = ea_load_nii(anchorPath);
output = ea_load_nii(outputPath);
verifyEqual(testCase, size(output.img), size(anchor.img));
verifyEqual(testCase, output.mat, anchor.mat, 'AbsTol', 1e-12);
verifyEqual(testCase, output.img(1, 1, 1), 3, 'AbsTol', 1e-6);
verifyTrue(testCase, isnan(output.img(3, 3, 3)));
end

function testTransformUsesForwardNormalization(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
mkdir(stubDir);
cleanup = onCleanup(@() cleanup_transform_fixture(testRoot, stubDir));

inputPath = fullfile(testRoot, 'native.nii');
outputPath = fullfile(testRoot, 'mni.nii');
referencePath = fullfile(testRoot, 'mni_reference.nii');
logPath = fullfile(testRoot, 'normalization_call.mat');
write_fixture_nifti(inputPath, single(reshape(1:8, [2, 2, 2])), eye(4));
write_fixture_nifti(referencePath, zeros(2, 2, 2, 'single'), diag([2, 2, 2, 1]));
write_normalization_stub(stubDir);
setenv('MH_VTA_NORMALIZATION_LOG', logPath);
addpath(stubDir, '-begin');
clear ea_apply_normalization_tofile;
rehash;

options = struct('subj', struct('subjDir', testRoot));
mh_vta_transform_efield_to_mni(inputPath, options, referencePath, outputPath);

call = load(logPath);
verifyEqual(testCase, call.useinverse, 0);
verifyEqual(testCase, call.interp, 1);
verifyEqual(testCase, call.ref, referencePath);
verifyTrue(testCase, isfile(outputPath));
end

function testHeadmodelBuildEmbedsContractAndCompatibleModelIsReused(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
subjectDir = fullfile(testRoot, 'sub-SNr003');
mkdir(stubDir);
mkdir(subjectDir);
cleanup = onCleanup(@() cleanup_headmodel_fixture(testRoot, stubDir));

write_headmodel_builder_stub(stubDir);
addpath(stubDir, '-begin');
clear mh_vta_run_horn_with_retry;
rehash;

options = fixture_options(subjectDir);
contract = fixture_headmodel_contract();
[headmodelPath, state] = mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation', contract);

verifyEqual(testCase, state, 'built');
verifyTrue(testCase, isfile(headmodelPath));
stored = load(headmodelPath, 'mh_vta_headmodel_contract');
verifyEqual(testCase, stored.mh_vta_headmodel_contract, contract);

[reusedPath, reusedState] = mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation', contract);
verifyEqual(testCase, reusedPath, headmodelPath);
verifyEqual(testCase, reusedState, 'reused');
end

function testHeadmodelContractMismatchIsRejectedWithoutOverwrite(testCase)
testRoot = tempname;
subjectDir = fullfile(testRoot, 'sub-SNr003');
headmodelDir = fullfile(subjectDir, 'headmodel', 'native');
mkdir(headmodelDir);
cleanup = onCleanup(@() rmdir(testRoot, 's'));

options = fixture_options(subjectDir);
contract = fixture_headmodel_contract();
staleContract = contract;
staleContract.anchor_sha256 = repmat('f', 1, 64);
mh_vta_headmodel_contract = staleContract;
headmodelPath = fullfile(headmodelDir, 'sub-SNr003_desc-headmodel1.mat');
save(headmodelPath, 'mh_vta_headmodel_contract');
originalHash = mh_fiber_file_sha256(headmodelPath);

verifyError(testCase, @() mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation', contract), ...
    'mh_vta_prepare_canonical_headmodel:IncompatibleHeadmodel');
verifyEqual(testCase, mh_fiber_file_sha256(headmodelPath), originalHash);
end

function options = fixture_options(subjectDir)
options = struct();
options.native = 1;
options.subj = struct('subjDir', subjectDir, 'subjId', 'SNr003');
end

function contract = fixture_headmodel_contract()
contract = struct( ...
    'subject_id', 'SNr003', ...
    'side', 'right', ...
    'atlas_set', 'Custom_Ewert_Zhang_Middlebrooks', ...
    'conductivity_s_per_m', struct('gray_matter', 0.33, 'white_matter', 0.14), ...
    'reconstruction_sha256', repmat('a', 1, 64), ...
    'anchor_sha256', repmat('b', 1, 64), ...
    'implementation_sha256', repmat('c', 1, 64));
end

function write_fixture_nifti(path, image, affine)
nii = struct();
nii.fname = path;
nii.dim = size(image);
if numel(nii.dim) < 3
    nii.dim(end+1:3) = 1;
end
nii.dt = [16, 0];
nii.mat = affine;
nii.n = [1, 1];
nii.pinfo = [1; 0; 0];
nii.descrip = 'VTA test fixture';
nii.img = image;
ea_write_nii(nii);
end

function write_normalization_stub(stubDir)
path = fullfile(stubDir, 'ea_apply_normalization_tofile.m');
text = ...
    "function ea_apply_normalization_tofile(options, from, to, useinverse, interp, ref)" + newline + ...
    "logPath = getenv('MH_VTA_NORMALIZATION_LOG');" + newline + ...
    "save(logPath, 'options', 'from', 'to', 'useinverse', 'interp', 'ref');" + newline + ...
    "copyfile(from, to);" + newline + ...
    "end" + newline;
write_text(path, text);
end

function write_headmodel_builder_stub(stubDir)
path = fullfile(stubDir, 'mh_vta_run_horn_with_retry.m');
text = ...
    "function diagnostics = mh_vta_run_horn_with_retry(varargin)" + newline + ...
    "expectedPath = varargin{5};" + newline + ...
    "vol = struct('fixture', true);" + newline + ...
    "save(expectedPath, 'vol', '-v7.3');" + newline + ...
    "diagnostics = struct('attempt_count', 1);" + newline + ...
    "end" + newline;
write_text(path, text);
end

function write_text(path, contents)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not write test stub: %s', path);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', char(contents));
end

function cleanup_transform_fixture(testRoot, stubDir)
if isfolder(stubDir)
    rmpath(stubDir);
end
clear ea_apply_normalization_tofile;
setenv('MH_VTA_NORMALIZATION_LOG', '');
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end

function cleanup_headmodel_fixture(testRoot, stubDir)
if isfolder(stubDir)
    rmpath(stubDir);
end
clear mh_vta_run_horn_with_retry;
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
