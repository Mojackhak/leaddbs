function test_ea_field_ref2itk()
%TEST_EA_FIELD_REF2ITK Validate ITK displacement-field fixed parameters.

repoRoot = fileparts(fileparts(mfilename('fullpath')));
addpath(genpath(repoRoot));

tmpDir = tempname;
mkdir(tmpDir);
cleanup = onCleanup(@() cleanup_tmpdir(tmpDir));

dims = [5, 6, 7];
originRAS = [-76.0, -98.5, -52.25];
theta = 20 * pi / 180;
directionRAS = [ ...
    1, 0, 0; ...
    0, cos(theta), -sin(theta); ...
    0, sin(theta), cos(theta)];

isoSpacing = [0.7, 0.7, 0.7];
isoFile = fullfile(tmpDir, 'iso_oblique_ref.nii');
write_test_nifti(isoFile, dims, isoSpacing, originRAS, directionRAS);

isoFixed = ea_field_ref2itk(isoFile);
isoExpected = expected_fixed_parameters(dims, isoSpacing, originRAS, directionRAS);
assert_close(isoFixed, isoExpected, 1e-6, 'Isotropic fixed parameters changed unexpectedly.');

isoDirection = fixed_to_direction(isoFixed);
isoOldDirection = old_direction_matrix(isoSpacing, directionRAS);
assert_close(isoDirection, isoOldDirection, 1e-6, 'Isotropic grids should match the old direction behavior.');

anisoSpacing = [0.5, 0.5, 0.7];
anisoFile = fullfile(tmpDir, 'anisotropic_oblique_ref.nii');
write_test_nifti(anisoFile, dims, anisoSpacing, originRAS, directionRAS);

anisoFixed = ea_field_ref2itk(anisoFile);
anisoExpected = expected_fixed_parameters(dims, anisoSpacing, originRAS, directionRAS);
assert_close(anisoFixed, anisoExpected, 1e-6, 'Anisotropic oblique fixed parameters are incorrect.');

anisoDirection = fixed_to_direction(anisoFixed);
anisoOldDirection = old_direction_matrix(anisoSpacing, directionRAS);
if max(abs(anisoDirection(:) - anisoOldDirection(:))) < 1e-3
    error('Anisotropic oblique direction did not differ from the old row/spacing bug.');
end

rowLengths = sqrt(sum(anisoDirection.^2, 2));
assert_close(rowLengths, ones(3, 1), 1e-6, 'Direction rows are not unit length.');
assert_close(anisoDirection * anisoDirection', eye(3), 1e-6, 'Direction rows are not orthonormal.');

expectedDirectionLPS = diag([-1, -1, 1]) * directionRAS;
expectedRowMajor = reshape(expectedDirectionLPS', [], 1);
assert_close(anisoFixed(10:18), expectedRowMajor, 1e-6, ...
    'Direction serialization is not ITK/SimpleITK row-major.');

fprintf('test_ea_field_ref2itk passed\n');

end

function write_test_nifti(fileName, dims, spacing, originRAS, directionRAS)

data = zeros(dims, 'single');
nii = make_nii(data, spacing, [], 16);
nii.hdr.dime.dim(1) = 3;
nii.hdr.dime.dim(2:4) = dims;
nii.hdr.dime.pixdim(2:4) = spacing;

affine = eye(4);
affine(1:3, 1:3) = directionRAS * diag(spacing);
affine(1:3, 4) = originRAS(:);

nii.hdr.hist.qform_code = 0;
nii.hdr.hist.sform_code = 1;
nii.hdr.hist.srow_x = affine(1, :);
nii.hdr.hist.srow_y = affine(2, :);
nii.hdr.hist.srow_z = affine(3, :);

save_nii(nii, fileName);

end

function fixed = expected_fixed_parameters(dims, spacing, originRAS, directionRAS)

directionLPS = diag([-1, -1, 1]) * directionRAS;

fixed = zeros(18, 1);
fixed(1:3) = dims(:);
fixed(4:6) = [-originRAS(1); -originRAS(2); originRAS(3)];
fixed(7:9) = spacing(:);
fixed(10:18) = reshape(directionLPS', [], 1);

end

function direction = fixed_to_direction(fixed)

direction = reshape(fixed(10:18), 3, 3)';

end

function direction = old_direction_matrix(spacing, directionRAS)

voxToRAS = directionRAS * diag(spacing);
direction = [ ...
    -voxToRAS(1, :) / spacing(1); ...
    -voxToRAS(2, :) / spacing(2); ...
     voxToRAS(3, :) / spacing(3)];

end

function assert_close(actual, expected, tolerance, message)

if max(abs(actual(:) - expected(:))) > tolerance
    error('%s', message);
end

end

function cleanup_tmpdir(tmpDir)

if isfolder(tmpDir)
    rmdir(tmpDir, 's');
end

end
