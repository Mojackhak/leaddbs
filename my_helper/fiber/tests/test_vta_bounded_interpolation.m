function tests = test_vta_bounded_interpolation
% Compare bounded native interpolation with the full-grid reference.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.repoDir = repoDir;
end

function testAffineVariantsMatchFullGridReference(testCase)
affines = affine_fixtures();
dimensions = [9, 8, 7];
meshVoxels = box_corners([3, 3, 2], [6, 5, 4]);
for affineIndex = 1:numel(affines)
    verify_export_matches_reference(testCase, dimensions, ...
        affines{affineIndex}, meshVoxels, false);
end
end

function testBoundaryAndPartialOutsideSupportMatchReference(testCase)
dimensions = [8, 7, 6];
affine = [1.2, 0.3, 0, -5; 0, 1.5, 0.2, 7; ...
    0, 0, 2, -9; 0, 0, 0, 1];
fixtures = { ...
    box_corners([1, 1, 1], [3, 3, 3]), ...
    box_corners([-3, 2, 2], [3, 5, 4])};
for fixtureIndex = 1:numel(fixtures)
    verify_export_matches_reference(testCase, dimensions, affine, ...
        fixtures{fixtureIndex}, false);
end
end

function testFullyOutsideSupportProducesFullSizeNaNGrid(testCase)
dimensions = [7, 6, 5];
affine = eye(4);
meshVoxels = box_corners([20, 20, 20], [23, 23, 23]);

[actual, ~, anchor] = run_fixture( ...
    dimensions, affine, meshVoxels, false);

verifyEqual(testCase, size(actual.img), dimensions);
verifyTrue(testCase, all(isnan(actual.img), 'all'));
verifyEqual(testCase, actual.mat, anchor.mat, 'AbsTol', 1e-12);
end

function testNonfiniteSamplesAreExcludedBeforeBounding(testCase)
dimensions = [8, 7, 6];
affine = [0, -2, 0, 12; 2, 0, 0, -4; 0, 0, 1.5, 3; 0, 0, 0, 1];
meshVoxels = box_corners([2, 2, 2], [5, 5, 4]);

verify_export_matches_reference(testCase, dimensions, affine, ...
    meshVoxels, true);
end

function testSmallSupportQueriesLessThanFullAnchor(testCase)
dimensions = [100, 100, 100];
meshVoxels = box_corners([40, 45, 50], [42, 47, 52]);
affine = [1, 0.2, 0, -50; 0, 1, 0.1, -50; ...
    0, 0, 1, -50; 0, 0, 0, 1];
pointsMm = ea_vox2mm(meshVoxels, affine);

[lowerBound, upperBound] = mh_vta_native_query_bounds( ...
    pointsMm, affine, dimensions);

queryCount = prod(upperBound - lowerBound + 1);
verifyLessThan(testCase, queryCount, prod(dimensions));
verifyGreaterThan(testCase, queryCount, 0);
end

function testInsufficientFiniteSamplesRetainsEstablishedError(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
anchorPath = fullfile(testRoot, 'anchor.nii');
outputPath = fullfile(testRoot, 'output.nii');
write_fixture_nifti(anchorPath, zeros(3, 3, 3, 'single'), eye(4));
points = [0, 0, 0; 1, 0, 0; 0, 1, 0; NaN, 0, 0];
values = [1; 2; 3; 4];

verifyError(testCase, @() mh_vta_export_common_grid( ...
    points, values, anchorPath, outputPath), ...
    'mh_vta_export_common_grid:InsufficientSamples');
end

function verify_export_matches_reference(testCase, dimensions, affine, ...
        meshVoxels, appendNonfinite)
[actual, expected, anchor] = run_fixture( ...
    dimensions, affine, meshVoxels, appendNonfinite);

verifyEqual(testCase, isfinite(actual.img), isfinite(expected));
verifyEqual(testCase, single(actual.img), expected);
verifyEqual(testCase, size(actual.img), dimensions);
verifyEqual(testCase, actual.mat, anchor.mat, 'AbsTol', 1e-12);
verifyEqual(testCase, actual.dt(1), 16);
verifyEqual(testCase, string(actual.descrip), ...
    "Continuous FEM E-field on native anchor grid (V/m)");
end

function [actual, expected, anchor] = run_fixture( ...
        dimensions, affine, meshVoxels, appendNonfinite)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
anchorPath = fullfile(testRoot, 'anchor.nii');
outputPath = fullfile(testRoot, 'output.nii');
write_fixture_nifti(anchorPath, zeros(dimensions, 'single'), affine);
anchor = ea_load_nii(anchorPath);
pointsMm = ea_vox2mm(meshVoxels, anchor.mat);
values = linear_field(pointsMm);
if appendNonfinite
    pointsMm = [pointsMm; NaN, 0, 0; 0, Inf, 0];
    values = [values; 100; NaN];
end
expected = full_grid_reference( ...
    pointsMm, values, dimensions, anchor.mat);
mh_vta_export_common_grid(pointsMm, values, anchorPath, outputPath);
actual = ea_load_nii(outputPath);
end

function sampled = full_grid_reference(pointsMm, values, dimensions, affine)
valid = all(isfinite(pointsMm), 2) & isfinite(values);
pointsMm = double(pointsMm(valid, :));
values = double(values(valid));
interpolant = scatteredInterpolant(pointsMm(:, 1), pointsMm(:, 2), ...
    pointsMm(:, 3), values, 'linear', 'none');
indices = (1:prod(dimensions))';
[i, j, k] = ind2sub(dimensions, indices);
xyzMm = ea_vox2mm([i, j, k], affine);
sampled = nan(dimensions, 'single');
sampled(indices) = single(interpolant( ...
    xyzMm(:, 1), xyzMm(:, 2), xyzMm(:, 3)));
end

function values = linear_field(pointsMm)
values = 0.25 * pointsMm(:, 1) - 0.5 * pointsMm(:, 2) + ...
    0.75 * pointsMm(:, 3) + 4;
end

function corners = box_corners(lowerBound, upperBound)
[x, y, z] = ndgrid([lowerBound(1), upperBound(1)], ...
    [lowerBound(2), upperBound(2)], [lowerBound(3), upperBound(3)]);
corners = [x(:), y(:), z(:)];
end

function affines = affine_fixtures()
theta = pi / 6;
rotation = [cos(theta), -sin(theta), 0; ...
    sin(theta), cos(theta), 0; 0, 0, 1];
affines = { ...
    eye(4), ...
    [eye(3), [11; -7; 4]; 0, 0, 0, 1], ...
    [rotation * diag([1.2, 1.5, 2]), [3; -5; 7]; 0, 0, 0, 1], ...
    [1.1, 0.35, 0.1, -4; 0, 1.4, 0.25, 6; ...
        0, 0, 1.8, -2; 0, 0, 0, 1], ...
    [-1.2, 0, 0, 12; 0, 1.3, 0, -3; 0, 0, 1.7, 5; ...
        0, 0, 0, 1]};
end

function write_fixture_nifti(path, image, affine)
nii = struct();
nii.fname = path;
nii.dim = size(image);
nii.dt = [16, 0];
nii.mat = affine;
nii.n = [1, 1];
nii.pinfo = [1; 0; 0];
nii.descrip = 'VTA bounded interpolation test fixture';
nii.img = image;
ea_write_nii(nii);
end
