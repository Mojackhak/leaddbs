function rois = mh_fiber_make_stnsnr_custom_rois(varargin)
% Generate STN/SNr ROI masks from Custom_Ewert_Zhang_Middlebrooks0.05.

parser = inputParser;
parser.FunctionName = 'mh_fiber_make_stnsnr_custom_rois';
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('CustomAtlasDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Threshold', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

repoDir = char(string(opts.RepoDir));
if isempty(repoDir)
    repoDir = resolve_repo_dir(mfilename('fullpath'));
end

customDir = default_path(opts.CustomAtlasDir, fullfile(repoDir, 'templates', 'space', ...
    'MNI152NLin2009bAsym', 'atlases', 'Custom_Ewert_Zhang_Middlebrooks0.05'));
outputDir = default_path(opts.OutputDir, fullfile(repoDir, 'connectomes', 'dMRI', ...
    'public_tracking', 'STN_SNr', 'rois', 'Custom_Ewert_Zhang_Middlebrooks0.05'));

must_be_folder(customDir, 'Custom atlas directory');
threshold = opts.Threshold;
thresholdSource = 'parameter';
if isempty(threshold)
    [threshold, thresholdSource] = resolve_custom_threshold(customDir);
end

if ~isfolder(outputDir)
    mkdir(outputDir);
end

roiDefs = { ...
    'L', 'STN', 'lh', 'STN.nii.gz'; ...
    'R', 'STN', 'rh', 'STN.nii.gz'; ...
    'L', 'SNr', 'lh', 'SNr.nii.gz'; ...
    'R', 'SNr', 'rh', 'SNr.nii.gz'};

rois = struct();
rois.atlasName = 'Custom_Ewert_Zhang_Middlebrooks0.05';
rois.customAtlasDir = customDir;
rois.outputDir = outputDir;
rois.threshold = threshold;
rois.thresholdSource = thresholdSource;
rois.mni = struct();
reportRows = {};

for i = 1:size(roiDefs, 1)
    side = roiDefs{i, 1};
    roiName = roiDefs{i, 2};
    hemiDir = roiDefs{i, 3};
    fileName = roiDefs{i, 4};
    sourcePath = fullfile(customDir, hemiDir, fileName);
    must_be_file(sourcePath, sprintf('%s %s custom ROI', side, roiName));

    outName = sprintf('Custom_Ewert_Zhang_Middlebrooks005_%s_%s_thr%g_mni.nii', ...
        roiName, side, threshold);
    outName = strrep(outName, '.', 'p');
    outName = strrep(outName, 'pnii', '.nii');
    outPath = fullfile(outputDir, outName);

    sourceNii = ea_load_nii(sourcePath);
    values = double(sourceNii.img);
    mask = values > threshold;
    if ~any(mask(:))
        error('mh_fiber_make_stnsnr_custom_rois:EmptyRoi', ...
            'Thresholded custom ROI is empty: %s > %.6g', sourcePath, threshold);
    end

    if logical(opts.Force) || ~isfile(outPath)
        out = sourceNii;
        out.img = double(mask);
        out.dt = 2;
        out.fname = outPath;
        ea_write_nii(out);
    end

    centroid = mask_centroid_mm(mask, sourceNii.mat);
    voxelVolume = abs(det(sourceNii.mat(1:3, 1:3)));
    rois.mni.(side).(roiName) = outPath;
    rois.(side).(roiName) = outPath;
    reportRows(end+1, :) = { ...
        side, roiName, sourcePath, outPath, threshold, thresholdSource, ...
        nnz(mask), nnz(mask) * voxelVolume, ...
        sourceNii.voxsize(1), sourceNii.voxsize(2), sourceNii.voxsize(3), ...
        centroid(1), centroid(2), centroid(3), max(values(:))}; %#ok<AGROW>
end

report = cell2table(reportRows, 'VariableNames', { ...
    'side', 'roi', 'source_path', 'roi_path', 'threshold', 'threshold_source', ...
    'voxel_count', 'volume_mm3', 'voxel_x_mm', 'voxel_y_mm', 'voxel_z_mm', ...
    'centroid_x', 'centroid_y', 'centroid_z', 'max_value'});
rois.reportTable = report;
rois.reportCsv = fullfile(outputDir, 'stnsnr_custom_roi_report.csv');
rois.reportMd = fullfile(outputDir, 'stnsnr_custom_roi_report.md');
writetable(report, rois.reportCsv);
write_roi_markdown(rois.reportMd, rois);
end

function [threshold, source] = resolve_custom_threshold(customDir)
indexPath = fullfile(customDir, 'atlas_index.mat');
if isfile(indexPath)
    atlasIndex = load(indexPath);
    if isfield(atlasIndex, 'atlases') && isfield(atlasIndex.atlases, 'threshold') && ...
            isfield(atlasIndex.atlases.threshold, 'value')
        threshold = double(atlasIndex.atlases.threshold.value);
        source = 'atlas_index.mat';
        return;
    end
end
threshold = 0.05;
source = 'fallback';
end

function path = default_path(value, fallback)
if strlength(string(value)) == 0
    path = fallback;
else
    path = char(string(value));
end
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

function write_roi_markdown(path, rois)
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_make_stnsnr_custom_rois:ReportOpenFailed', ...
        'Cannot write report: %s', path);
end
cleanup = onCleanup(@() fclose(fid));
report = rois.reportTable;

fprintf(fid, '# STN/SNr Custom ROI Report\n\n');
fprintf(fid, '- Atlas: `%s`\n', rois.atlasName);
fprintf(fid, '- Atlas directory: `%s`\n', rois.customAtlasDir);
fprintf(fid, '- Mask rule: voxel value `> %.6g` (`%s`).\n', ...
    rois.threshold, rois.thresholdSource);
fprintf(fid, '- These masks are intended to be used directly for STN/SNr fiber tracking/query and scene ROI drawing.\n\n');
fprintf(fid, '| Side | ROI | Voxels | Volume mm3 | Voxel size mm | Centroid MNI |\n');
fprintf(fid, '|---|---|---:|---:|---|---|\n');
for i = 1:height(report)
    fprintf(fid, '| %s | %s | %d | %.3f | %.3f x %.3f x %.3f | [%.3f %.3f %.3f] |\n', ...
        report.side{i}, report.roi{i}, report.voxel_count(i), report.volume_mm3(i), ...
        report.voxel_x_mm(i), report.voxel_y_mm(i), report.voxel_z_mm(i), ...
        report.centroid_x(i), report.centroid_y(i), report.centroid_z(i));
end
end

function must_be_file(path, label)
if ~isfile(path)
    error('mh_fiber_make_stnsnr_custom_rois:MissingFile', ...
        '%s is missing: %s', label, path);
end
end

function must_be_folder(path, label)
if ~isfolder(path)
    error('mh_fiber_make_stnsnr_custom_rois:MissingFolder', ...
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
error('mh_fiber_make_stnsnr_custom_rois:RepoRootNotFound', ...
    'Cannot resolve Lead-DBS repo root from: %s', startPath);
end
