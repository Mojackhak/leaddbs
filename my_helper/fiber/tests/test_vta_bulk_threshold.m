function tests = test_vta_bulk_threshold
% Validate one-load bulk VTA threshold generation and integration.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.repoDir = repoDir;
end

function testBulkThresholdsPreserveArraysAndMetadata(testCase)
testRoot = create_test_root();
cleanup = onCleanup(@() rmdir(testRoot, 's'));
inputPath = fullfile(testRoot, 'efield.nii.gz');
affine = [2, 0, 0, -4; 0, 3, 0, -6; 0, 0, 4, -8; 0, 0, 0, 1];
values = single(reshape([179, 180, 200, 220, 221, NaN, Inf, -Inf], ...
    [8, 1, 1]));
write_fixture_nifti(inputPath, values, affine);
thresholds = [180, 200, 220];
outputs = fullfile(testRoot, ["vta-180.nii.gz"; "vta-200.nii.gz"; ...
    "vta-220.nii.gz"]);

published = mh_vta_threshold_efields(inputPath, thresholds, outputs);

verifyTrue(testCase, all(published));
for index = 1:numel(thresholds)
    nii = ea_load_nii(char(outputs(index)));
    expected = uint8(isfinite(values) & values >= thresholds(index));
    verifyEqual(testCase, uint8(nii.img), expected);
    verifyEqual(testCase, nii.mat, affine, 'AbsTol', 1e-12);
    verifyEqual(testCase, nii.dim, [8, 1, 1]);
    verifyEqual(testCase, nii.dt(1), 2);
    verifyEqual(testCase, nii.pinfo(1:2), [1; 0]);
    verifyEqual(testCase, string(nii.descrip), ...
        "VTA indicator E >= " + thresholds(index) + " V/m");
end
end

function testBulkLoadsSourceExactlyOnce(testCase)
testRoot = create_test_root();
stubDir = fullfile(testRoot, 'stub');
mkdir(stubDir);
inputPath = fullfile(testRoot, 'efield.nii.gz');
write_fixture_nifti(inputPath, single(reshape([180, 200, 220], [3, 1, 1])), eye(4));
fixture = ea_load_nii(inputPath);
fixturePath = fullfile(testRoot, 'fixture.mat');
save(fixturePath, 'fixture');
logPath = fullfile(testRoot, 'loads.txt');
write_loader_stub(stubDir);
setenv('MH_VTA_LOAD_FIXTURE_MAT', fixturePath);
setenv('MH_VTA_LOAD_COUNT_LOG', logPath);
addpath(stubDir, '-begin');
clear ea_load_nii;
cleanup = onCleanup(@() cleanup_loader_fixture(testRoot, stubDir));
outputs = fullfile(testRoot, ["vta-180.nii.gz"; "vta-200.nii.gz"; ...
    "vta-220.nii.gz"]);

mh_vta_threshold_efields(inputPath, [180, 200, 220], outputs);

loads = splitlines(strtrim(string(fileread(logPath))));
verifyEqual(testCase, numel(loads), 1);
verifyEqual(testCase, loads, "load");
end

function testAllExistingOutputsDoNotRequireSource(testCase)
testRoot = create_test_root();
cleanup = onCleanup(@() rmdir(testRoot, 's'));
outputPath = fullfile(testRoot, 'existing.nii.gz');
write_fixture_nifti(outputPath, uint8(ones(2, 1, 1)), eye(4));

published = mh_vta_threshold_efields( ...
    fullfile(testRoot, 'missing-efield.nii.gz'), 180, outputPath);

verifyFalse(testCase, published);
verifyEqual(testCase, uint8(ea_load_nii(outputPath).img), ...
    uint8(ones(2, 1, 1)));
end

function testFailureRetainsEarlierPublishedThreshold(testCase)
testRoot = create_test_root();
cleanup = onCleanup(@() rmdir(testRoot, 's'));
inputPath = fullfile(testRoot, 'efield.nii.gz');
write_fixture_nifti(inputPath, single(reshape([180, 220], [2, 1, 1])), eye(4));
firstOutput = fullfile(testRoot, 'vta-180.nii.gz');
blockedParent = fullfile(testRoot, 'not-a-directory');
fid = fopen(blockedParent, 'w');
verifyGreaterThan(testCase, fid, 0);
fclose(fid);
secondOutput = fullfile(blockedParent, 'vta-220.nii.gz');

failed = false;
try
    mh_vta_threshold_efields(inputPath, [180, 220], ...
        [string(firstOutput); string(secondOutput)]);
catch
    failed = true;
end

verifyTrue(testCase, failed);
verifyTrue(testCase, isfile(firstOutput));
verifyFalse(testCase, isfile(secondOutput));
publishedFiles = string({dir(fullfile(testRoot, '*.nii.gz')).name});
verifyEqual(testCase, sort(publishedFiles), ...
    sort(["efield.nii.gz", "vta-180.nii.gz"]));
end

function testEmptyRequestDoesNotRequireSource(testCase)
testRoot = create_test_root();
cleanup = onCleanup(@() rmdir(testRoot, 's'));

published = mh_vta_threshold_efields( ...
    fullfile(testRoot, 'missing-efield.nii.gz'), [], strings(0, 1));

verifyEmpty(testCase, published);
end

function testCompatibilityWrapperMatchesBulkOutput(testCase)
testRoot = create_test_root();
cleanup = onCleanup(@() rmdir(testRoot, 's'));
inputPath = fullfile(testRoot, 'efield.nii.gz');
values = single(reshape([179, 180, 220, NaN], [4, 1, 1]));
write_fixture_nifti(inputPath, values, eye(4));
singlePath = fullfile(testRoot, 'single.nii.gz');
bulkPath = fullfile(testRoot, 'bulk.nii.gz');

mh_vta_threshold_efield(inputPath, 180, singlePath);
mh_vta_threshold_efields(inputPath, 180, bulkPath);

singleNii = ea_load_nii(singlePath);
bulkNii = ea_load_nii(bulkPath);
verifyEqual(testCase, singleNii.img, bulkNii.img);
verifyEqual(testCase, singleNii.mat, bulkNii.mat, 'AbsTol', 1e-12);
verifyEqual(testCase, singleNii.dt, bulkNii.dt);
verifyEqual(testCase, singleNii.pinfo, bulkNii.pinfo);
verifyEqual(testCase, singleNii.descrip, bulkNii.descrip);
end

function testGroupPeakPathUsesBulkThresholdEvents(testCase)
testRoot = create_test_root();
nativeLeaf = fullfile(testRoot, 'native');
mniLeaf = fullfile(testRoot, 'mni');
mkdir(nativeLeaf);
mkdir(mniLeaf);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
write_fixture_nifti(fullfile(nativeLeaf, 'efield.nii.gz'), ...
    single(reshape([179, 180, 200, 220], [4, 1, 1])), eye(4));
task = struct( ...
    'task_id', 'group-bulk-threshold-test', ...
    'output_leaves', struct('native', nativeLeaf, ...
        'MNI152NLin2009bAsym', mniLeaf), ...
    'missing_artifacts', struct('native', {{ ...
        'vta_threshold-0p18Vpermm.nii.gz', ...
        'vta_threshold-0p20Vpermm.nii.gz', ...
        'vta_threshold-0p22Vpermm.nii.gz'}}), ...
    'model', struct('thresholds_v_per_m', [180, 200, 220]));
stages = strings(0, 1);

mh_vta_derive_canonical_group_peak(task, ...
    'EventEmitter', @collect_event, 'TaskId', task.task_id);

verifyEqual(testCase, stages, ["task_runtime_resolution"; ...
    "threshold_generation"; "artifact_publication"; ...
    "threshold_generation"; "artifact_publication"; ...
    "threshold_generation"; "artifact_publication"]);

    function collect_event(~, fields)
        stages(end + 1, 1) = string(fields.stage);
    end
end

function root = create_test_root()
root = tempname;
mkdir(root);
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
nii.descrip = 'VTA bulk threshold test fixture';
nii.img = image;
ea_write_nii(nii);
end

function write_loader_stub(stubDir)
contents = ...
    "function nii = ea_load_nii(varargin)" + newline + ...
    "logPath = getenv('MH_VTA_LOAD_COUNT_LOG');" + newline + ...
    "fid = fopen(logPath, 'a');" + newline + ...
    "fprintf(fid, 'load\n');" + newline + ...
    "fclose(fid);" + newline + ...
    "payload = load(getenv('MH_VTA_LOAD_FIXTURE_MAT'), 'fixture');" + newline + ...
    "nii = payload.fixture;" + newline + ...
    "end" + newline;
write_text(fullfile(stubDir, 'ea_load_nii.m'), contents);
end

function write_text(path, contents)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not write test stub: %s', path);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', char(contents));
end

function cleanup_loader_fixture(testRoot, stubDir)
if isfolder(stubDir)
    rmpath(stubDir);
end
clear ea_load_nii;
setenv('MH_VTA_LOAD_FIXTURE_MAT', '');
setenv('MH_VTA_LOAD_COUNT_LOG', '');
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
