function test_single_source_backend_equivalence()
% Exercise the generic NIfTI comparison helper with synthetic E-fields.
%
% Runner-facing API:
%   result = mh_compare_single_source_backend_outputs(referencePath, ...
%       candidatePath, 'Space', space, 'Side', side, ...
%       'Comparison', 'equivalence'|'repeatability', ...
%       'ThrowOnFailure', true|false)
%
% The result contains a one-row efield_row table, a three-row binary_rows
% table, and a scalar logical pass value. ThrowOnFailure defaults to true;
% false returns complete failing metrics for runner-side persistence.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));

testRoot = tempname;
mkdir(testRoot);
cleanupObj = onCleanup(@() cleanup_test(testRoot));

dimensions = [20 20 20];
referenceData = reshape(linspace(160, 240, prod(dimensions)), dimensions);
candidateData = referenceData;
crossingIndices = [1 2 3];
referenceData(crossingIndices) = [179.9996 199.9996 219.9996];
candidateData(crossingIndices) = [180.0004 200.0004 220.0004];

referencePath = fullfile(testRoot, 'reference.nii');
candidatePath = fullfile(testRoot, 'candidate.nii');
write_nii(referencePath, referenceData);
write_nii_like(referencePath, candidatePath, candidateData);

result = mh_compare_single_source_backend_outputs( ...
    referencePath, candidatePath, ...
    'Space', 'native', 'Side', 'L', 'Comparison', 'equivalence');

assert(result.pass, 'A within-limit synthetic pair should pass.');
assert(istable(result.efield_row) && height(result.efield_row) == 1, ...
    'efield_row must be a one-row table.');
assert(istable(result.binary_rows) && height(result.binary_rows) == 3, ...
    'binary_rows must contain one row per threshold.');
assert(isequal(result.binary_rows.threshold_v_per_m', [180 200 220]), ...
    'The helper must evaluate the approved thresholds.');
assert(all(result.binary_rows.pass), ...
    'Every binary-mask threshold should pass.');
assert(result.efield_row.value_max_abs <= 1e-3, ...
    'The reported maximum value difference is incorrect.');
assert(all(result.binary_rows.discordant_within_tolerance), ...
    'Near-threshold discordances should be accepted.');
jsonText = jsonencode(struct( ...
    'efield_row', table2struct(result.efield_row), ...
    'binary_rows', table2struct(result.binary_rows), ...
    'pass', result.pass));
assert(~isempty(jsonText), 'Result metrics must be JSON serializable.');

repeatResult = mh_compare_single_source_backend_outputs( ...
    referencePath, referencePath, ...
    'Space', 'MNI', 'Side', 'R', 'Comparison', 'repeatability');
assert(repeatResult.pass && repeatResult.efield_row.exact_repeatability, ...
    'Voxel-identical repeat runs should pass strict repeatability.');

identityAlignment = mh_compare_single_source_backend_outputs( ...
    referencePath, referencePath, ...
    'Space', 'native', 'Side', 'R', 'Comparison', 'equivalence', ...
    'ResampleCandidateToReference', true);
assert(identityAlignment.pass, ...
    'Identity grid alignment must preserve strict equivalence.');
assert(~identityAlignment.efield_row.resampled_to_reference_grid, ...
    'Identity grid alignment must not interpolate the candidate.');

assert_error_id(@() mh_compare_single_source_backend_outputs( ...
    referencePath, candidatePath, ...
    'Space', 'native', 'Side', 'L', 'Comparison', 'repeatability'), ...
    'mh_compare_single_source_backend_outputs:RepeatabilityMismatch');
softRepeatResult = mh_compare_single_source_backend_outputs( ...
    referencePath, candidatePath, ...
    'Space', 'native', 'Side', 'L', 'Comparison', 'repeatability', ...
    'ThrowOnFailure', false);
assert(~softRepeatResult.pass && ~softRepeatResult.efield_row.pass, ...
    'Soft repeatability failure must return pass=false.');
assert(height(softRepeatResult.binary_rows) == 3, ...
    'Soft repeatability failure must return all binary metrics.');

differentDimensionsPath = fullfile(testRoot, 'different_dimensions.nii');
write_nii(differentDimensionsPath, zeros(10, 10, 10));
assert_error_id(@() compare_equivalence(referencePath, differentDimensionsPath), ...
    'mh_compare_single_source_backend_outputs:DimensionMismatch');
softDimensions = mh_compare_single_source_backend_outputs( ...
    referencePath, differentDimensionsPath, 'ThrowOnFailure', false);
assert(~softDimensions.pass && ...
    ~softDimensions.efield_row.dimensions_match, ...
    'Soft dimension failure must retain a structural metrics row.');

referenceGridPath = fullfile(testRoot, 'reference_grid.nii');
candidateGridPath = fullfile(testRoot, 'candidate_grid.nii');
referenceAffine = diag([2 2 2 1]);
candidateAffine = diag([1 1 1 1]);
referenceGridData = linear_world_field([10 10 10], referenceAffine);
candidateGridData = linear_world_field([20 20 20], candidateAffine);
write_nii_with_affine(referenceGridPath, referenceGridData, referenceAffine);
write_nii_with_affine(candidateGridPath, candidateGridData, candidateAffine);
resampled = mh_compare_single_source_backend_outputs( ...
    referenceGridPath, candidateGridPath, ...
    'Space', 'native', 'Side', 'R', 'Comparison', 'equivalence', ...
    'ResampleCandidateToReference', true);
assert(resampled.pass, ...
    'A linear field should remain equivalent on the reference grid.');
assert(resampled.efield_row.resampled_to_reference_grid, ...
    'Metrics must record candidate resampling.');
assert(resampled.efield_row.dimensions_match, ...
    'Comparison dimensions must match after candidate resampling.');

finiteMaskPath = fullfile(testRoot, 'finite_mask.nii');
finiteMaskData = referenceData;
finiteMaskData(10) = NaN;
write_nii_like(referencePath, finiteMaskPath, finiteMaskData);
assert_error_id(@() compare_equivalence(referencePath, finiteMaskPath), ...
    'mh_compare_single_source_backend_outputs:FiniteMaskMismatch');
softFiniteMask = mh_compare_single_source_backend_outputs( ...
    referencePath, finiteMaskPath, 'ThrowOnFailure', false);
assert(~softFiniteMask.pass && ...
    ~softFiniteMask.efield_row.finite_mask_match, ...
    'Soft finite-mask failure must retain a structural metrics row.');

affinePath = fullfile(testRoot, 'affine.nii');
write_nii_like(referencePath, affinePath, referenceData, 1e-6);
assert_error_id(@() compare_equivalence(referencePath, affinePath), ...
    'mh_compare_single_source_backend_outputs:AffineToleranceExceeded');
softAffine = mh_compare_single_source_backend_outputs( ...
    referencePath, affinePath, 'ThrowOnFailure', false);
assert(~softAffine.pass && ~softAffine.efield_row.pass, ...
    'Soft affine failure must retain a failed E-field metrics row.');

valuePath = fullfile(testRoot, 'value.nii');
valueData = referenceData;
valueData(100) = valueData(100) + 2e-3;
write_nii_like(referencePath, valuePath, valueData);
assert_error_id(@() compare_equivalence(referencePath, valuePath), ...
    'mh_compare_single_source_backend_outputs:ValueToleranceExceeded');
softValueResult = mh_compare_single_source_backend_outputs( ...
    referencePath, valuePath, ...
    'Space', 'native', 'Side', 'L', 'Comparison', 'equivalence', ...
    'ThrowOnFailure', false);
assert(~softValueResult.pass && ~softValueResult.efield_row.pass, ...
    'Soft continuous-gate failure must return pass=false.');
assert(height(softValueResult.binary_rows) == 3, ...
    'Soft continuous-gate failure must return all binary metrics.');

volumePath = fullfile(testRoot, 'volume.nii');
volumeReferencePath = fullfile(testRoot, 'volume_reference.nii');
volumeReferenceData = referenceData;
volumeCandidateData = referenceData;
volumeReferenceData(11:16) = 199.9996;
volumeCandidateData(11:16) = 200.0004;
write_nii_like(referencePath, volumeReferencePath, volumeReferenceData);
write_nii_like(referencePath, volumePath, volumeCandidateData);
assert_error_id(@() compare_equivalence(volumeReferencePath, volumePath), ...
    'mh_compare_single_source_backend_outputs:BinaryVolumeToleranceExceeded');
softVolumeResult = mh_compare_single_source_backend_outputs( ...
    volumeReferencePath, volumePath, ...
    'Space', 'MNI', 'Side', 'R', 'Comparison', 'equivalence', ...
    'ThrowOnFailure', false);
assert(~softVolumeResult.pass && softVolumeResult.efield_row.pass, ...
    'Soft binary-gate failure must preserve the passing E-field row.');
assert(height(softVolumeResult.binary_rows) == 3 && ...
    any(~softVolumeResult.binary_rows.pass), ...
    'Soft binary-gate failure must return all failing binary metrics.');

allNanPath = fullfile(testRoot, 'all_nan.nii');
write_nii_like(referencePath, allNanPath, nan(size(referenceData)));
assert_error_id(@() compare_equivalence(allNanPath, allNanPath), ...
    'mh_compare_single_source_backend_outputs:NoFiniteSignal');
softAllNan = mh_compare_single_source_backend_outputs( ...
    allNanPath, allNanPath, 'ThrowOnFailure', false);
assert(~softAllNan.pass && ~softAllNan.efield_row.finite_signal_present, ...
    'Soft all-NaN failure must retain an invalid E-field metrics row.');

allZeroPath = fullfile(testRoot, 'all_zero.nii');
write_nii_like(referencePath, allZeroPath, zeros(size(referenceData)));
assert_error_id(@() compare_equivalence(allZeroPath, allZeroPath), ...
    'mh_compare_single_source_backend_outputs:ZeroSignal');
softAllZero = mh_compare_single_source_backend_outputs( ...
    allZeroPath, allZeroPath, 'ThrowOnFailure', false);
assert(~softAllZero.pass && ~softAllZero.efield_row.nonzero_signal, ...
    'Soft zero-signal failure must retain an invalid E-field metrics row.');

emptyVtaPath = fullfile(testRoot, 'empty_vta.nii');
write_nii_like(referencePath, emptyVtaPath, ones(size(referenceData)) * 100);
assert_error_id(@() compare_equivalence(emptyVtaPath, emptyVtaPath), ...
    'mh_compare_single_source_backend_outputs:EmptyThresholdMask');

fprintf('Synthetic single-source backend equivalence test passed.\n');
end

function result = compare_equivalence(referencePath, candidatePath)
result = mh_compare_single_source_backend_outputs( ...
    referencePath, candidatePath, ...
    'Space', 'native', 'Side', 'L', 'Comparison', 'equivalence');
end

function assert_error_id(operation, expectedId)
actualId = '';
try
    operation();
catch ME
    actualId = ME.identifier;
end
assert(strcmp(actualId, expectedId), ...
    'Expected error ID "%s", received "%s".', expectedId, actualId);
end

function write_nii(path, data)
niftiwrite(single(data), path, 'Compressed', false);
end

function write_nii_like(templatePath, path, data, affineOffset)
if nargin < 4
    affineOffset = 0;
end
nii = ea_load_nii(templatePath);
nii.fname = path;
nii.img = double(data);
nii.mat(1, 4) = nii.mat(1, 4) + affineOffset;
ea_write_nii(nii);
end

function data = linear_world_field(dimensions, affine)
[x, y, z] = ndgrid(1:dimensions(1), 1:dimensions(2), 1:dimensions(3));
coordinates = [x(:), y(:), z(:), ones(numel(x), 1)] * affine';
values = 160 + 2 * coordinates(:, 1) + coordinates(:, 2) + ...
    0.5 * coordinates(:, 3);
data = reshape(values, dimensions);
end

function write_nii_with_affine(path, data, affine)
niftiwrite(single(data), path, 'Compressed', false);
nii = ea_load_nii(path);
nii.fname = path;
nii.img = single(data);
nii.mat = affine;
ea_write_nii(nii);
end

function cleanup_test(testRoot)
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
