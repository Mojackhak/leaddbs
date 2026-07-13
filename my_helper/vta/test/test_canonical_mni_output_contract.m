function tests = test_canonical_mni_output_contract
% Validate canonical MNI transform and threshold artifacts without FEM.

tests = functiontests(localfunctions);
end

function setupOnce(~)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
end

function testIdenticalRepeatAndThresholdsPass(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() rmdir(root, 's'));
efield = reshape(single([100, 180, 199, 200, 220, 300]), [3, 2, 1]);
storedPath = fullfile(root, 'stored.nii');
repeatPath = fullfile(root, 'repeat.nii');
write_nii(storedPath, efield);
write_nii(repeatPath, efield);
thresholdPaths = write_thresholds(root, efield, [180, 200, 220]);

result = mh_validate_canonical_mni_outputs( ...
    storedPath, repeatPath, thresholdPaths, [180, 200, 220]);

verifyTrue(testCase, result.pass);
verifyTrue(testCase, result.deterministic_repeat);
verifyTrue(testCase, all(result.threshold_rows.pass));
end

function testRepeatMismatchFails(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() rmdir(root, 's'));
efield = reshape(single([100, 180, 199, 200, 220, 300]), [3, 2, 1]);
repeat = efield;
repeat(1) = repeat(1) + 1;
storedPath = fullfile(root, 'stored.nii');
repeatPath = fullfile(root, 'repeat.nii');
write_nii(storedPath, efield);
write_nii(repeatPath, repeat);
thresholdPaths = write_thresholds(root, efield, [180, 200, 220]);

verifyError(testCase, @() mh_validate_canonical_mni_outputs( ...
    storedPath, repeatPath, thresholdPaths, [180, 200, 220]), ...
    'mh_vta_acceptance:MniTransformNondeterministic');
end

function testThresholdMismatchFails(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() rmdir(root, 's'));
efield = reshape(single([100, 180, 199, 200, 220, 300]), [3, 2, 1]);
storedPath = fullfile(root, 'stored.nii');
repeatPath = fullfile(root, 'repeat.nii');
write_nii(storedPath, efield);
write_nii(repeatPath, efield);
thresholdPaths = write_thresholds(root, efield, [180, 200, 220]);
broken = ea_load_nii(thresholdPaths{2});
broken.img(1) = 1;
ea_write_nii(broken);

verifyError(testCase, @() mh_validate_canonical_mni_outputs( ...
    storedPath, repeatPath, thresholdPaths, [180, 200, 220]), ...
    'mh_vta_acceptance:MniThresholdMismatch');
end

function paths = write_thresholds(root, efield, thresholds)
paths = cell(1, numel(thresholds));
for index = 1:numel(thresholds)
    paths{index} = fullfile(root, sprintf('threshold-%d.nii', thresholds(index)));
    write_nii(paths{index}, uint8(efield >= thresholds(index)), 2);
end
end

function write_nii(path, image, datatype)
if nargin < 3
    datatype = 16;
end
nii = struct('fname', path, 'dim', size(image), 'dt', [datatype, 0], ...
    'mat', eye(4), 'n', [1, 1], 'pinfo', [1; 0; 0], ...
    'descrip', 'canonical MNI acceptance fixture', 'img', image);
if numel(nii.dim) < 3
    nii.dim(end + 1:3) = 1;
end
ea_write_nii(nii);
end
