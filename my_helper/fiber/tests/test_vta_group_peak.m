function tests = test_vta_group_peak
% Verify alternating-source group peak composition on a common NIfTI grid.

tests = functiontests(localfunctions);
end

function testPeakUsesVoxelwiseMaximum(testCase)
workDir = make_work_dir(testCase);
firstPath = fullfile(workDir, 'first.nii');
secondPath = fullfile(workDir, 'second.nii');
outputPath = fullfile(workDir, 'peak.nii');
write_nifti(firstPath, single(reshape([10 30 20], [3 1 1])));
write_nifti(secondPath, single(reshape([20 15 40], [3 1 1])));

mh_vta_compose_group_peak({firstPath, secondPath}, outputPath);

output = ea_load_nii(outputPath);
verifyEqual(testCase, double(output.img(:)'), [20 30 40]);
verifyEqual(testCase, output.dt(1), 16);
end

function testInputsRemainUnchanged(testCase)
workDir = make_work_dir(testCase);
firstPath = fullfile(workDir, 'first.nii');
secondPath = fullfile(workDir, 'second.nii');
outputPath = fullfile(workDir, 'peak.nii');
first = single(reshape([10 30 20], [3 1 1]));
second = single(reshape([20 15 40], [3 1 1]));
write_nifti(firstPath, first);
write_nifti(secondPath, second);

mh_vta_compose_group_peak({firstPath, secondPath}, outputPath);

verifyEqual(testCase, double(ea_load_nii(firstPath).img), double(first));
verifyEqual(testCase, double(ea_load_nii(secondPath).img), double(second));
end

function testPeakIgnoresPerSourceNaNAndPreservesAllNaN(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() rmdir(root, 's'));
left = fullfile(root, 'left.nii');
right = fullfile(root, 'right.nii');
output = fullfile(root, 'peak.nii');
write_nifti(left, single(reshape([NaN 10 NaN 5], [4 1 1])));
write_nifti(right, single(reshape([NaN NaN 20 7], [4 1 1])));

mh_vta_compose_group_peak({left, right}, output);

actual = ea_load_nii(output).img;
verifyTrue(testCase, isnan(actual(1)));
verifyEqual(testCase, double(actual(2:4)), [10; 20; 7]);
end

function testPeakRejectsGridMismatch(testCase)
workDir = make_work_dir(testCase);
firstPath = fullfile(workDir, 'first.nii');
secondPath = fullfile(workDir, 'second.nii');
write_nifti(firstPath, single(zeros(3, 1, 1)));
write_nifti(secondPath, single(zeros(4, 1, 1)));

verifyError(testCase, ...
    @() mh_vta_compose_group_peak({firstPath, secondPath}, fullfile(workDir, 'peak.nii')), ...
    'mh_vta:GridMismatch');
end

function workDir = make_work_dir(testCase)
workDir = tempname;
mkdir(workDir);
testCase.addTeardown(@() rmdir(workDir, 's'));
end

function write_nifti(path, data)
niftiwrite(data, path, 'Compressed', false);
end
