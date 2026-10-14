function tests = test_stnvo_plus
% Focused tests for probability addition and expanded atlas mask geometry.
tests = functiontests(localfunctions);
end

function setup(testCase)
root = tempname;
mkdir(root);
ref = fullfile(root, 'reference.nii');
write_image(zeros(17, 17, 17, 'single'), ref, [0, 0, 0]);
testCase.TestData.root = root;
testCase.TestData.spec = struct('atlas_name', 'test', 'repo_dir', root, 'reference_image', ref, ...
    'output_dir', fullfile(root, 'output'));
end

function teardown(testCase)
rmdir(testCase.TestData.root, 's');
end

function testSumBeforeThresholdAndInclusiveBoundary(testCase)
a = zeros(3, 3, 3);
b = a;
a(2, 2, 2) = 0.03;
b(2, 2, 2) = 0.03;
a(3, 3, 3) = 0.05;
roi = sum_roi(testCase, a, b, [0, 0, 0]);
mask = build(testCase, roi);
verifyTrue(testCase, mask(2, 2, 2));
verifyTrue(testCase, mask(3, 3, 3));
verifyEqual(testCase, nnz(mask), 2);
end

function testCroppedOriginsAndUnionExtent(testCase)
a = zeros(3, 3, 3, 'single');
b = zeros(4, 4, 4, 'single');
a(2, 2, 2) = 0.03;
b(1, 2, 2) = 0.03;
b(4, 4, 4) = 0.08;
roi = sum_roi(testCase, a, b, [0.5, 0, 0]);
mask = build(testCase, roi);
verifyTrue(testCase, mask(2, 2, 2));
verifyTrue(testCase, mask(5, 4, 4));
verifyEqual(testCase, nnz(mask), 2);
end

function testNegativeCropOffset(testCase)
a = zeros(3, 3, 3, 'single');
b = zeros(4, 4, 4, 'single');
a(2, 2, 2) = 0.03;
b(3, 2, 2) = 0.03;
roi = sum_roi(testCase, a, b, [-0.5, 0, 0]);
mask = build(testCase, roi);
verifyTrue(testCase, mask(2, 2, 2));
verifyEqual(testCase, nnz(mask), 1);
end

function testNonIntegerCropOffsetRejected(testCase)
a = ones(3, 3, 3, 'single');
roi = sum_roi(testCase, a, a, [0.125, 0, 0]);
verifyError(testCase, @() build(testCase, roi), ...
    'mh_atlas_build_roi_mask:ProbabilityGridMismatch');
end

function testInvalidProbabilityRejected(testCase)
a = ones(3, 3, 3, 'single');
b = a;
b(1) = NaN;
roi = sum_roi(testCase, a, b, [0, 0, 0]);
verifyError(testCase, @() build(testCase, roi), ...
    'mh_atlas_build_roi_mask:InvalidProbabilityImage');
end

function testEuclideanDilationOnReference(testCase)
a = zeros(17, 17, 17, 'single');
a(9, 9, 9) = 0.06;
base = sum_roi(testCase, a, zeros(size(a), 'single'), [0, 0, 0]);
roi = struct('name', 'expanded', 'operation', 'dilate_mm', 'margin_mm', 2, ...
    'sides', struct('L', struct(), 'R', struct()), 'sources', base);
mask = build(testCase, roi);
verifyTrue(testCase, mask(9, 9, 9));
verifyTrue(testCase, mask(13, 9, 9));
verifyFalse(testCase, mask(14, 9, 9));
verifyFalse(testCase, mask(12, 12, 9));
[x, y, z] = ndgrid(-8:8, -8:8, -8:8);
verifyEqual(testCase, mask, (x.^2 + y.^2 + z.^2) <= 16);
end

function roi = sum_roi(testCase, a, b, originB)
root = testCase.TestData.root;
pathA = fullfile(root, 'a.nii');
pathB = fullfile(root, 'b.nii');
write_image(a, pathA, [0, 0, 0]);
write_image(b, pathB, originB);
roi = struct('name', 'sum', 'operation', 'probability_sum_threshold', ...
    'threshold', 0.05, 'threshold_operator', '>=', ...
    'sides', struct('L', struct(), 'R', struct()));
roi.sources = [struct('sides', struct('L', struct('source_file', pathA))), ...
    struct('sides', struct('L', struct('source_file', pathB)))];
end

function mask = build(testCase, roi)
rec = mh_atlas_build_roi_mask(testCase.TestData.spec, roi, 'L', ...
    fullfile(testCase.TestData.root, 'temporary'), struct('Force', false));
mask = niftiread(rec.output_file) > 0;
info = niftiinfo(rec.output_file);
ref = niftiinfo(testCase.TestData.spec.reference_image);
verifyEqual(testCase, info.ImageSize, ref.ImageSize);
verifyEqual(testCase, info.Transform.T, ref.Transform.T, 'AbsTol', 1e-6);
end

function write_image(data, filename, origin)
niftiwrite(data, filename);
info = niftiinfo(filename);
info.PixelDimensions = [0.5, 0.5, 0.5];
T = diag([0.5, 0.5, 0.5, 1]);
T(4, 1:3) = origin;
info.Transform = affine3d(T);
info.TransformName = 'Sform';
niftiwrite(data, filename, info);
end
