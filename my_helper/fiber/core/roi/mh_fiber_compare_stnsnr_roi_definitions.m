function result = mh_fiber_compare_stnsnr_roi_definitions(varargin)
% Compare HybraPD STN/SNr labels with the custom Ewert/Zhang/Middlebrooks atlas.

parser = inputParser;
parser.FunctionName = 'mh_fiber_compare_stnsnr_roi_definitions';
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('HybraPdNii', '', @(x) ischar(x) || isstring(x));
parser.addParameter('HybraPdTxt', '', @(x) ischar(x) || isstring(x));
parser.addParameter('CustomAtlasDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('CustomThreshold', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('WriteOutputs', true, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

repoDir = char(string(opts.RepoDir));
if isempty(repoDir)
    repoDir = resolve_repo_dir(mfilename('fullpath'));
end

hybraNii = default_path(opts.HybraPdNii, fullfile(repoDir, 'templates', 'space', ...
    'MNI152NLin2009bAsym', 'labeling', 'HybraPD Whole Brain (Yu 2021).nii'));
hybraTxt = default_path(opts.HybraPdTxt, fullfile(repoDir, 'templates', 'space', ...
    'MNI152NLin2009bAsym', 'labeling', 'HybraPD Whole Brain (Yu 2021).txt'));
customDir = default_path(opts.CustomAtlasDir, fullfile(repoDir, 'templates', 'space', ...
    'MNI152NLin2009bAsym', 'atlases', 'Custom_Ewert_Zhang_Middlebrooks0.05'));
outputDir = default_path(opts.OutputDir, fullfile(repoDir, 'connectomes', 'dMRI', ...
    'public_tracking', 'STN_SNr', 'roi_definition_qc'));

must_be_file(hybraNii, 'HybraPD NIfTI');
must_be_file(hybraTxt, 'HybraPD label text');
must_be_folder(customDir, 'Custom atlas directory');

threshold = opts.CustomThreshold;
thresholdSource = 'parameter';
if isempty(threshold)
    indexPath = fullfile(customDir, 'atlas_index.mat');
    must_be_file(indexPath, 'Custom atlas index');
    atlasIndex = load(indexPath);
    if isfield(atlasIndex, 'atlases') && isfield(atlasIndex.atlases, 'threshold') && ...
            isfield(atlasIndex.atlases.threshold, 'value')
        threshold = double(atlasIndex.atlases.threshold.value);
        thresholdSource = 'atlas_index.mat';
    else
        threshold = 0.05;
        thresholdSource = 'fallback';
    end
end

hybra = ea_load_nii(hybraNii);
labelNames = read_label_names(hybraTxt);
roiDefs = { ...
    'L', 'STN', 321, 'lh', 'STN.nii.gz'; ...
    'R', 'STN', 322, 'rh', 'STN.nii.gz'; ...
    'L', 'SNr', 315, 'lh', 'SNr.nii.gz'; ...
    'R', 'SNr', 316, 'rh', 'SNr.nii.gz'};

rows = {};
for i = 1:size(roiDefs, 1)
    side = roiDefs{i, 1};
    roi = roiDefs{i, 2};
    hybraLabel = roiDefs{i, 3};
    hemiDir = roiDefs{i, 4};
    customFile = roiDefs{i, 5};
    customPath = fullfile(customDir, hemiDir, customFile);
    must_be_file(customPath, sprintf('Custom %s %s NIfTI', side, roi));

    custom = ea_load_nii(customPath);
    hybraMask = round(double(hybra.img)) == hybraLabel;
    customValues = double(custom.img);
    customMask = customValues > threshold;
    customProjectedMask = project_mask_to_reference(customMask, custom.mat, size(hybra.img), hybra.mat);

    hybraVoxelVolume = abs(det(hybra.mat(1:3, 1:3)));
    customVoxelVolume = abs(det(custom.mat(1:3, 1:3)));
    hybraVoxelCount = nnz(hybraMask);
    customNativeVoxelCount = nnz(customMask);
    customProjectedVoxelCount = nnz(customProjectedMask);
    overlapVoxelCount = nnz(hybraMask & customProjectedMask);
    unionVoxelCount = nnz(hybraMask | customProjectedMask);

    dice = 2 * overlapVoxelCount / max(1, hybraVoxelCount + customProjectedVoxelCount);
    jaccard = overlapVoxelCount / max(1, unionVoxelCount);
    hybraCentroid = mask_centroid_mm(hybraMask, hybra.mat);
    customCentroid = mask_centroid_mm(customMask, custom.mat);
    centroidDistance = sqrt(sum((hybraCentroid - customCentroid) .^ 2, 'omitnan'));

    labelName = label_name_for_id(labelNames, hybraLabel);
    rows(end+1, :) = { ...
        side, roi, hybraLabel, labelName, customPath, threshold, thresholdSource, ...
        hybraVoxelCount, hybraVoxelCount * hybraVoxelVolume, ...
        customNativeVoxelCount, customNativeVoxelCount * customVoxelVolume, ...
        customProjectedVoxelCount, customProjectedVoxelCount * hybraVoxelVolume, ...
        overlapVoxelCount, overlapVoxelCount * hybraVoxelVolume, ...
        dice, jaccard, nnz(hybraMask & ~customProjectedMask), nnz(customProjectedMask & ~hybraMask), ...
        hybraCentroid(1), hybraCentroid(2), hybraCentroid(3), ...
        customCentroid(1), customCentroid(2), customCentroid(3), ...
        centroidDistance, custom.voxsize(1), custom.voxsize(2), custom.voxsize(3), ...
        max(customValues(:))}; %#ok<AGROW>
end

summary = cell2table(rows, 'VariableNames', { ...
    'side', 'roi', 'hybra_label', 'hybra_label_name', 'custom_path', ...
    'custom_threshold', 'custom_threshold_source', ...
    'hybra_voxels_1mm', 'hybra_volume_mm3', ...
    'custom_native_voxels', 'custom_native_volume_mm3', ...
    'custom_projected_voxels_1mm', 'custom_projected_volume_mm3', ...
    'overlap_voxels_1mm', 'overlap_volume_mm3', ...
    'dice_1mm', 'jaccard_1mm', 'hybra_only_voxels_1mm', 'custom_only_voxels_1mm', ...
    'hybra_centroid_x', 'hybra_centroid_y', 'hybra_centroid_z', ...
    'custom_centroid_x', 'custom_centroid_y', 'custom_centroid_z', ...
    'centroid_distance_mm', 'custom_voxel_x_mm', 'custom_voxel_y_mm', ...
    'custom_voxel_z_mm', 'custom_max_value'});

result = struct();
result.summaryTable = summary;
result.threshold = threshold;
result.thresholdSource = thresholdSource;
result.hybraNii = hybraNii;
result.hybraTxt = hybraTxt;
result.customAtlasDir = customDir;
result.outputDir = outputDir;

if logical(opts.WriteOutputs)
    if ~isfolder(outputDir)
        mkdir(outputDir);
    end
    result.summaryCsv = fullfile(outputDir, 'stnsnr_hybrapd_vs_custom_ewert_zhang_middlebrooks005.csv');
    result.reportMd = fullfile(outputDir, 'stnsnr_hybrapd_vs_custom_ewert_zhang_middlebrooks005.md');
    writetable(summary, result.summaryCsv);
    write_markdown_report(result.reportMd, result);
end
end

function path = default_path(value, fallback)
if strlength(string(value)) == 0
    path = fallback;
else
    path = char(string(value));
end
end

function projected = project_mask_to_reference(mask, sourceMat, refSize, refMat)
projected = false(refSize);
if ~any(mask(:))
    return;
end

[x, y, z] = ind2sub(size(mask), find(mask));
xyzMm = ea_vox2mm([x, y, z], sourceMat);
refVox = round(ea_mm2vox(xyzMm, refMat));
inside = all(refVox >= 1, 2) & refVox(:, 1) <= refSize(1) & ...
    refVox(:, 2) <= refSize(2) & refVox(:, 3) <= refSize(3);
refVox = refVox(inside, :);
if isempty(refVox)
    return;
end

refInd = sub2ind(refSize, refVox(:, 1), refVox(:, 2), refVox(:, 3));
projected(unique(refInd)) = true;
end

function centroid = mask_centroid_mm(mask, mat)
if ~any(mask(:))
    centroid = [NaN, NaN, NaN];
    return;
end
[x, y, z] = ind2sub(size(mask), find(mask));
xyz = ea_vox2mm([x, y, z], mat);
centroid = mean(xyz, 1, 'omitnan');
end

function labels = read_label_names(labelTxt)
lines = readlines(labelTxt);
labels = strings(1000, 1);
for i = 1:numel(lines)
    line = strtrim(lines(i));
    if line == ""
        continue;
    end
    parts = regexp(line, '^(\d+)\s+(.+)$', 'tokens', 'once');
    if isempty(parts)
        continue;
    end
    id = str2double(parts{1});
    if id > numel(labels)
        labels(end+1:id) = "";
    end
    labels(id) = string(parts{2});
end
end

function name = label_name_for_id(labels, id)
if id <= numel(labels) && labels(id) ~= ""
    name = char(labels(id));
else
    name = '<missing label text>';
end
end

function write_markdown_report(path, result)
summary = result.summaryTable;
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_compare_stnsnr_roi_definitions:ReportOpenFailed', ...
        'Cannot write report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, '# STN/SNr ROI Definition Comparison\n\n');
fprintf(fid, '- HybraPD atlas: `%s`\n', result.hybraNii);
fprintf(fid, '- Custom atlas: `%s`\n', result.customAtlasDir);
fprintf(fid, '- Custom atlas mask rule: voxel value `> %.3f` (`%s`).\n', ...
    result.threshold, result.thresholdSource);
fprintf(fid, '- Overlap metrics are computed after projecting the custom high-resolution masks to the HybraPD 1 mm grid by nearest voxel center.\n\n');

fprintf(fid, '| Side | ROI | HybraPD label | HybraPD mm3 | Custom native mm3 | Custom projected mm3 | Overlap mm3 | Dice | Jaccard | Centroid distance mm |\n');
fprintf(fid, '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n');
for i = 1:height(summary)
    fprintf(fid, '| %s | %s | %d | %.3f | %.3f | %.3f | %.3f | %.6f | %.6f | %.3f |\n', ...
        summary.side{i}, summary.roi{i}, summary.hybra_label(i), ...
        summary.hybra_volume_mm3(i), summary.custom_native_volume_mm3(i), ...
        summary.custom_projected_volume_mm3(i), summary.overlap_volume_mm3(i), ...
        summary.dice_1mm(i), summary.jaccard_1mm(i), summary.centroid_distance_mm(i));
end
end

function must_be_file(path, label)
if ~isfile(path)
    error('mh_fiber_compare_stnsnr_roi_definitions:MissingFile', ...
        '%s is missing: %s', label, path);
end
end

function must_be_folder(path, label)
if ~isfolder(path)
    error('mh_fiber_compare_stnsnr_roi_definitions:MissingFolder', ...
        '%s is missing: %s', label, path);
end
end

function repoDir = resolve_repo_dir(startPath)
repoDir = fileparts(startPath);
while strlength(string(repoDir)) > 0
    if isfolder(fullfile(repoDir, 'templates')) && isfolder(fullfile(repoDir, 'my_helper'))
        return;
    end
    parentDir = fileparts(repoDir);
    if strcmp(parentDir, repoDir)
        break;
    end
    repoDir = parentDir;
end
error('mh_fiber_compare_stnsnr_roi_definitions:RepoRootNotFound', ...
    'Cannot resolve Lead-DBS repo root from: %s', startPath);
end
