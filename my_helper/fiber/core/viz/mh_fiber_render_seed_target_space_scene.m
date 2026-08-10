function result = mh_fiber_render_seed_target_space_scene(displayMat, outputDirectory, resultJson)
% Render one categorical target-space tractography scene from resolved inputs.

arguments
    displayMat (1,:) char
    outputDirectory (1,:) char
    resultJson (1,:) char
end

if exist(displayMat, 'file') ~= 2
    error('mh_fiber_render_seed_target_space_scene:MissingInput', ...
        'Display input does not exist: %s', displayMat);
end
if exist('ea_mnifigure', 'file') ~= 2
    error('mh_fiber_render_seed_target_space_scene:MissingLeadDBS', ...
        'ea_mnifigure was not found on the MATLAB path.');
end
if exist('mh_viz_default_fiber_views', 'file') ~= 2 || ...
        exist('mh_viz_default_fiber_scene_spec', 'file') ~= 2
    error('mh_fiber_render_seed_target_space_scene:MissingSceneContract', ...
        'Normative fiber view and scene helpers are required.');
end

data = load(displayMat);
targetIds = cellstr(string(data.target_ids(:)));
targetKeys = cellstr(string(data.target_keys(:)));
targetMaskPaths = cellstr(string(data.target_mask_paths(:)));
targetColors = double(data.target_colors);
targetAvailable = double(data.target_available_counts(:));
targetDisplayed = double(data.target_display_counts(:));
seedMaskPath = char(string(data.seed_mask_path{1}));
seedColor = double(data.seed_wireframe_color(:)');
subjectId = char(string(data.subject_id{1}));
side = char(string(data.side{1}));
seedId = char(string(data.seed_id{1}));
targetSpace = char(string(data.target_space{1}));
targetCount = numel(targetIds);

local_validate_input(data, targetCount, targetIds, targetKeys, ...
    targetMaskPaths, targetColors, targetAvailable, targetDisplayed, ...
    seedMaskPath, seedColor);

maskScratchDirectory = tempname;
mkdir(maskScratchDirectory);
maskScratchCleanup = onCleanup( ...
    @() local_remove_directory(maskScratchDirectory)); %#ok<NASGU>
for targetIndex = 1:targetCount
    targetMaskPaths{targetIndex} = local_stage_mask_copy( ...
        targetMaskPaths{targetIndex}, maskScratchDirectory, targetIndex);
end
seedMaskPath = local_stage_mask_copy( ...
    seedMaskPath, maskScratchDirectory, targetCount + 1);

if exist(outputDirectory, 'dir') ~= 7
    mkdir(outputDirectory);
end
figureDirectory = fullfile(outputDirectory, 'figures');
if exist(figureDirectory, 'dir') ~= 7
    mkdir(figureDirectory);
end
stem = sprintf('%s_%s_%s_target_fibers', subjectId, side, seedId);
figPath = fullfile(figureDirectory, [stem, '.fig']);
pngPath = fullfile(figureDirectory, [stem, '_view01.png']);
pdfPath = fullfile(figureDirectory, [stem, '_view01.pdf']);

oldVisible = get(groot, 'DefaultFigureVisible');
visibilityCleanup = onCleanup(@() set(groot, 'DefaultFigureVisible', oldVisible)); %#ok<NASGU>
set(groot, 'DefaultFigureVisible', 'off');
ea_mnifigure();
hFig = gcf;
hAx = gca;
set(hFig, 'Visible', 'off', 'Color', 'k', ...
    'Name', sprintf('%s %s %s target fibers', subjectId, side, seedId));
set(hAx, 'Color', 'none');
hold(hAx, 'on');
axis(hAx, 'equal');
axis(hAx, 'vis3d');
axis(hAx, 'off');

sceneSpec = mh_viz_default_fiber_scene_spec();
anatomyHandle = local_add_anatomy_slice(hAx, sceneSpec);
local_hide_ras_triad(hFig);

targetHandles = gobjects(targetCount, 1);
for targetIndex = 1:targetCount
    targetHandles(targetIndex) = local_add_mask_surface( ...
        hAx, targetMaskPaths{targetIndex}, targetColors(targetIndex, :), ...
        0.15, false, 1.0, ...
        sprintf('mh_seed_target_surface_%03d', targetIndex));
end

fiberHandles = gobjects(targetCount, 1);
for targetIndex = 1:targetCount
    fiberHandles(targetIndex) = local_add_fiber_layer( ...
        hAx, data.fiber_points, data.fiber_offsets_zero_based, ...
        data.fiber_target_indices_one_based, targetIndex, ...
        targetColors(targetIndex, :), 0.25, ...
        sprintf('mh_seed_target_fibers_%03d', targetIndex));
end

seedHandle = local_add_mask_surface(hAx, seedMaskPath, seedColor, ...
    0.15, true, 0.5, 'mh_seed_target_seed_wireframe');
set(hAx, 'SortMethod', 'childorder');
uistack(targetHandles, 'bottom');
if isgraphics(anatomyHandle)
    uistack(anatomyHandle, 'bottom');
end
uistack(fiberHandles, 'top');
uistack(seedHandle, 'top');

for targetIndex = 1:targetCount
    mh_fiber_add_toggle(hFig, fiberHandles(targetIndex), ...
        sprintf('%s %s fibers (%d/%d)', side, targetIds{targetIndex}, ...
        targetDisplayed(targetIndex), targetAvailable(targetIndex)), ...
        targetColors(targetIndex, :), 'on', 'seed_target_target_fiber');
    mh_fiber_add_toggle(hFig, targetHandles(targetIndex), ...
        sprintf('%s %s target', side, targetIds{targetIndex}), ...
        targetColors(targetIndex, :), 'on', 'seed_target_target_surface');
end
mh_fiber_add_toggle(hFig, seedHandle, ...
    sprintf('%s %s seed', side, seedId), seedColor, 'on', ...
    'seed_target_seed_wireframe');
mh_fiber_add_toggle(hFig, fiberHandles, 'All fibers', ...
    [0.95, 0.95, 0.95], 'on', 'seed_target_all_fibers');
mh_fiber_add_toggle(hFig, targetHandles, 'All targets', ...
    [0.75, 0.75, 0.75], 'on', 'seed_target_all_targets');

views = mh_viz_default_fiber_views();
viewSpec = views.reference{1};
local_apply_view(hAx, viewSpec);
if exist('mh_viz_apply_soft_camera_lighting', 'file') == 2
    mh_viz_apply_soft_camera_lighting(hAx);
end
mh_fiber_rebind_scene_controls(hFig);
drawnow;
savefig(hFig, figPath);
local_verify_saved_controls(figPath, 2 * targetCount + 3);

[legendHandle, legendObjects] = local_add_export_legend( ...
    hAx, targetIds, targetColors);
exportgraphics(hFig, pngPath, 'Resolution', 600, 'BackgroundColor', 'black');
exportgraphics(hFig, pdfPath, 'ContentType', 'image', 'Resolution', 600, ...
    'BackgroundColor', 'black');
delete(legendHandle);
delete(legendObjects(isgraphics(legendObjects)));

result = struct();
result.status = 'complete';
result.subject_id = subjectId;
result.side = side;
result.seed_id = seedId;
result.target_space = targetSpace;
result.target_count = targetCount;
result.fiber_layer_count = nnz(isgraphics(fiberHandles));
result.target_surface_count = nnz(isgraphics(targetHandles));
result.seed_wireframe_count = double(isgraphics(seedHandle));
result.control_count = numel(local_seed_target_controls(hFig));
result.figure_path = figPath;
result.png_path = pngPath;
result.pdf_path = pdfPath;
result.view = viewSpec;
result.scene_contract = sceneSpec;
local_write_json(resultJson, result);
close(hFig);
end


function stagedPath = local_stage_mask_copy(sourcePath, scratchDirectory, index)
if endsWith(sourcePath, '.nii.gz', 'IgnoreCase', true)
    suffix = '.nii.gz';
elseif endsWith(sourcePath, '.nii', 'IgnoreCase', true)
    suffix = '.nii';
else
    error('mh_fiber_render_seed_target_space_scene:BadMaskExtension', ...
        'Mask must use .nii or .nii.gz: %s', sourcePath);
end
stagedPath = fullfile(scratchDirectory, ...
    sprintf('mask_%03d%s', index, suffix));
[copied, message] = copyfile(sourcePath, stagedPath, 'f');
if ~copied
    error('mh_fiber_render_seed_target_space_scene:MaskStageFailed', ...
        'Could not stage mask %s: %s', sourcePath, message);
end
end


function local_remove_directory(path)
if exist(path, 'dir') == 7
    rmdir(path, 's');
end
end


function local_validate_input(data, targetCount, targetIds, targetKeys, ...
        targetMaskPaths, targetColors, targetAvailable, targetDisplayed, ...
        seedMaskPath, seedColor)
requiredFields = {'fiber_points', 'fiber_offsets_zero_based', ...
    'fiber_target_indices_one_based'};
for i = 1:numel(requiredFields)
    if ~isfield(data, requiredFields{i})
        error('mh_fiber_render_seed_target_space_scene:BadInput', ...
            'Missing display field: %s', requiredFields{i});
    end
end
if targetCount < 1 || numel(targetKeys) ~= targetCount || ...
        numel(targetMaskPaths) ~= targetCount || ...
        ~isequal(size(targetColors), [targetCount, 3]) || ...
        numel(targetAvailable) ~= targetCount || ...
        numel(targetDisplayed) ~= targetCount
    error('mh_fiber_render_seed_target_space_scene:BadTargets', ...
        'Target metadata dimensions do not agree.');
end
if any(~isfinite(targetColors), 'all') || any(targetColors < 0, 'all') || ...
        any(targetColors > 1, 'all') || size(unique(targetColors, 'rows'), 1) ~= targetCount
    error('mh_fiber_render_seed_target_space_scene:BadColors', ...
        'Target colors must be finite, distinct RGB rows in [0, 1].');
end
if numel(seedColor) ~= 3 || any(~isfinite(seedColor)) || ...
        any(seedColor < 0) || any(seedColor > 1)
    error('mh_fiber_render_seed_target_space_scene:BadSeedColor', ...
        'Seed color must be one finite RGB row in [0, 1].');
end
paths = [targetMaskPaths; {seedMaskPath}];
for i = 1:numel(paths)
    if exist(paths{i}, 'file') ~= 2
        error('mh_fiber_render_seed_target_space_scene:MissingMask', ...
            'Mask file does not exist: %s', paths{i});
    end
end
offsets = double(data.fiber_offsets_zero_based(:));
fiberTargets = double(data.fiber_target_indices_one_based(:));
if isempty(offsets) || offsets(1) ~= 0 || any(diff(offsets) < 2) || ...
        offsets(end) ~= size(data.fiber_points, 1) || ...
        numel(fiberTargets) ~= numel(offsets) - 1 || ...
        any(fiberTargets < 1) || any(fiberTargets > targetCount)
    error('mh_fiber_render_seed_target_space_scene:BadFibers', ...
        'Fiber offsets, points, or target indices are invalid.');
end
end


function handle = local_add_mask_surface(hAx, path, color, faceAlpha, ...
        wireframe, reduceFactor, tag)
nii = ea_load_nii(path);
mask = double(nii.img) > 0;
if ~any(mask(:))
    error('mh_fiber_render_seed_target_space_scene:EmptyMask', ...
        'Mask is empty: %s', path);
end
[faces, vertices] = isosurface(mask, 0.5);
if isempty(faces)
    error('mh_fiber_render_seed_target_space_scene:EmptySurface', ...
        'Mask surface is empty: %s', path);
end
vertices = [vertices(:, 2), vertices(:, 1), vertices(:, 3), ...
    ones(size(vertices, 1), 1)] * double(nii.mat)';
surface = struct('faces', faces, 'vertices', vertices(:, 1:3));
if reduceFactor < 1
    surface = reducepatch(surface, reduceFactor);
end
if wireframe
    handle = patch(hAx, surface, 'FaceColor', 'none', ...
        'EdgeColor', color, 'EdgeAlpha', faceAlpha, 'LineWidth', 0.5, ...
        'Tag', tag);
else
    handle = patch(hAx, surface, 'FaceColor', color, ...
        'FaceAlpha', faceAlpha, 'EdgeColor', 'none', 'Tag', tag);
end
end


function handle = local_add_fiber_layer(hAx, points, offsets, targetIndices, ...
        targetIndex, color, lineWidth, tag)
offsets = double(offsets(:));
targetIndices = double(targetIndices(:));
fiberRows = find(targetIndices == targetIndex);
if isempty(fiberRows)
    handle = line(hAx, nan, nan, nan, 'Color', color, ...
        'LineWidth', lineWidth, 'Tag', tag);
    return;
end
pointCount = sum(offsets(fiberRows + 1) - offsets(fiberRows));
xyz = nan(pointCount + numel(fiberRows), 3);
cursor = 1;
for i = 1:numel(fiberRows)
    row = fiberRows(i);
    first = offsets(row) + 1;
    last = offsets(row + 1);
    count = last - first + 1;
    xyz(cursor:(cursor + count - 1), :) = double(points(first:last, :));
    cursor = cursor + count + 1;
end
handle = line(hAx, xyz(:, 1), xyz(:, 2), xyz(:, 3), ...
    'Color', color, 'LineWidth', lineWidth, 'Tag', tag);
end


function handle = local_add_anatomy_slice(hAx, sceneSpec)
handle = gobjects(0);
path = char(string(sceneSpec.AnatomyNifti));
if exist(path, 'file') ~= 2
    error('mh_fiber_render_seed_target_space_scene:MissingBackdrop', ...
        'Normative anatomy backdrop does not exist: %s', path);
end
nii = ea_load_nii(path);
inverseMat = inv(double(nii.mat));
voxel = [double(sceneSpec.AnatomySliceCoordinateMm), 0, 0, 1] * inverseMat';
i = min(max(round(voxel(1)), 1), size(nii.img, 1));
[jGrid, kGrid] = ndgrid(1:size(nii.img, 2), 1:size(nii.img, 3));
iGrid = repmat(i, size(jGrid));
world = [iGrid(:), jGrid(:), kGrid(:), ones(numel(iGrid), 1)] * double(nii.mat)';
intensity = double(squeeze(nii.img(i, :, :)));
finiteValues = intensity(isfinite(intensity));
limits = prctile(finiteValues, [1, 99]);
scaled = min(max((intensity - limits(1)) / max(diff(limits), eps), 0), 1);
rgb = repmat(reshape(scaled, [size(scaled), 1]), [1, 1, 3]);
handle = surface(hAx, reshape(world(:, 1), size(jGrid)), ...
    reshape(world(:, 2), size(jGrid)), reshape(world(:, 3), size(jGrid)), ...
    rgb, 'FaceColor', 'texturemap', 'EdgeColor', 'none', ...
    'FaceAlpha', double(sceneSpec.AnatomySliceAlpha), ...
    'Tag', 'mh_seed_target_anatomy_backdrop');
end


function local_hide_ras_triad(hFig)
objects = findall(hFig, '-regexp', 'Tag', '(?i)ras');
if ~isempty(objects)
    set(objects, 'Visible', 'off');
end
end


function local_apply_view(hAx, viewSpec)
view(hAx, double(viewSpec.az), double(viewSpec.el));
camva(hAx, double(viewSpec.camva));
camup(hAx, double(viewSpec.camup));
camproj(hAx, char(string(viewSpec.camproj)));
camtarget(hAx, double(viewSpec.camtarget));
campos(hAx, double(viewSpec.campos));
end


function local_verify_saved_controls(figPath, expectedCount)
verificationFigure = openfig(figPath, 'invisible');
cleanup = onCleanup(@() close(verificationFigure)); %#ok<NASGU>
mh_fiber_rebind_scene_controls(verificationFigure);
toggles = local_seed_target_controls(verificationFigure);
if numel(toggles) ~= expectedCount
    error('mh_fiber_render_seed_target_space_scene:BadSavedControls', ...
        'Saved FIG has %d controls; expected %d.', numel(toggles), expectedCount);
end
for i = 1:numel(toggles)
    handles = getappdata(toggles(i), 'mh_fiber_target_handles');
    if isempty(handles) || ~all(isgraphics(handles))
        error('mh_fiber_render_seed_target_space_scene:BadSavedControls', ...
            'Saved FIG contains an unbound display control.');
    end
end
end


function toggles = local_seed_target_controls(hFig)
allToggles = findall(hFig, 'Type', 'uitoggletool');
keep = false(size(allToggles));
for i = 1:numel(allToggles)
    value = get(allToggles(i), 'UserData');
    if ischar(value) || (isstring(value) && isscalar(value))
        keep(i) = startsWith(char(value), 'seed_target_');
    end
end
toggles = allToggles(keep);
end


function [legendHandle, legendObjects] = local_add_export_legend(hAx, targetIds, colors)
legendObjects = gobjects(numel(targetIds), 1);
for i = 1:numel(targetIds)
    legendObjects(i) = line(hAx, nan, nan, nan, 'Color', colors(i, :), ...
        'LineWidth', 2, 'DisplayName', targetIds{i});
end
legendHandle = legend(hAx, legendObjects, targetIds, ...
    'TextColor', 'w', 'Color', 'k', 'EdgeColor', [0.3, 0.3, 0.3], ...
    'Interpreter', 'none', 'NumColumns', 2, 'Location', 'southoutside');
end


function local_write_json(path, value)
parent = fileparts(path);
if exist(parent, 'dir') ~= 7
    mkdir(parent);
end
fid = fopen(path, 'w');
if fid < 0
    error('mh_fiber_render_seed_target_space_scene:JsonWriteFailed', ...
        'Cannot write result JSON: %s', path);
end
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '%s\n', jsonencode(value, 'PrettyPrint', true));
end
