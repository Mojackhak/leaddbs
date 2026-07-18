function scene = mh_viz_make_sweet_sour_scene(spec)
% Render sweet/sour voxel surfaces and fibers in one ea_mnifigure scene.
%
% Required input is a scalar struct. All spatial sources are optional, but at
% least one of VoxelSweetNifti, VoxelSourNifti, FiberSweetMat, or FiberSourMat
% must be present. Fiber MAT files must contain Lead-DBS `fibers` and `idx`
% variables after canonical model fiber IDs have been resolved to geometry.

if nargin < 1 || ~isstruct(spec) || ~isscalar(spec)
    error('mh_viz_make_sweet_sour_scene:BadSpec', ...
        'spec must be a scalar struct.');
end
if exist('ea_mnifigure', 'file') ~= 2
    error('mh_viz_make_sweet_sour_scene:MissingLeadDBS', ...
        'ea_mnifigure was not found. Add Lead-DBS to the MATLAB path.');
end

spec = local_apply_defaults(spec);
sourceFields = {'VoxelSweetNifti', 'VoxelSourNifti', ...
    'FiberSweetMat', 'FiberSourMat'};
hasSource = false;
for i = 1:numel(sourceFields)
    hasSource = hasSource || strlength(string(spec.(sourceFields{i}))) > 0;
end
if ~hasSource
    error('mh_viz_make_sweet_sour_scene:MissingSource', ...
        'At least one sweet or sour voxel/fiber source is required.');
end

figuresBefore = findall(groot, 'Type', 'figure');
visibilityCleanup = []; %#ok<NASGU>
if strcmpi(spec.FigureVisible, 'off')
    oldVisible = get(groot, 'DefaultFigureVisible');
    set(groot, 'DefaultFigureVisible', 'off');
    visibilityCleanup = onCleanup(@() set(groot, 'DefaultFigureVisible', oldVisible));
end

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
anatomySlices = findall(hAx, 'Type', 'surface');
if spec.ShowAnatomySlices
    for i = 1:numel(anatomySlices)
        try
            set(anatomySlices(i), 'FaceAlpha', spec.AnatomySliceAlpha);
        catch
        end
    end
else
    set(anatomySlices, 'Visible', 'off');
end

if strcmpi(spec.FigureVisible, 'off')
    newFigures = setdiff(findall(groot, 'Type', 'figure'), figuresBefore);
    set([hFig; newFigures(:)], 'Visible', 'off');
    clear visibilityCleanup;
elseif strcmpi(spec.FigureVisible, 'on')
    set(hFig, 'Visible', 'on');
end

objects = struct('anatomySlices', anatomySlices, ...
    'voxelSweet', [], 'voxelSour', [], ...
    'fiberSweet', [], 'fiberSour', []);
objects.voxelSweet = local_add_voxel_surface(hAx, spec.VoxelSweetNifti, ...
    spec.SweetColor, spec.VoxelAlpha, spec.VoxelThreshold, ...
    spec.SurfaceSmoothingIters, 'mh_viz_voxel_sweet', 'Sweet voxel');
objects.voxelSour = local_add_voxel_surface(hAx, spec.VoxelSourNifti, ...
    spec.SourColor, spec.VoxelAlpha, spec.VoxelThreshold, ...
    spec.SurfaceSmoothingIters, 'mh_viz_voxel_sour', 'Sour voxel');
objects.fiberSweet = local_add_fibers(hFig, hAx, spec.FiberSweetMat, ...
    spec.SweetColor, spec.FiberAlpha, 'mh_viz_fiber_sweet', 'Sweet fiber');
objects.fiberSour = local_add_fibers(hFig, hAx, spec.FiberSourMat, ...
    spec.SourColor, spec.FiberAlpha, 'mh_viz_fiber_sour', 'Sour fiber');

if spec.AddToolbarToggles && exist('mh_fiber_add_toggle', 'file') == 2
    local_add_toggle(hFig, objects.voxelSweet, 'Sweet voxel', spec.SweetColor, 'voxel');
    local_add_toggle(hFig, objects.voxelSour, 'Sour voxel', spec.SourColor, 'voxel');
    local_add_toggle(hFig, objects.fiberSweet, 'Sweet fiber', spec.SweetColor, 'fiber');
    local_add_toggle(hFig, objects.fiberSour, 'Sour fiber', spec.SourColor, 'fiber');
end

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
if spec.AddRASTriad && exist('ea_add_ras_triad', 'file') == 2
    ea_add_ras_triad(hAx, 'FontName', spec.FontName, ...
        'FontSize', spec.RASTriadFontSize, 'LineWidth', spec.RASTriadLineWidth);
end

local_apply_lighting(hAx);
setappdata(hFig, 'mh_viz_sweet_sour_scene_spec', spec);
setappdata(hFig, 'mh_viz_sweet_sour_objects', objects);
drawnow;

scene = struct();
scene.figure = hFig;
scene.axes = hAx;
scene.objects = objects;
scene.fig = '';
scene.image = '';
scene.spin = '';

if strlength(string(spec.OutputFig)) > 0
    local_ensure_parent(spec.OutputFig);
    savefig(hFig, char(string(spec.OutputFig)));
    scene.fig = char(string(spec.OutputFig));
end
if strlength(string(spec.OutputImage)) > 0
    local_ensure_parent(spec.OutputImage);
    if exist('ea_export_figure_transparent', 'file') == 2
        ea_export_figure_transparent(hFig, char(string(spec.OutputImage)), ...
            'BackgroundColor', spec.BackgroundColor, ...
            'Resolution', spec.ExportResolution, ...
            'Renderer', spec.ExportRenderer);
    else
        exportgraphics(hFig, char(string(spec.OutputImage)), ...
            'Resolution', spec.ExportResolution, ...
            'BackgroundColor', spec.BackgroundColor);
    end
    scene.image = char(string(spec.OutputImage));
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
defaults.VoxelSweetNifti = '';
defaults.VoxelSourNifti = '';
defaults.FiberSweetMat = '';
defaults.FiberSourMat = '';
defaults.AtlasName = '';
defaults.SweetColor = [0.77, 0.14, 0.24];
defaults.SourColor = [0.12, 0.35, 0.68];
defaults.VoxelAlpha = 0.72;
defaults.FiberAlpha = 0.32;
defaults.VoxelThreshold = 0.5;
defaults.SurfaceSmoothingIters = 10;
defaults.ViewStruct = [];
defaults.ShowAnatomySlices = true;
defaults.AnatomySliceAlpha = 0.18;
defaults.AddRASTriad = true;
defaults.RASTriadFontSize = 12;
defaults.RASTriadLineWidth = 2;
defaults.AddToolbarToggles = true;
defaults.FontName = 'Arial';
defaults.BackgroundColor = [1, 1, 1];
defaults.FigureVisible = 'on';
defaults.OutputFig = '';
defaults.OutputImage = '';
defaults.OutputSpin = '';
defaults.ExportResolution = 300;
defaults.ExportRenderer = 'opengl';
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
local_validate_unit(spec.VoxelAlpha, 'VoxelAlpha');
local_validate_unit(spec.FiberAlpha, 'FiberAlpha');
local_validate_unit(spec.AnatomySliceAlpha, 'AnatomySliceAlpha');
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

function handle = local_add_fibers(hFig, hAx, pathValue, color, alphaValue, tag, label)
handle = [];
pathValue = char(string(pathValue));
if isempty(pathValue)
    return;
end
if ~isfile(pathValue)
    error('mh_viz_make_sweet_sour_scene:MissingFiberFile', ...
        'Fiber MAT does not exist: %s', pathValue);
end
data = load(pathValue, 'fibers', 'idx');
if ~isfield(data, 'fibers') || ~isfield(data, 'idx') || isempty(data.idx)
    error('mh_viz_make_sweet_sour_scene:BadFiberFile', ...
        'Fiber MAT must contain nonempty fibers and idx variables: %s', pathValue);
end
set(0, 'CurrentFigure', hFig);
axes(hAx);
handle = ea_showfiber(data.fibers(:, 1:3), data.idx, color, alphaValue);
valid = handle(isgraphics(handle));
for i = 1:numel(valid)
    set(valid(i), 'Tag', tag, 'DisplayName', label, ...
        'UserData', struct('mh_viz_type', 'fiber', 'label', label, ...
        'source', pathValue, 'fiber_count', numel(data.idx)));
end
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
