function scene = mh_viz_make_sweet_sour_scene(spec)
% Render sweet/sour voxel surfaces and fibers in one ea_mnifigure scene.
%
% Required input is a scalar struct. VoxelSignedNifti uses the migrated MyLFP
% signed-heatmap surface contract with a symmetric vik colormap and right-side
% colorbar. VoxelSweetNifti and VoxelSourNifti are optional binary overlays.
% FiberCategoricalMat contains the complete candidate axis with aligned
% `fibers`, `idx`, `scores`, `fiber_ids`, and `fiber_roles` variables.
% FiberCoefficientMat renders the same complete axis from its continuous
% `scores` coefficients with a symmetric vik colorbar and no count legend.
% Legacy scored fiber MAT inputs remain supported independently.

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
    'FiberCategoricalMat', 'FiberCoefficientMat', 'FiberScoreMat', ...
    'FiberSweetMat', 'FiberSourMat'};
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
    useMatlabBackend = strcmpi(spec.FigureBackend, 'matlab') || ...
        (strcmpi(spec.FigureBackend, 'auto') && spec.StrictHeadless && ...
        strcmpi(spec.FigureVisible, 'off'));
    if useMatlabBackend
        plotConfig = default_plot_patch_config();
        hFig = figure('Visible', char(string(spec.FigureVisible)), ...
            'Color', spec.BackgroundColor, ...
            'Position', plotConfig.FigurePosition);
        hAx = axes('Parent', hFig, ...
            'Position', plotConfig.PlotAxesPosition);
    else
        ea_mnifigure();
        hFig = gcf;
        hAx = gca;
    end
    hold(hAx, 'on');
    axis(hAx, 'equal');
    axis(hAx, 'vis3d');
    axis(hAx, 'off');
    local_apply_reference_font(hFig, hAx);
end
set(hFig, 'Color', spec.BackgroundColor);
set(hAx, 'Color', 'none');
explicitAnatomySlice = local_add_explicit_anatomy_slice(hFig, hAx, spec);
anatomySlices = findall(hAx, 'Type', 'surface');
if usesReferenceVoxelHeatmap || ~isempty(explicitAnatomySlice)
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
atlasWireframes = local_add_atlas_wireframes(hAx, spec);

if strcmpi(spec.FigureVisible, 'off')
    newFigures = setdiff(findall(groot, 'Type', 'figure'), figuresBefore);
    set([hFig; newFigures(:)], 'Visible', 'off');
    if spec.StrictHeadless
        local_assert_figures_hidden([hFig; newFigures(:)]);
    end
elseif strcmpi(spec.FigureVisible, 'on')
    set(hFig, 'Visible', 'on');
end

objects = struct('anatomySlices', anatomySlices, ...
    'atlasWireframes', atlasWireframes, ...
    'voxelHeatmap', voxelHeatmap, ...
    'voxelSweet', [], 'voxelSour', [], ...
    'fiberCandidate', [], 'fiberCoefficient', [], 'fiberScored', [], ...
    'fiberSweet', [], 'fiberSour', [], ...
    'fiberCategoricalMetadata', struct(), 'fiberLegend', [], ...
    'fiberCoefficientMetadata', struct(), ...
    'fiberLegendHandles', gobjects(0, 1), ...
    'fiberColorLimit', [], ...
    'fiberColorbarAxes', fiberColorbarAxes, ...
    'rasTriad', rasTriad, 'colorbar', colorbarHandle);
objects.voxelSweet = local_add_voxel_surface(hAx, spec.VoxelSweetNifti, ...
    spec.SweetColor, spec.VoxelAlpha, spec.VoxelThreshold, ...
    spec.SurfaceSmoothingIters, 'mh_viz_voxel_sweet', 'Sweet voxel');
objects.voxelSour = local_add_voxel_surface(hAx, spec.VoxelSourNifti, ...
    spec.SourColor, spec.VoxelAlpha, spec.VoxelThreshold, ...
    spec.SurfaceSmoothingIters, 'mh_viz_voxel_sour', 'Sour voxel');
[categoricalHandles, categoricalMetadata] = local_add_categorical_fibers( ...
    hAx, spec);
objects.fiberCandidate = categoricalHandles.candidate;
objects.fiberSweet = categoricalHandles.sweet;
objects.fiberSour = categoricalHandles.sour;
objects.fiberCategoricalMetadata = categoricalMetadata;
if strlength(string(spec.FiberCategoricalMat)) > 0
    [objects.fiberLegend, objects.fiberLegendHandles] = ...
        local_add_categorical_fiber_legend( ...
        hAx, categoricalMetadata, spec);
end
fiberColorLimit = local_resolve_fiber_color_limit(spec, ...
    strlength(string(spec.FiberCategoricalMat)) == 0);
objects.fiberColorLimit = fiberColorLimit;
[objects.fiberCoefficient, objects.fiberCoefficientMetadata] = ...
    local_add_coefficient_fibers(hAx, spec, fiberColorLimit);
objects.fiberScored = local_add_scored_fibers(hFig, hAx, spec.FiberScoreMat, ...
    spec.FiberAlpha, fiberColorLimit, 'mh_viz_fiber_scored', 'Scored fiber');
if isempty(objects.fiberSweet)
    objects.fiberSweet = local_add_scored_fibers( ...
        hFig, hAx, spec.FiberSweetMat, spec.FiberAlpha, fiberColorLimit, ...
        'mh_viz_fiber_sweet', 'Sweet fiber');
end
if isempty(objects.fiberSour)
    objects.fiberSour = local_add_scored_fibers( ...
        hFig, hAx, spec.FiberSourMat, spec.FiberAlpha, fiberColorLimit, ...
        'mh_viz_fiber_sour', 'Sour fiber');
end
if ~isempty(fiberColorLimit) && isempty(colorbarHandle)
    [colorbarHandle, fiberColorbarAxes] = local_add_fiber_colorbar( ...
        hAx, fiberColorLimit, spec.FiberColorbarLabel, ...
        spec.FiberColorbarTextColor);
    objects.colorbar = colorbarHandle;
    objects.fiberColorbarAxes = fiberColorbarAxes;
end
if strlength(string(spec.FiberCategoricalMat)) > 0
    local_apply_categorical_fiber_layer_order(hAx, objects);
elseif strlength(string(spec.FiberCoefficientMat)) > 0
    set(hAx, 'SortMethod', 'childorder');
    uistack(objects.fiberCoefficient, 'top');
end

if spec.AddToolbarToggles && exist('mh_fiber_add_toggle', 'file') == 2
    local_add_toggle(hFig, objects.atlasWireframes, ...
        char(string(spec.AtlasName)), [0.35, 0.35, 0.35], 'atlas');
    local_add_toggle(hFig, objects.voxelHeatmap, 'Voxel heatmap', ...
        [0.45, 0.45, 0.45], 'voxel');
    local_add_toggle(hFig, objects.voxelSweet, 'Sweet voxel', spec.SweetColor, 'voxel');
    local_add_toggle(hFig, objects.voxelSour, 'Sour voxel', spec.SourColor, 'voxel');
    local_add_toggle(hFig, objects.fiberCandidate, 'Candidate fibers', ...
        spec.CandidateFiberColor, 'fiber');
    local_add_toggle(hFig, objects.fiberCoefficient, ...
        'Coefficient-colored fibers', [0.45, 0.45, 0.45], 'fiber');
    local_add_toggle(hFig, objects.fiberScored, 'Scored fiber', ...
        [0.45, 0.45, 0.45], 'fiber');
    local_add_toggle(hFig, objects.fiberSweet, 'Sweet fiber', ...
        spec.SweetFiberColor, 'fiber');
    local_add_toggle(hFig, objects.fiberSour, 'Sour fiber', ...
        spec.SourFiberColor, 'fiber');
end

if ~isempty(spec.ViewStruct)
    if exist('ea_apply_view_struct', 'file') == 2
        ea_apply_view_struct(spec.ViewStruct, hAx);
    else
        local_apply_view_struct(spec.ViewStruct, hAx);
    end
elseif ~usesReferenceVoxelHeatmap
    view(hAx, 3);
    camproj(hAx, 'orthographic');
end
if spec.AddRASTriad && isempty(rasTriad) && exist('ea_add_ras_triad', 'file') == 2
    rasTriad = local_add_reference_ras_triad( ...
        hAx, spec.RASColors, spec.RASShowLabels);
    objects.rasTriad = rasTriad;
end

if exist('mh_viz_apply_soft_camera_lighting', 'file') == 2
    mh_viz_apply_soft_camera_lighting(hAx);
else
    local_apply_lighting(hAx);
end
setappdata(hFig, 'mh_viz_sweet_sour_scene_spec', spec);
setappdata(hFig, 'mh_viz_sweet_sour_objects', objects);
drawnow;
if strcmpi(spec.FigureVisible, 'off')
    newFigures = setdiff(findall(groot, 'Type', 'figure'), figuresBefore);
    set([hFig; newFigures(:)], 'Visible', 'off');
    if spec.StrictHeadless
        local_assert_figures_hidden([hFig; newFigures(:)]);
    end
end

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
defaults.VoxelSampleDepthMm = 1.0;
defaults.VoxelSweetNifti = '';
defaults.VoxelSourNifti = '';
defaults.FiberCategoricalMat = '';
defaults.FiberCoefficientMat = '';
defaults.FiberScoreMat = '';
defaults.FiberSweetMat = '';
defaults.FiberSourMat = '';
defaults.AtlasName = 'Custom_STNSNr';
defaults.ShowAtlasWireframe = [];
defaults.AtlasRoiIndices = [];
defaults.AtlasReduceFactor = 0.5;
defaults.AtlasEdgeAlpha = 0.15;
defaults.SweetColor = [0.77, 0.14, 0.24];
defaults.SourColor = [0.12, 0.35, 0.68];
defaults.VoxelAlpha = 0.72;
defaults.FiberAlpha = 0.32;
defaults.CandidateFiberColor = [204, 204, 204] / 255;
defaults.CandidateFiberAlpha = 1.0;
defaults.CandidateFiberLineWidth = 0.25;
defaults.CoefficientFiberAlpha = 1.0;
defaults.CoefficientFiberLineWidth = 0.25;
defaults.SweetFiberColor = [242, 0, 14] / 255;
defaults.SourFiberColor = [14, 106, 175] / 255;
defaults.SelectedFiberAlpha = 1.0;
defaults.SelectedFiberRenderMode = 'tube';
defaults.SelectedFiberLineWidth = 0.50;
defaults.SelectedFiberTubeWidth = 0.20;
defaults.SelectedFiberSampleFactor = 5;
defaults.SelectedFiberReduceFactor = 0.10;
defaults.ShowFiberLegend = true;
defaults.FiberLegendTextColor = [0, 0, 0];
defaults.FiberColorbarTextColor = [0, 0, 0];
defaults.FiberColorLimit = [];
defaults.FiberColorbarLabel = 'Fiber score';
defaults.VoxelThreshold = 0.5;
defaults.SurfaceSmoothingIters = 10;
defaults.ViewStruct = [];
defaults.ShowAnatomySlices = true;
defaults.AnatomySliceAlpha = 0.18;
defaults.AnatomyNifti = '';
defaults.AnatomySlicePlane = 'x';
defaults.AnatomySliceCoordinateMm = 0;
defaults.AnatomySliceTransparencyPercent = 100;
defaults.AddRASTriad = true;
defaults.RASShowLabels = true;
defaults.RASColors = [242, 0, 14; 14, 106, 175; 12, 162, 40] / 255;
defaults.AddToolbarToggles = true;
defaults.FontName = 'Arial';
defaults.BackgroundColor = [1, 1, 1];
defaults.FigureVisible = 'on';
defaults.FigureBackend = 'leaddbs';
defaults.StrictHeadless = false;
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

isDedicatedFiber = (isfield(spec, 'FiberCategoricalMat') && ...
    strlength(string(spec.FiberCategoricalMat)) > 0) || ...
    (isfield(spec, 'FiberCoefficientMat') && ...
    strlength(string(spec.FiberCoefficientMat)) > 0);
if isDedicatedFiber
    fiberDefaults = mh_viz_default_fiber_scene_spec();
    fiberNames = fieldnames(fiberDefaults);
    for i = 1:numel(fiberNames)
        defaults.(fiberNames{i}) = fiberDefaults.(fiberNames{i});
    end
end

names = fieldnames(defaults);
for i = 1:numel(names)
    name = names{i};
    if ~isfield(spec, name) || isempty(spec.(name))
        spec.(name) = defaults.(name);
    end
end
if isempty(spec.ShowAtlasWireframe)
    spec.ShowAtlasWireframe = ...
        strlength(string(spec.VoxelSignedNifti)) > 0;
end
local_validate_color(spec.SweetColor, 'SweetColor');
local_validate_color(spec.SourColor, 'SourColor');
local_validate_color(spec.CandidateFiberColor, 'CandidateFiberColor');
local_validate_color(spec.SweetFiberColor, 'SweetFiberColor');
local_validate_color(spec.SourFiberColor, 'SourFiberColor');
local_validate_color(spec.FiberLegendTextColor, 'FiberLegendTextColor');
local_validate_color(spec.FiberColorbarTextColor, 'FiberColorbarTextColor');
local_validate_color(spec.BackgroundColor, 'BackgroundColor');
if ~isnumeric(spec.RASColors) || ~isequal(size(spec.RASColors), [3, 3]) || ...
        any(~isfinite(spec.RASColors), 'all') || ...
        any(spec.RASColors < 0, 'all') || any(spec.RASColors > 1, 'all')
    error('mh_viz_make_sweet_sour_scene:BadRASColors', ...
        'RASColors must be a finite 3-by-3 RGB matrix within zero and one.');
end
if ~islogical(spec.RASShowLabels) || ~isscalar(spec.RASShowLabels)
    error('mh_viz_make_sweet_sour_scene:BadRASLabelVisibility', ...
        'RASShowLabels must be a scalar logical.');
end
local_validate_unit(spec.VoxelAlpha, 'VoxelAlpha');
local_validate_unit(spec.FiberAlpha, 'FiberAlpha');
local_validate_unit(spec.CandidateFiberAlpha, 'CandidateFiberAlpha');
local_validate_unit(spec.SelectedFiberAlpha, 'SelectedFiberAlpha');
local_validate_unit(spec.AnatomySliceAlpha, 'AnatomySliceAlpha');
local_validate_unit(spec.AtlasEdgeAlpha, 'AtlasEdgeAlpha');
if ~(ischar(spec.AnatomyNifti) || ...
        (isstring(spec.AnatomyNifti) && isscalar(spec.AnatomyNifti)))
    error('mh_viz_make_sweet_sour_scene:BadAnatomyNifti', ...
        'AnatomyNifti must be a text scalar.');
end
if ~(ischar(spec.AnatomySlicePlane) || ...
        (isstring(spec.AnatomySlicePlane) && isscalar(spec.AnatomySlicePlane))) || ...
        ~ismember(lower(strtrim(char(string(spec.AnatomySlicePlane)))), ...
        {'x', 'y', 'z'})
    error('mh_viz_make_sweet_sour_scene:BadAnatomySlicePlane', ...
        'AnatomySlicePlane must be x, y, or z.');
end
if ~isnumeric(spec.AnatomySliceCoordinateMm) || ...
        ~isscalar(spec.AnatomySliceCoordinateMm) || ...
        ~isfinite(spec.AnatomySliceCoordinateMm)
    error('mh_viz_make_sweet_sour_scene:BadAnatomySliceCoordinate', ...
        'AnatomySliceCoordinateMm must be a finite scalar.');
end
if ~isnumeric(spec.AnatomySliceTransparencyPercent) || ...
        ~isscalar(spec.AnatomySliceTransparencyPercent) || ...
        ~isfinite(spec.AnatomySliceTransparencyPercent) || ...
        spec.AnatomySliceTransparencyPercent < 0 || ...
        spec.AnatomySliceTransparencyPercent > 100
    error('mh_viz_make_sweet_sour_scene:BadAnatomySliceTransparency', ...
        'AnatomySliceTransparencyPercent must be from zero through 100.');
end
if ~islogical(spec.AddRASTriad) || ~isscalar(spec.AddRASTriad)
    error('mh_viz_make_sweet_sour_scene:BadRASTriadVisibility', ...
        'AddRASTriad must be a scalar logical.');
end
if ~islogical(spec.ShowAtlasWireframe) || ~isscalar(spec.ShowAtlasWireframe)
    error('mh_viz_make_sweet_sour_scene:BadAtlasVisibility', ...
        'ShowAtlasWireframe must be a scalar logical.');
end
if ~isnumeric(spec.AtlasReduceFactor) || ...
        ~isscalar(spec.AtlasReduceFactor) || ...
        ~isfinite(spec.AtlasReduceFactor) || ...
        spec.AtlasReduceFactor <= 0 || spec.AtlasReduceFactor > 1
    error('mh_viz_make_sweet_sour_scene:BadAtlasReduceFactor', ...
        'AtlasReduceFactor must be greater than zero and no greater than one.');
end
if ~isempty(spec.AtlasRoiIndices) && ...
        (~isnumeric(spec.AtlasRoiIndices) || ...
        ~isvector(spec.AtlasRoiIndices) || ...
        any(~isfinite(spec.AtlasRoiIndices), 'all') || ...
        any(spec.AtlasRoiIndices < 1, 'all') || ...
        any(mod(spec.AtlasRoiIndices, 1) ~= 0, 'all') || ...
        numel(unique(spec.AtlasRoiIndices)) ~= numel(spec.AtlasRoiIndices))
    error('mh_viz_make_sweet_sour_scene:BadAtlasRoiIndices', ...
        'AtlasRoiIndices must contain unique positive integers.');
end
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
dedicatedFiberSources = strlength(string( ...
    {spec.FiberCategoricalMat, spec.FiberCoefficientMat})) > 0;
legacyFiberSources = strlength(string( ...
    {spec.FiberScoreMat, spec.FiberSweetMat, spec.FiberSourMat})) > 0;
if nnz(dedicatedFiberSources) > 1 || ...
        (any(dedicatedFiberSources) && any(legacyFiberSources))
    error('mh_viz_make_sweet_sour_scene:MixedFiberModes', ...
        ['FiberCategoricalMat, FiberCoefficientMat, and legacy scored MAT ', ...
        'inputs are mutually exclusive.']);
end
if ~isnumeric(spec.CandidateFiberLineWidth) || ...
        ~isscalar(spec.CandidateFiberLineWidth) || ...
        ~isfinite(spec.CandidateFiberLineWidth) || ...
        spec.CandidateFiberLineWidth <= 0
    error('mh_viz_make_sweet_sour_scene:BadCandidateLineWidth', ...
        'CandidateFiberLineWidth must be a positive finite scalar.');
end
local_validate_unit(spec.CoefficientFiberAlpha, 'CoefficientFiberAlpha');
if ~isnumeric(spec.CoefficientFiberLineWidth) || ...
        ~isscalar(spec.CoefficientFiberLineWidth) || ...
        ~isfinite(spec.CoefficientFiberLineWidth) || ...
        spec.CoefficientFiberLineWidth <= 0
    error('mh_viz_make_sweet_sour_scene:BadCoefficientFiberLineWidth', ...
        'CoefficientFiberLineWidth must be a positive finite scalar.');
end
selectedRenderMode = lower(strtrim(char(string( ...
    spec.SelectedFiberRenderMode))));
if ~ismember(selectedRenderMode, {'line', 'tube'})
    error('mh_viz_make_sweet_sour_scene:BadSelectedRenderMode', ...
        'SelectedFiberRenderMode must be line or tube.');
end
spec.SelectedFiberRenderMode = selectedRenderMode;
if ~isnumeric(spec.SelectedFiberLineWidth) || ...
        ~isscalar(spec.SelectedFiberLineWidth) || ...
        ~isfinite(spec.SelectedFiberLineWidth) || ...
        spec.SelectedFiberLineWidth <= 0
    error('mh_viz_make_sweet_sour_scene:BadSelectedLineWidth', ...
        'SelectedFiberLineWidth must be a positive finite scalar.');
end
if ~isnumeric(spec.SelectedFiberTubeWidth) || ...
        ~isscalar(spec.SelectedFiberTubeWidth) || ...
        ~isfinite(spec.SelectedFiberTubeWidth) || ...
        spec.SelectedFiberTubeWidth <= 0
    error('mh_viz_make_sweet_sour_scene:BadSelectedTubeWidth', ...
        'SelectedFiberTubeWidth must be a positive finite scalar.');
end
if ~isnumeric(spec.SelectedFiberSampleFactor) || ...
        ~isscalar(spec.SelectedFiberSampleFactor) || ...
        ~isfinite(spec.SelectedFiberSampleFactor) || ...
        spec.SelectedFiberSampleFactor < 1 || ...
        mod(spec.SelectedFiberSampleFactor, 1) ~= 0
    error('mh_viz_make_sweet_sour_scene:BadSelectedSampleFactor', ...
        'SelectedFiberSampleFactor must be a positive integer.');
end
local_validate_unit(spec.SelectedFiberReduceFactor, ...
    'SelectedFiberReduceFactor');
if ~islogical(spec.ShowFiberLegend) || ~isscalar(spec.ShowFiberLegend)
    error('mh_viz_make_sweet_sour_scene:BadFiberLegendVisibility', ...
        'ShowFiberLegend must be a scalar logical.');
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
if ~any(strcmpi(char(string(spec.FigureBackend)), ...
        {'leaddbs', 'matlab', 'auto'}))
    error('mh_viz_make_sweet_sour_scene:BadFigureBackend', ...
        'FigureBackend must be leaddbs, matlab, or auto.');
end
if ~islogical(spec.StrictHeadless) || ~isscalar(spec.StrictHeadless)
    error('mh_viz_make_sweet_sour_scene:BadStrictHeadless', ...
        'StrictHeadless must be a scalar logical.');
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
plotConfig.AtlasName = '';
plotConfig.ViewStruct = spec.ViewStruct;
plotConfig.ColorbarLabel = char(string(spec.VoxelColorbarLabel));
plotConfig.RASTriadColors = spec.RASColors;
plotConfig.AddRASTriad = logical(spec.AddRASTriad);
plotConfig.RASShowLabels = logical(spec.RASShowLabels);
plotConfig.FigureVisible = char(string(spec.FigureVisible));
plotConfig.FigureBackend = char(string(spec.FigureBackend));
plotConfig.StrictHeadless = logical(spec.StrictHeadless);
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

function handles = local_add_atlas_wireframes(hAx, spec)
handles = gobjects(0, 1);
if ~spec.ShowAtlasWireframe
    return;
end
atlasName = char(string(spec.AtlasName));
if isempty(strtrim(atlasName))
    error('mh_viz_make_sweet_sour_scene:MissingAtlasName', ...
        'AtlasName is required when ShowAtlasWireframe is true.');
end
if exist('ea_space', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingSpaceResolver', ...
        'ea_space was not found. Add Lead-DBS to the MATLAB path.');
end
atlasIndex = fullfile(ea_space([], 'atlases'), atlasName, 'atlas_index.mat');
if ~isfile(atlasIndex)
    error('mh_viz_make_sweet_sour_scene:MissingAtlas', ...
        'Atlas index does not exist: %s', atlasIndex);
end
loaded = load(atlasIndex, 'atlases');
if ~isfield(loaded, 'atlases') || ~isstruct(loaded.atlases) || ...
        ~isfield(loaded.atlases, 'roi') || ...
        ~iscell(loaded.atlases.roi) || ...
        ~isfield(loaded.atlases, 'colormap')
    error('mh_viz_make_sweet_sour_scene:BadAtlas', ...
        'Atlas index lacks roi geometry or colormap: %s', atlasIndex);
end
atlases = loaded.atlases;
roiCount = size(atlases.roi, 1);
roiIndices = double(spec.AtlasRoiIndices(:))';
if isempty(roiIndices)
    roiIndices = 1:roiCount;
elseif any(roiIndices > roiCount)
    error('mh_viz_make_sweet_sour_scene:AtlasRoiIndexOutOfRange', ...
        'AtlasRoiIndices exceed the %d available atlas rows.', roiCount);
end
colors = double(atlases.colormap);
if size(colors, 1) < roiCount || size(colors, 2) < 3
    error('mh_viz_make_sweet_sour_scene:BadAtlasColors', ...
        'Atlas colormap does not align with its ROI rows: %s', atlasIndex);
end
handles = gobjects(numel(roiIndices), 1);
for outputIndex = 1:numel(roiIndices)
    i = roiIndices(outputIndex);
    entry = atlases.roi{i, 1};
    if ~isstruct(entry) || ~isfield(entry, 'fv') || ...
            ~isstruct(entry.fv) || ~isfield(entry.fv, 'faces') || ...
            ~isfield(entry.fv, 'vertices')
        error('mh_viz_make_sweet_sour_scene:BadAtlasROI', ...
            'Atlas ROI %d lacks triangulated geometry: %s', i, atlasIndex);
    end
    roi = entry.fv;
    if spec.AtlasReduceFactor < 1
        roi = reducepatch(roi, spec.AtlasReduceFactor);
    end
    label = sprintf('%s ROI %d', atlasName, i);
    if isfield(atlases, 'names') && numel(atlases.names) >= i
        candidate = char(string(atlases.names{i}));
        if ~isempty(strtrim(candidate))
            label = candidate;
        end
    end
    handles(outputIndex) = patch(hAx, ...
        'Faces', roi.faces, ...
        'Vertices', roi.vertices, ...
        'FaceColor', 'none', ...
        'EdgeColor', colors(i, 1:3), ...
        'EdgeAlpha', spec.AtlasEdgeAlpha, ...
        'Tag', 'mh_viz_atlas_wireframe', ...
        'DisplayName', label, ...
        'UserData', struct('mh_viz_type', 'atlas', ...
            'atlas_name', atlasName, 'roi_index', i, ...
            'source', atlasIndex));
end
end

function triad = local_add_reference_ras_triad(hAx, rasColors, showLabels)
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
    'ShowLabels', showLabels, ...
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

function [handles, metadata] = local_add_categorical_fibers(hAx, spec)
handles = struct('candidate', [], 'sweet', [], 'sour', []);
metadata = struct();
pathValue = char(string(spec.FiberCategoricalMat));
if isempty(pathValue)
    return;
end
if ~isfile(pathValue)
    error('mh_viz_make_sweet_sour_scene:MissingCategoricalFiberFile', ...
        'Categorical fiber MAT does not exist: %s', pathValue);
end
data = load(pathValue, ...
    'fibers', 'idx', 'scores', 'fiber_ids', 'fiber_roles');
required = {'fibers', 'idx', 'scores', 'fiber_ids', 'fiber_roles'};
for index = 1:numel(required)
    if ~isfield(data, required{index})
        error('mh_viz_make_sweet_sour_scene:BadCategoricalFiberFile', ...
            'Categorical fiber MAT lacks %s: %s', required{index}, pathValue);
    end
end
if numel(data.scores) ~= numel(data.idx) || ...
        any(~isfinite(double(data.scores(:))))
    error('mh_viz_make_sweet_sour_scene:BadCategoricalFiberScores', ...
        'Categorical fiber scores must be finite and aligned with idx.');
end
[handles, metadata] = mh_viz_show_categorical_fibers( ...
    hAx, data.fibers(:, 1:3), data.idx, data.fiber_roles, data.fiber_ids, ...
    'CandidateColor', spec.CandidateFiberColor, ...
    'CandidateAlpha', spec.CandidateFiberAlpha, ...
    'CandidateLineWidth', spec.CandidateFiberLineWidth, ...
    'SweetColor', spec.SweetFiberColor, ...
    'SourColor', spec.SourFiberColor, ...
    'SelectedAlpha', spec.SelectedFiberAlpha, ...
    'SelectedRenderMode', spec.SelectedFiberRenderMode, ...
    'SelectedLineWidth', spec.SelectedFiberLineWidth, ...
    'SelectedTubeWidth', spec.SelectedFiberTubeWidth, ...
    'SelectedSampleFactor', spec.SelectedFiberSampleFactor, ...
    'SelectedReduceFactor', spec.SelectedFiberReduceFactor);
metadata.source = pathValue;
metadata.score_min = min(double(data.scores(:)));
metadata.score_max = max(double(data.scores(:)));
for name = {'candidate', 'sweet', 'sour'}
    handle = handles.(name{1});
    valid = handle(isgraphics(handle));
    for index = 1:numel(valid)
        set(valid(index), 'UserData', struct( ...
            'mh_viz_type', ['fiber_', name{1}], ...
            'source', pathValue, ...
            'candidate_fiber_count', metadata.candidate_fiber_count, ...
            'rendered_fiber_count', metadata.rendered_fiber_count));
    end
end
end

function [handle, metadata] = ...
        local_add_coefficient_fibers(hAx, spec, colorLimit)
handle = gobjects(0, 1);
metadata = struct();
pathValue = char(string(spec.FiberCoefficientMat));
if isempty(pathValue)
    return;
end
if ~isfile(pathValue)
    error('mh_viz_make_sweet_sour_scene:MissingCoefficientFiberFile', ...
        'Coefficient fiber MAT does not exist: %s', pathValue);
end
data = load(pathValue, 'fibers', 'idx', 'scores', 'fiber_ids');
required = {'fibers', 'idx', 'scores', 'fiber_ids'};
for index = 1:numel(required)
    if ~isfield(data, required{index})
        error('mh_viz_make_sweet_sour_scene:BadCoefficientFiberFile', ...
            'Coefficient fiber MAT lacks %s: %s', required{index}, pathValue);
    end
end
if isempty(colorLimit)
    error('mh_viz_make_sweet_sour_scene:MissingCoefficientColorLimit', ...
        'Coefficient fiber rendering requires a symmetric color limit.');
end
[handle, metadata] = mh_viz_show_coefficient_fibers( ...
    hAx, data.fibers(:, 1:3), data.idx, data.scores, data.fiber_ids, ...
    colorLimit, ...
    'Alpha', spec.CoefficientFiberAlpha, ...
    'LineWidth', spec.CoefficientFiberLineWidth);
metadata.source = pathValue;
set(handle, 'UserData', struct( ...
    'mh_viz_type', 'fiber_coefficient', ...
    'source', pathValue, ...
    'candidate_fiber_count', metadata.candidate_fiber_count, ...
    'rendered_fiber_count', metadata.rendered_fiber_count, ...
    'score_color_limit', colorLimit, ...
    'colormap', 'vik'));
end

function local_apply_categorical_fiber_layer_order(hAx, objects)
% Place selected categorical fibers in front of the candidate layer.

set(hAx, 'SortMethod', 'childorder');
orderedLayers = { ...
    objects.fiberCandidate, ...
    objects.fiberSweet, ...
    objects.fiberSour};
for layerIndex = 1:numel(orderedLayers)
    handles = orderedLayers{layerIndex};
    handles = handles(isgraphics(handles));
    if ~isempty(handles)
        uistack(handles, 'top');
    end
end
end

function [hLegend, legendHandles] = ...
        local_add_categorical_fiber_legend(hAx, metadata, spec)
hLegend = [];
legendHandles = gobjects(0, 1);
if ~spec.ShowFiberLegend
    return;
end
entries = { ...
    'candidate', 'Candidate fibers', metadata.candidate_fiber_count, ...
        spec.CandidateFiberColor; ...
    'sweet', 'Sweet fibers', metadata.sweet_fiber_count, ...
        spec.SweetFiberColor; ...
    'sour', 'Sour fibers', metadata.sour_fiber_count, ...
        spec.SourFiberColor};
legendHandles = gobjects(size(entries, 1), 1);
legendLabels = cell(size(entries, 1), 1);
for index = 1:size(entries, 1)
    legendHandles(index) = line(hAx, nan, nan, ...
        'Color', entries{index, 4}, ...
        'LineStyle', '-', ...
        'LineWidth', 4, ...
        'Marker', 'none', ...
        'Tag', ['mh_viz_fiber_legend_', entries{index, 1}], ...
        'HandleVisibility', 'on');
    legendLabels{index} = sprintf( ...
        '%s: %d', entries{index, 2}, entries{index, 3});
end
hLegend = legend(hAx, legendHandles, legendLabels, ...
    'Location', 'eastoutside', ...
    'Box', 'off', ...
    'Color', 'none', ...
    'FontName', spec.FontName, ...
    'FontSize', 18, ...
    'TextColor', spec.FiberLegendTextColor, ...
    'Interpreter', 'none', ...
    'Tag', 'mh_viz_fiber_legend');
hLegend.AutoUpdate = 'off';
hLegend.Units = 'normalized';
hLegend.Position = [0.72, 0.43, 0.25, 0.14];
setappdata(hLegend, 'mh_viz_fiber_legend_colors', ...
    vertcat(entries{:, 4}));
setappdata(hLegend, 'mh_viz_fiber_legend_labels', legendLabels);
hAx.Position = [0.10, 0.12, 0.60, 0.76];
end

function colorLimit = local_resolve_fiber_color_limit(spec, enabled)
if ~enabled
    colorLimit = [];
    return;
end
paths = {spec.FiberCoefficientMat, spec.FiberScoreMat, ...
    spec.FiberSweetMat, spec.FiberSourMat};
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

function [hCb, hColorbarAx] = ...
        local_add_fiber_colorbar(hAx, colorLimit, label, textColor)
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
hCb.Color = textColor;
hCb.FontName = plotConfig.FontName;
hCb.FontSize = plotConfig.ColorbarTickFontSize;
hCb.TickLabelInterpreter = plotConfig.ColorbarTickLabelInterpreter;
hCb.Label.String = char(string(label));
hCb.Label.Color = textColor;
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

function handle = local_add_explicit_anatomy_slice(hFig, hAx, spec)
handle = gobjects(0, 1);
pathValue = char(string(spec.AnatomyNifti));
if isempty(pathValue) || ~spec.ShowAnatomySlices
    return;
end
if ~isfile(pathValue)
    error('mh_viz_make_sweet_sour_scene:MissingAnatomyNifti', ...
        'AnatomyNifti does not exist: %s', pathValue);
end
if exist('nifti', 'file') ~= 2 || exist('slice3i', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingAnatomyRenderer', ...
        'SPM nifti and Lead-DBS slice3i are required for anatomy slices.');
end

volume = nifti(pathValue);
plane = lower(strtrim(char(string(spec.AnatomySlicePlane))));
dimension = find(strcmp(plane, {'x', 'y', 'z'}), 1);
worldCoordinate = [0, 0, 0, 1]';
worldCoordinate(dimension) = double(spec.AnatomySliceCoordinateMm);
voxelCoordinate = volume.mat \ worldCoordinate;
sliceIndex = round(voxelCoordinate(dimension));
dimensionSize = size(volume.dat, dimension);
if sliceIndex < 1 || sliceIndex > dimensionSize
    error('mh_viz_make_sweet_sour_scene:AnatomySliceOutsideVolume', ...
        'The %s=%g mm anatomy slice lies outside %s.', ...
        plane, spec.AnatomySliceCoordinateMm, pathValue);
end

set(groot, 'CurrentFigure', hFig);
set(hFig, 'CurrentAxes', hAx);
handle = slice3i( ...
    hFig, volume.dat, volume.mat, dimension, sliceIndex, []);
set(handle, ...
    'FaceAlpha', double(spec.AnatomySliceTransparencyPercent) / 100, ...
    'Visible', 'on', ...
    'Tag', ['mh_viz_anatomy_', plane, '_slice'], ...
    'DisplayName', sprintf('Anatomy %s=%g mm', ...
    plane, spec.AnatomySliceCoordinateMm));
setappdata(handle, 'mh_viz_anatomy_source', pathValue);
setappdata(handle, 'mh_viz_anatomy_plane', plane);
setappdata(handle, 'mh_viz_anatomy_coordinate_mm', ...
    double(spec.AnatomySliceCoordinateMm));
setappdata(handle, 'mh_viz_anatomy_transparency_percent', ...
    double(spec.AnatomySliceTransparencyPercent));
setappdata(hFig, [plane, 'sliceplot'], handle);
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

function local_assert_figures_hidden(figures)
figures = figures(isgraphics(figures, 'figure'));
for index = 1:numel(figures)
    if strcmpi(get(figures(index), 'Visible'), 'on')
        error('mh_viz_make_sweet_sour_scene:StrictHeadlessVisibleFigure', ...
            'Strict headless mode created a visible MATLAB figure.');
    end
end
end

function local_ensure_parent(pathValue)
parent = fileparts(char(string(pathValue)));
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
end
