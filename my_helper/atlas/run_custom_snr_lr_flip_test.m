% Compare nonlinear left-to-right flipped Custom SNr with the native right SNr.

repoDir = '/Users/mojackhu/Github/leaddbs';
cd(repoDir);
addpath(genpath(repoDir));

atlasDir = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', ...
    'atlases', 'Custom_Ewert_Zhang_Middlebrooks');
lhPath = fullfile(atlasDir, 'lh', 'SNr.nii.gz');
rhPath = fullfile(atlasDir, 'rh', 'SNr.nii.gz');

outputDir = '/Volumes/VAL/STNSNr/summary/atlas_qc/lr_flip/Custom_Ewert_Zhang_Middlebrooks_SNr';
if ~isfolder(outputDir)
    mkdir(outputDir);
end

flippedPath = fullfile(outputDir, 'lh_SNr_flipped_to_right.nii.gz');
flippedOnRhPath = fullfile(outputDir, 'lh_SNr_flipped_to_right_on_rh_grid.nii.gz');
diffPath = fullfile(outputDir, 'lh_SNr_flip_vs_rh_continuous_diff.nii.gz');
metricsPath = fullfile(outputDir, 'lh_SNr_flip_vs_rh_metrics.csv');
manifestPath = fullfile(outputDir, 'lh_SNr_flip_vs_rh_manifest.json');

thresholds = [0.001, 0.01, 0.05, 0.25, 0.5];

if ~isfile(lhPath)
    error('run_custom_snr_lr_flip_test:MissingLeftSNr', 'Missing left SNr: %s', lhPath);
end
if ~isfile(rhPath)
    error('run_custom_snr_lr_flip_test:MissingRightSNr', 'Missing right SNr: %s', rhPath);
end

fprintf('Flipping left SNr to right space with ea_flip_lr_nonlinear...\n');
ea_flip_lr_nonlinear(lhPath, flippedPath);

lhNii = ea_load_nii(lhPath);
rhNii = ea_load_nii(rhPath);
flippedNii = ea_load_nii(flippedPath);

fprintf('Resampling flipped left SNr to the native right SNr grid...\n');
flippedOnRh = resample_linear_to_reference(flippedNii, rhNii);
write_like_reference(rhNii, single(flippedOnRh), flippedOnRhPath, 'lh SNr flipped to right, resampled to rh SNr grid');

rightImg = double(rhNii.img);
diffImg = flippedOnRh - rightImg;
write_like_reference(rhNii, single(diffImg), diffPath, 'lh SNr flipped to right minus native rh SNr');

fprintf('Computing continuous and thresholded metrics...\n');
metricsTable = build_metrics_table(flippedOnRh, rightImg, thresholds, voxel_volume_mm3(rhNii.mat));
writetable(metricsTable, metricsPath);

manifest = struct();
manifest.generated_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z'));
manifest.repo_dir = repoDir;
manifest.test_name = 'Custom_Ewert_Zhang_Middlebrooks_SNr_left_to_right_flip';
manifest.flip_function = 'ea_flip_lr_nonlinear';
manifest.flip_interpolation = 'Lead-DBS default; ANTs reports BSplineInterpolateImageFunction for this transform';
manifest.comparison_grid = 'native right SNr grid';
manifest.thresholds = thresholds;
manifest.inputs = struct('left_snr', lhPath, 'right_snr', rhPath);
manifest.outputs = struct( ...
    'left_snr_flipped_to_right', flippedPath, ...
    'left_snr_flipped_to_right_on_right_grid', flippedOnRhPath, ...
    'continuous_difference', diffPath, ...
    'metrics_csv', metricsPath, ...
    'manifest_json', manifestPath);
manifest.image_qc = struct( ...
    'left_snr', image_qc(lhNii), ...
    'right_snr', image_qc(rhNii), ...
    'left_snr_flipped_to_right', image_qc(flippedNii), ...
    'left_snr_flipped_to_right_on_right_grid', array_qc(flippedOnRh, rhNii.mat));

write_json(manifestPath, manifest);

fprintf('\nCustom SNr LR flip test finished.\n');
fprintf('Metrics: %s\n', metricsPath);
fprintf('Manifest: %s\n', manifestPath);
fprintf('Flipped image: %s\n', flippedPath);
fprintf('Flipped-on-right-grid image: %s\n', flippedOnRhPath);
fprintf('Difference image: %s\n', diffPath);

function sampled = resample_linear_to_reference(sourceNii, referenceNii)
sourceImg = double(sourceNii.img);
refSize = size(referenceNii.img);
sampled = zeros(refSize);

grid1 = 1:size(sourceImg, 1);
grid2 = 1:size(sourceImg, 2);
grid3 = 1:size(sourceImg, 3);
F = griddedInterpolant({grid1, grid2, grid3}, sourceImg, 'linear', 'none');

total = prod(refSize);
chunkSize = 250000;
for startIdx = 1:chunkSize:total
    stopIdx = min(total, startIdx + chunkSize - 1);
    idx = (startIdx:stopIdx)';
    [x, y, z] = ind2sub(refSize, idx);
    xyzMm = ea_vox2mm([x, y, z], referenceNii.mat);
    sourceVox = ea_mm2vox(xyzMm, sourceNii.mat);
    vals = F(sourceVox(:, 1), sourceVox(:, 2), sourceVox(:, 3));
    vals(isnan(vals)) = 0;
    sampled(idx) = vals;
end
end

function write_like_reference(referenceNii, img, outputPath, description)
out = referenceNii;
out.fname = outputPath;
out.img = img;
out.dt = [16, 0];
out.descrip = description;
ea_write_nii(out);
end

function tbl = build_metrics_table(flippedImg, rightImg, thresholds, voxelVolumeMm3)
diffImg = flippedImg - rightImg;
unionSupport = flippedImg ~= 0 | rightImg ~= 0;
if any(unionSupport(:))
    diffVals = diffImg(unionSupport);
    absDiffVals = abs(diffVals);
    flippedVals = flippedImg(unionSupport);
    rightVals = rightImg(unionSupport);
    if std(flippedVals) > 0 && std(rightVals) > 0
        corrMat = corrcoef(flippedVals, rightVals);
        pearson = corrMat(1, 2);
    else
        pearson = NaN;
    end
    continuousRow = metric_row('continuous', NaN, ...
        nnz(flippedImg ~= 0), nnz(rightImg ~= 0), NaN, nnz(unionSupport), ...
        nnz(flippedImg ~= 0) * voxelVolumeMm3, nnz(rightImg ~= 0) * voxelVolumeMm3, NaN, nnz(unionSupport) * voxelVolumeMm3, ...
        NaN, NaN, mean(diffVals), mean(absDiffVals), sqrt(mean(diffVals .^ 2)), ...
        median(absDiffVals), prctile(absDiffVals, 95), max(absDiffVals), pearson);
else
    continuousRow = metric_row('continuous', NaN, 0, 0, NaN, 0, ...
        0, 0, NaN, 0, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN);
end

rows = repmat(continuousRow, numel(thresholds) + 1, 1);
rows(1) = continuousRow;
for i = 1:numel(thresholds)
    threshold = thresholds(i);
    flippedMask = flippedImg > threshold;
    rightMask = rightImg > threshold;
    intersectionMask = flippedMask & rightMask;
    unionMask = flippedMask | rightMask;
    flippedVoxels = nnz(flippedMask);
    rightVoxels = nnz(rightMask);
    intersectionVoxels = nnz(intersectionMask);
    unionVoxels = nnz(unionMask);
    if flippedVoxels + rightVoxels > 0
        dice = 2 * intersectionVoxels / (flippedVoxels + rightVoxels);
    else
        dice = NaN;
    end
    if unionVoxels > 0
        jaccard = intersectionVoxels / unionVoxels;
    else
        jaccard = NaN;
    end
    rows(i + 1) = metric_row('threshold', threshold, ...
        flippedVoxels, rightVoxels, intersectionVoxels, unionVoxels, ...
        flippedVoxels * voxelVolumeMm3, rightVoxels * voxelVolumeMm3, ...
        intersectionVoxels * voxelVolumeMm3, unionVoxels * voxelVolumeMm3, ...
        dice, jaccard, NaN, NaN, NaN, NaN, NaN, NaN, NaN);
end
tbl = struct2table(rows);
end

function row = metric_row(metricType, threshold, flippedVoxels, rightVoxels, intersectionVoxels, unionVoxels, ...
        flippedVolume, rightVolume, intersectionVolume, unionVolume, dice, jaccard, meanDiff, meanAbsDiff, ...
        rmse, medianAbsDiff, p95AbsDiff, maxAbsDiff, pearson)
row = struct();
row.metric_type = string(metricType);
row.threshold = threshold;
row.flipped_voxels = flippedVoxels;
row.right_voxels = rightVoxels;
row.intersection_voxels = intersectionVoxels;
row.union_voxels = unionVoxels;
row.flipped_volume_mm3 = flippedVolume;
row.right_volume_mm3 = rightVolume;
row.intersection_volume_mm3 = intersectionVolume;
row.union_volume_mm3 = unionVolume;
row.dice = dice;
row.jaccard = jaccard;
row.mean_diff = meanDiff;
row.mean_abs_diff = meanAbsDiff;
row.rmse = rmse;
row.median_abs_diff = medianAbsDiff;
row.p95_abs_diff = p95AbsDiff;
row.max_abs_diff = maxAbsDiff;
row.pearson = pearson;
end

function qc = image_qc(nii)
qc = array_qc(double(nii.img), nii.mat);
qc.fname = nii.fname;
end

function qc = array_qc(img, mat)
finiteVals = img(isfinite(img));
nonzeroVals = finiteVals(finiteVals ~= 0);
qc = struct();
qc.size = size(img);
qc.voxel_volume_mm3 = voxel_volume_mm3(mat);
qc.affine = mat;
qc.min = min(finiteVals(:));
qc.max = max(finiteVals(:));
qc.sum = sum(finiteVals(:));
qc.nonzero_voxels = numel(nonzeroVals);
if isempty(nonzeroVals)
    qc.nonzero_percentiles = [];
else
    qc.nonzero_percentiles = prctile(nonzeroVals, [1, 5, 25, 50, 75, 95, 99]);
end
end

function volume = voxel_volume_mm3(mat)
volume = abs(det(mat(1:3, 1:3)));
end

function write_json(path, data)
fid = fopen(path, 'w');
if fid < 0
    error('run_custom_snr_lr_flip_test:JsonOpenFailed', 'Cannot write JSON: %s', path);
end
cleanupObj = onCleanup(@() fclose(fid));
try
    encoded = jsonencode(data, 'PrettyPrint', true);
catch
    encoded = jsonencode(data);
end
fprintf(fid, '%s\n', encoded);
clear cleanupObj;
end
