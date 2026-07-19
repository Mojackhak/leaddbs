function scene = mh_viz_make_sweet_sour_scene(spec)
% Render sweet/sour voxel surfaces and fibers in one ea_mnifigure scene.
%
% Required input is a scalar struct. VoxelSignedNifti uses the migrated MyLFP
% signed-heatmap surface contract with a symmetric vik colormap and right-side
% colorbar. VoxelSweetNifti and VoxelSourNifti are optional binary overlays.
% Fiber MAT files must contain Lead-DBS `fibers`, `idx`, and `scores` variables
% after canonical model fiber IDs have been resolved to geometry.

if nargin < 1 || ~isstruct(spec) || ~isscalar(spec)
    error('mh_viz_make_sweet_sour_scene:BadSpec', ...
        'spec must be a scalar struct.');
end
if exist('ea_mnifigure', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingLeadDBS', ...
        'ea_mnifigure was not found. Add Lead-DBS to the MATLAB path.');
end

spec = local_apply_defaults(spec);
sourceFields = {'VoxelSignedNifti', 'VoxelSweetNifti', 'VoxelSourNifti', ...
    'FiberScoreMat', 'FiberSweetMat', 'FiberSourMat'};
hasSource = false;
for i = 1:numel(sourceFields)
    hasSource = hasSource || strlength(string(spec.(sourceFields{i}))) > 0;
end
if ~hasSource
    error('mh_viz_make_sweet_sour_scene:MissingSource', ...
        'At least one signed voxel, selection mask, or fiber source is required.');
end

figuresBefore = findall(groot, 'Type', 'figure');
visibilityCleanup = []; %#ok<NASGU>
if strcmpi(spec.FigureVisible, 'off')
    oldVisible = get(groot, 'DefaultFigureVisible');
    set(groot, 'DefaultFigureVisible', 'off');
    visibilityCleanup = onCleanup(@() set(groot, 'DefaultFigureVisible', oldVisible));
end

usesReferenceVoxelHeatmap = strlength(string(spec.VoxelSignedNifti)) > 0;
voxelHeatmap = [];
rasTriad = [];
colorbarHandle = [];
fiberColorbarAxes = [];
if usesReferenceVoxelHeatmap
    [hFig, hAx, voxelHeatmap, rasTriad, colorbarHandle] = ...
        local_open_signed_voxel_scene(spec);
else
    if strlength(string(spec.AtlasName)) > 0
        ea_mnifigure(char(string(spec.AtlasName)));
    else
        ea_mnifigure();
    end
    hFig = gcf;
    hAx = gca;
    set(hFig, 'Color', spec.BackgroundColor);
    hold(hAx, 'on');
    axis(hAx, 'equal');
    axis(hAx, 'vis3d');
    axis(hAx, 'off');
    local_apply_reference_font(hFig, hAx);
end
anatomySlices = findall(hAx, 'Type', 'surface');
if usesReferenceVoxelHeatmap
    local_freeze_anatomy_truecolor(anatomySlices);
end
if ~spec.ShowAnatomySlices
    set(anatomySlices, 'Visible', 'off');
elseif ~usesReferenceVoxelHeatmap
    for i = 1:numel(anatomySlices)
        try
            set(anatomySlices(i), 'FaceAlpha', spec.AnatomySliceAlpha);
        catch
        end
    end
end

if strcmpi(spec.FigureVisible, 'off')
    newFigures = setdiff(findall(groot, 'Type', 'figure'), figuresBefore);
    set([hFig; newFigures(:)], 'Visible', 'off');
    clear visibilityCleanup;
elseif strcmpi(spec.FigureVisible, 'on')
    set(hFig, 'Visible', 'on');
end

objects = struct('anatomySlices', anatomySlices, ...
    'voxelHeatmap', voxelHeatmap, ...
    'voxelSweet', [], 'voxelSour', [], ...
    'fiberScored', [], 'fiberSweet', [], 'fiberSour', [], ...
    'fiberColorLimit', [], ...
    'fiberColorbarAxes', fiberColorbarAxes, ...
    'rasTriad', rasTriad, 'colorbar', colorbarHandle);
objects.voxelSweet = local_add_voxel_surface(hAx, spec.VoxelSweetNifti, ...
    spec.SweetColor, spec.VoxelAlpha, spec.VoxelThreshold, ...
    spec.SurfaceSmoothingIters, 'mh_viz_voxel_sweet', 'Sweet voxel');
objects.voxelSour = local_add_voxel_surface(hAx, spec.VoxelSourNifti, ...
    spec.SourColor, spec.VoxelAlpha, spec.VoxelThreshold, ...
    spec.SurfaceSmoothingIters, 'mh_viz_voxel_sour', 'Sour voxel');
fiberColorLimit = local_resolve_fiber_color_limit(spec);
objects.fiberColorLimit = fiberColorLimit;
objects.fiberScored = local_add_scored_fibers(hFig, hAx, spec.FiberScoreMat, ...
    spec.FiberAlpha, fiberColorLimit, 'mh_viz_fiber_scored', 'Scored fiber');
objects.fiberSweet = local_add_scored_fibers(hFig, hAx, spec.FiberSweetMat, ...
    spec.FiberAlpha, fiberColorLimit, 'mh_viz_fiber_sweet', 'Sweet fiber');
objects.fiberSour = local_add_scored_fibers(hFig, hAx, spec.FiberSourMat, ...
    spec.FiberAlpha, fiberColorLimit, 'mh_viz_fiber_sour', 'Sour fiber');
if ~isempty(fiberColorLimit) && isempty(colorbarHandle)
    [colorbarHandle, fiberColorbarAxes] = local_add_fiber_colorbar( ...
        hAx, fiberColorLimit, spec.FiberColorbarLabel);
    objects.colorbar = colorbarHandle;
    objects.fiberColorbarAxes = fiberColorbarAxes;
end

if spec.AddToolbarToggles && exist('mh_fiber_add_toggle', 'file') == 2
    vikColors = ea_colormap_vik(256);
    local_add_toggle(hFig, objects.voxelHeatmap, 'Voxel heatmap', ...
        [0.45, 0.45, 0.45], 'voxel');
    local_add_toggle(hFig, objects.voxelSweet, 'Sweet voxel', spec.SweetColor, 'voxel');
    local_add_toggle(hFig, objects.voxelSour, 'Sour voxel', spec.SourColor, 'voxel');
    local_add_toggle(hFig, objects.fiberScored, 'Scored fiber', ...
        [0.45, 0.45, 0.45], 'fiber');
    local_add_toggle(hFig, objects.fiberSweet, 'Sweet fiber', ...
        vikColors(end, :), 'fiber');
    local_add_toggle(hFig, objects.fiberSour, 'Sour fiber', ...
        vikColors(1, :), 'fiber');
end

if ~usesReferenceVoxelHeatmap
    if ~isempty(spec.ViewStruct)
        if exist('ea_apply_view_struct', 'file') == 2
            ea_apply_view_struct(spec.ViewStruct, hAx);
        else
            local_apply_view_struct(spec.ViewStruct, hAx);
        end
    else
        view(hAx, 3);
        camproj(hAx, 'orthographic');
    end
end
if spec.AddRASTriad && isempty(rasTriad) && exist('ea_add_ras_triad', 'file') == 2
    rasTriad = local_add_reference_ras_triad(hAx, spec.RASColors);
    objects.rasTriad = rasTriad;
end

if ~usesReferenceVoxelHeatmap
    local_apply_lighting(hAx);
end
setappdata(hFig, 'mh_viz_sweet_sour_scene_spec', spec);
setappdata(hFig, 'mh_viz_sweet_sour_objects', objects);
drawnow;

scene = struct();
scene.figure = hFig;
scene.axes = hAx;
scene.objects = objects;
scene.fig = '';
scene.image = '';
scene.pdf = '';
scene.spin = '';

if strlength(string(spec.OutputFig)) > 0
    local_ensure_parent(spec.OutputFig);
    savefig(hFig, char(string(spec.OutputFig)));
    scene.fig = char(string(spec.OutputFig));
end
if strlength(string(spec.OutputImage)) > 0
    local_ensure_parent(spec.OutputImage);
    local_export_scene(hFig, spec.OutputImage, spec);
    scene.image = char(string(spec.OutputImage));
end
if strlength(string(spec.OutputPdf)) > 0
    local_ensure_parent(spec.OutputPdf);
    local_export_scene(hFig, spec.OutputPdf, spec);
    scene.pdf = char(string(spec.OutputPdf));
end
if strlength(string(spec.OutputSpin)) > 0
    if exist('ea_export_mnifigure_spin', 'file') ~= 2
        error('mh_viz_make_sweet_sour_scene:MissingSpinExporter', ...
            'ea_export_mnifigure_spin was not found.');
    end
    local_ensure_parent(spec.OutputSpin);
    ea_export_mnifigure_spin(hFig, hAx, char(string(spec.OutputSpin)), ...
        'NumFrames', spec.SpinFrames, 'FrameRate', spec.SpinFrameRate, ...
        'BgColor', spec.BackgroundColor);
    scene.spin = char(string(spec.OutputSpin));
end

if spec.CloseAfterExport && isgraphics(hFig)
    close(hFig);
    scene.figure = [];
    scene.axes = [];
end
end

function spec = local_apply_defaults(spec)
defaults = struct();
defaults.VoxelSignedNifti = '';
defaults.VoxelTemplateNifti = '';
defaults.VoxelColorbarLabel = '';
defaults.VoxelSampleDepthMm = [];
defaults.VoxelSweetNifti = '';
defaults.VoxelSourNifti = '';
defaults.FiberScoreMat = '';
defaults.FiberSweetMat = '';
defaults.FiberSourMat = '';
defaults.AtlasName = '';
defaults.SweetColor = [0.77, 0.14, 0.24];
defaults.SourColor = [0.12, 0.35, 0.68];
defaults.VoxelAlpha = 0.72;
defaults.FiberAlpha = 0.32;
defaults.FiberColorLimit = [];
defaults.FiberColorbarLabel = 'Fiber score';
defaults.VoxelThreshold = 0.5;
defaults.SurfaceSmoothingIters = 10;
defaults.ViewStruct = [];
defaults.ShowAnatomySlices = true;
defaults.AnatomySliceAlpha = 0.18;
defaults.AddRASTriad = true;
defaults.RASColors = [242, 0, 14; 14, 106, 175; 12, 162, 40] / 255;
defaults.AddToolbarToggles = true;
defaults.FontName = 'Arial';
defaults.BackgroundColor = [1, 1, 1];
defaults.FigureVisible = 'on';
defaults.OutputFig = '';
defaults.OutputImage = '';
defaults.OutputPdf = '';
defaults.OutputSpin = '';
defaults.ExportResolution = 450;
defaults.ExportRenderer = 'opengl';
defaults.ExportContentType = 'mixed';
defaults.UseSymbolForGreek = false;
defaults.SpinFrames = 240;
defaults.SpinFrameRate = 30;
defaults.CloseAfterExport = false;

names = fieldnames(defaults);
for i = 1:numel(names)
    name = names{i};
    if ~isfield(spec, name) || isempty(spec.(name))
        spec.(name) = defaults.(name);
    end
end
local_validate_color(spec.SweetColor, 'SweetColor');
local_validate_color(spec.SourColor, 'SourColor');
local_validate_color(spec.BackgroundColor, 'BackgroundColor');
if ~isnumeric(spec.RASColors) || ~isequal(size(spec.RASColors), [3, 3]) || ...
        any(~isfinite(spec.RASColors), 'all') || ...
        any(spec.RASColors < 0, 'all') || any(spec.RASColors > 1, 'all')
    error('mh_viz_make_sweet_sour_scene:BadRASColors', ...
        'RASColors must be a finite 3-by-3 RGB matrix within zero and one.');
end
local_validate_unit(spec.VoxelAlpha, 'VoxelAlpha');
local_validate_unit(spec.FiberAlpha, 'FiberAlpha');
local_validate_unit(spec.AnatomySliceAlpha, 'AnatomySliceAlpha');
if ~isempty(spec.VoxelSampleDepthMm) && ...
        (~isnumeric(spec.VoxelSampleDepthMm) || ...
        ~isscalar(spec.VoxelSampleDepthMm) || ...
        ~isfinite(spec.VoxelSampleDepthMm) || ...
        spec.VoxelSampleDepthMm < 0)
    error('mh_viz_make_sweet_sour_scene:BadVoxelSampleDepth', ...
        'VoxelSampleDepthMm must be empty or a nonnegative finite scalar.');
end
if ~isempty(spec.FiberColorLimit) && ...
        (~isnumeric(spec.FiberColorLimit) || ...
        ~isscalar(spec.FiberColorLimit) || ...
        ~isfinite(spec.FiberColorLimit) || spec.FiberColorLimit <= 0)
    error('mh_viz_make_sweet_sour_scene:BadFiberColorLimit', ...
        'FiberColorLimit must be empty or a positive finite scalar.');
end
if ~isnumeric(spec.VoxelThreshold) || ~isscalar(spec.VoxelThreshold) || ...
        ~isfinite(spec.VoxelThreshold)
    error('mh_viz_make_sweet_sour_scene:BadThreshold', ...
        'VoxelThreshold must be a finite scalar.');
end
if ~isnumeric(spec.SurfaceSmoothingIters) || ...
        ~isscalar(spec.SurfaceSmoothingIters) || ...
        spec.SurfaceSmoothingIters < 0 || ...
        mod(spec.SurfaceSmoothingIters, 1) ~= 0
    error('mh_viz_make_sweet_sour_scene:BadSmoothingIterations', ...
        'SurfaceSmoothingIters must be a nonnegative integer.');
end
if ~any(strcmpi(char(string(spec.FigureVisible)), {'on', 'off'}))
    error('mh_viz_make_sweet_sour_scene:BadVisibility', ...
        'FigureVisible must be on or off.');
end
if ~(ischar(spec.VoxelColorbarLabel) || ...
        (isstring(spec.VoxelColorbarLabel) && isscalar(spec.VoxelColorbarLabel)))
    error('mh_viz_make_sweet_sour_scene:BadColorbarLabel', ...
        'VoxelColorbarLabel must be text.');
end
if ~(ischar(spec.FiberColorbarLabel) || ...
        (isstring(spec.FiberColorbarLabel) && isscalar(spec.FiberColorbarLabel)))
    error('mh_viz_make_sweet_sour_scene:BadFiberColorbarLabel', ...
        'FiberColorbarLabel must be text.');
end
if strlength(string(spec.OutputPdf)) > 0
    [~, ~, extension] = fileparts(char(string(spec.OutputPdf)));
    if ~strcmpi(extension, '.pdf')
        error('mh_viz_make_sweet_sour_scene:BadPdfPath', ...
            'OutputPdf must use the .pdf extension.');
    end
end
validContentTypes = {'auto', 'vector', 'image', 'mixed'};
if ~any(strcmpi(char(string(spec.ExportContentType)), validContentTypes))
    error('mh_viz_make_sweet_sour_scene:BadExportContentType', ...
        'ExportContentType must be auto, vector, image, or mixed.');
end
end

function [hFig, hAx, voxelHandles, triad, hCb] = ...
        local_open_signed_voxel_scene(spec)
requiredFunctions = {'default_nifti2patch_config', ...
    'default_plot_patch_config', 'struct2namevalue', ...
    'ea_nifti2patch', 'ea_plot_patch_leaddbs'};
for i = 1:numel(requiredFunctions)
    if exist(requiredFunctions{i}, 'file') ~= 2
        error('mh_viz_make_sweet_sour_scene:MissingSurfaceHelper', ...
            'Required migrated MyLFP helper was not found: %s', ...
            requiredFunctions{i});
    end
end

signedPath = char(string(spec.VoxelSignedNifti));
if ~isfile(signedPath)
    error('mh_viz_make_sweet_sour_scene:MissingSignedVoxelFile', ...
        'Signed voxel NIfTI does not exist: %s', signedPath);
end

niftiConfig = default_nifti2patch_config();
if ~isempty(spec.VoxelSampleDepthMm)
    niftiConfig.SampleDepthMm = spec.VoxelSampleDepthMm;
end
if strlength(string(spec.VoxelTemplateNifti)) > 0
    templatePath = char(string(spec.VoxelTemplateNifti));
    if ~isfile(templatePath)
        error('mh_viz_make_sweet_sour_scene:MissingVoxelTemplate', ...
            'Voxel template NIfTI does not exist: %s', templatePath);
    end
    niftiConfig.TemplateNifti = templatePath;
end
niftiArgs = struct2namevalue(niftiConfig);
patchObject = ea_nifti2patch(signedPath, niftiArgs{:});

plotConfig = default_plot_patch_config();
plotConfig.AtlasName = char(string(spec.AtlasName));
plotConfig.ViewStruct = spec.ViewStruct;
plotConfig.ColorbarLabel = char(string(spec.VoxelColorbarLabel));
plotConfig.RASTriadColors = spec.RASColors;
plotConfig.AddRASTriad = logical(spec.AddRASTriad);
plotConfig.FigureVisible = char(string(spec.FigureVisible));
plotConfig.ExportFile = '';
plotArgs = struct2namevalue(plotConfig);
[hFig, hAx, hPatch, triad, ~, hCb, hMissingPatch, hBlendPatch] = ...
    ea_plot_patch_leaddbs(patchObject, plotArgs{:});
voxelHandles = [hPatch(:); hMissingPatch(:); hBlendPatch(:)];
for i = 1:numel(voxelHandles)
    if isgraphics(voxelHandles(i))
        setappdata(voxelHandles(i), 'mh_viz_type', 'voxel_heatmap');
        setappdata(voxelHandles(i), 'mh_viz_source', signedPath);
    end
end
end

function triad = local_add_reference_ras_triad(hAx, rasColors)
if exist('default_plot_patch_config', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingPlotDefaults', ...
        'default_plot_patch_config was not found.');
end
plotConfig = default_plot_patch_config();
triad = ea_add_ras_triad(hAx, ...
    'Colors', rasColors, ...
    'Location', plotConfig.RASTriadLocation, ...
    'Size', 0.18, ...
    'Padding', 0.02, ...
    'AxesPadding', plotConfig.RASTriadAxesPadding, ...
    'Length', 1, ...
    'LineWidth', plotConfig.RASTriadLineWidth, ...
    'HeadSize', plotConfig.RASTriadHeadSize, ...
    'FontSize', plotConfig.RASTriadFontSize, ...
    'FontName', plotConfig.FontName);
end

function handle = local_add_voxel_surface(hAx, pathValue, color, alphaValue, ...
        threshold, smoothingIters, tag, label)
handle = [];
pathValue = char(string(pathValue));
if isempty(pathValue)
    return;
end
if ~isfile(pathValue)
    error('mh_viz_make_sweet_sour_scene:MissingVoxelFile', ...
        'Voxel NIfTI does not exist: %s', pathValue);
end
patchObject = ea_nifti2patch(pathValue, ...
    'SurfaceMode', 'mask', ...
    'MaskThreshold', threshold, ...
    'MaskIsovalue', 0.5, ...
    'VolumeSmoothingSigmaMm', 0, ...
    'SurfaceSmoothingIters', smoothingIters, ...
    'SurfaceSmoothingMethod', 'taubin', ...
    'SurfaceSmoothingLambda', 0.5, ...
    'SurfaceSmoothingMu', -0.1, ...
    'Alpha', alphaValue, ...
    'ReduceFactor', 1);
handle = patch(hAx, ...
    'Faces', patchObject.faces, ...
    'Vertices', patchObject.vertices, ...
    'FaceColor', color, ...
    'EdgeColor', 'none', ...
    'FaceAlpha', alphaValue, ...
    'FaceLighting', 'gouraud', ...
    'EdgeLighting', 'gouraud', ...
    'Tag', tag, ...
    'DisplayName', label, ...
    'UserData', struct('mh_viz_type', 'voxel', 'label', label, 'source', pathValue));
end

function colorLimit = local_resolve_fiber_color_limit(spec)
paths = {spec.FiberScoreMat, spec.FiberSweetMat, spec.FiberSourMat};
hasFiberSource = any(cellfun(@(value) ...
    strlength(string(value)) > 0, paths));
if ~hasFiberSource
    colorLimit = [];
    return;
end
if ~isempty(spec.FiberColorLimit)
    colorLimit = double(spec.FiberColorLimit);
    return;
end

allScores = [];
for i = 1:numel(paths)
    pathValue = char(string(paths{i}));
    if isempty(pathValue)
        continue;
    end
    if ~isfile(pathValue)
        error('mh_viz_make_sweet_sour_scene:MissingFiberFile', ...
            'Fiber MAT does not exist: %s', pathValue);
    end
    data = load(pathValue, 'scores');
    if ~isfield(data, 'scores')
        error('mh_viz_make_sweet_sour_scene:MissingFiberScores', ...
            'Fiber MAT must contain one scores value per fiber: %s', pathValue);
    end
    allScores = [allScores; double(data.scores(:))]; %#ok<AGROW>
end
finiteScores = allScores(isfinite(allScores));
if isempty(finiteScores) || max(abs(finiteScores)) <= 0
    error('mh_viz_make_sweet_sour_scene:NoFiniteFiberScores', ...
        'Fiber score inputs must contain at least one finite nonzero value.');
end
colorLimit = max(abs(finiteScores));
end

function handle = local_add_scored_fibers( ...
        hFig, hAx, pathValue, alphaValue, colorLimit, tag, label)
handle = [];
pathValue = char(string(pathValue));
if isempty(pathValue)
    return;
end
if ~isfile(pathValue)
    error('mh_viz_make_sweet_sour_scene:MissingFiberFile', ...
        'Fiber MAT does not exist: %s', pathValue);
end
data = load(pathValue, 'fibers', 'idx', 'scores');
if ~isfield(data, 'fibers') || ~isfield(data, 'idx') || ...
        ~isfield(data, 'scores') || isempty(data.idx)
    error('mh_viz_make_sweet_sour_scene:BadFiberFile', ...
        ['Fiber MAT must contain nonempty fibers and idx variables plus ', ...
         'one scores value per fiber: %s'], pathValue);
end
set(0, 'CurrentFigure', hFig);
axes(hAx);
handle = mh_viz_show_scored_fibers( ...
    data.fibers(:, 1:3), data.idx, data.scores, colorLimit, alphaValue);
valid = handle(isgraphics(handle));
for i = 1:numel(valid)
    set(valid(i), 'Tag', tag, 'DisplayName', label, ...
        'UserData', struct('mh_viz_type', 'fiber', 'label', label, ...
        'source', pathValue, 'fiber_count', numel(data.idx), ...
        'score_color_limit', colorLimit, 'colormap', 'vik'));
end
end

function [hCb, hColorbarAx] = local_add_fiber_colorbar(hAx, colorLimit, label)
if exist('default_plot_patch_config', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingPlotDefaults', ...
        'default_plot_patch_config was not found.');
end
plotConfig = default_plot_patch_config();
fiberColorMap = ea_colormap_vik(256);
hFig = ancestor(hAx, 'figure');
hColorbarAx = axes('Parent', hFig, ...
    'Units', 'normalized', ...
    'Position', [0, 0, 0.001, 0.001], ...
    'Visible', 'off', ...
    'Color', 'none', ...
    'HitTest', 'off', ...
    'Tag', 'mh_viz_fiber_colorbar_axes');
try
    hColorbarAx.PickableParts = 'none';
catch
end
colormap(hColorbarAx, fiberColorMap);
set(hColorbarAx, 'CLim', [-colorLimit, colorLimit], 'CLimMode', 'manual');
hCb = colorbar(hColorbarAx, 'Location', 'eastoutside');
hCb.Limits = [-colorLimit, colorLimit];
hCb.LimitsMode = 'manual';
hCb.Ticks = linspace(-colorLimit, colorLimit, 5);
setappdata(hCb, 'SurfaceColormap', fiberColorMap);
hCb.Units = plotConfig.ColorbarUnits;
hCb.Position = plotConfig.ColorbarPosition;
hCb.LineWidth = plotConfig.ColorbarLineWidth;
hCb.Color = plotConfig.ColorbarTickColor;
hCb.FontName = plotConfig.FontName;
hCb.FontSize = plotConfig.ColorbarTickFontSize;
hCb.TickLabelInterpreter = plotConfig.ColorbarTickLabelInterpreter;
hCb.Label.String = char(string(label));
hCb.Label.Color = plotConfig.ColorbarLabelColor;
hCb.Label.FontName = plotConfig.FontName;
hCb.Label.FontSize = plotConfig.ColorbarLabelFontSize;
hCb.Label.Interpreter = plotConfig.ColorbarLabelInterpreter;
hAx.Units = 'normalized';
hAx.Position = plotConfig.PlotAxesPosition;
hColorbarAx.Position = [0, 0, 0.001, 0.001];
end

function local_add_toggle(hFig, objectHandle, label, color, objectType)
if isempty(objectHandle)
    return;
end
try
    mh_fiber_add_toggle(hFig, objectHandle, label, color, 'on', objectType);
catch ME
    warning('mh_viz_make_sweet_sour_scene:ToggleFailed', ...
        'Could not add the %s toggle: %s', label, ME.message);
end
end

function local_apply_reference_font(hFig, hAx)
if exist('default_plot_patch_config', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingPlotDefaults', ...
        'default_plot_patch_config was not found.');
end
plotConfig = default_plot_patch_config();
set(hFig, ...
    'DefaultAxesFontName', plotConfig.FontName, ...
    'DefaultTextFontName', plotConfig.FontName);
set(hAx, 'FontName', plotConfig.FontName);
end

function local_export_scene(hFig, outputPath, spec)
outputPath = char(string(outputPath));
if exist('ea_export_figure_transparent', 'file') == 2
    ea_export_figure_transparent(hFig, outputPath, ...
        'BackgroundColor', spec.BackgroundColor, ...
        'Resolution', spec.ExportResolution, ...
        'Renderer', spec.ExportRenderer, ...
        'ContentType', spec.ExportContentType, ...
        'UseSymbolForGreek', logical(spec.UseSymbolForGreek));
else
    [~, ~, extension] = fileparts(outputPath);
    if strcmpi(extension, '.pdf')
        exportgraphics(hFig, outputPath, ...
            'ContentType', char(string(spec.ExportContentType)), ...
            'BackgroundColor', spec.BackgroundColor);
    else
        exportgraphics(hFig, outputPath, ...
            'Resolution', spec.ExportResolution, ...
            'BackgroundColor', spec.BackgroundColor);
    end
end
end

function local_apply_view_struct(viewStruct, hAx)
fields = {'CameraPosition', 'CameraTarget', 'CameraUpVector', ...
    'CameraViewAngle', 'Projection'};
sourceFields = {'campos', 'camtarget', 'camup', 'camva', 'camproj'};
for i = 1:numel(fields)
    if isfield(viewStruct, sourceFields{i})
        set(hAx, fields{i}, viewStruct.(sourceFields{i}));
    end
end
if isfield(viewStruct, 'az') && isfield(viewStruct, 'el')
    view(hAx, viewStruct.az, viewStruct.el);
end
end

function local_apply_lighting(hAx)
try
    delete(findall(hAx, 'Type', 'light'));
catch
end
try
    camlight(hAx, 'headlight');
    camlight(hAx, -35, 20);
    lighting(hAx, 'gouraud');
    material(hAx, 'dull');
catch ME
    warning('mh_viz_make_sweet_sour_scene:LightingFailed', ...
        'Could not apply scene lighting: %s', ME.message);
end
end

function local_freeze_anatomy_truecolor(anatomySlices)
scalarData = cell(numel(anatomySlices), 1);
finiteValues = [];
for i = 1:numel(anatomySlices)
    data = get(anatomySlices(i), 'CData');
    if ~isnumeric(data) || ~ismatrix(data)
        continue;
    end
    data = double(data);
    scalarData{i} = data;
    finiteValues = [finiteValues; data(isfinite(data))]; %#ok<AGROW>
end
if isempty(finiteValues)
    return;
end
lower = min(finiteValues);
upper = max(finiteValues);
for i = 1:numel(anatomySlices)
    data = scalarData{i};
    if isempty(data)
        continue;
    end
    if upper > lower
        gray = (data - lower) / (upper - lower);
    else
        gray = 0.5 * ones(size(data));
    end
    gray(~isfinite(gray)) = 0;
    gray = max(0, min(1, gray));
    set(anatomySlices(i), ...
        'CData', repmat(gray, 1, 1, 3), ...
        'CDataMapping', 'direct');
    setappdata(anatomySlices(i), 'mh_viz_anatomy_truecolor', true);
end
end

function local_validate_color(value, name)
if ~isnumeric(value) || numel(value) ~= 3 || any(~isfinite(value)) || ...
        any(value < 0) || any(value > 1)
    error('mh_viz_make_sweet_sour_scene:BadColor', ...
        '%s must be a three-element RGB value from zero through one.', name);
end
end

function local_validate_unit(value, name)
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || ...
        value < 0 || value > 1
    error('mh_viz_make_sweet_sour_scene:BadAlpha', ...
        '%s must be a scalar from zero through one.', name);
end
end

function local_ensure_parent(pathValue)
parent = fileparts(char(string(pathValue)));
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
end
