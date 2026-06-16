function figures = mh_fiber_make_scene(cfg, dirs, rois, vta)
% Generate a Lead-DBS/MATLAB scene figure with electrodes, ROI, VTA, and fibers.

figures = struct();
figures.mni = make_one_scene(cfg, dirs, rois.mni, vta.mni, 'mni');
figures.native = make_one_scene(cfg, dirs, rois.native, vta.native, 'native');
figures.fig = figures.mni.fig;
figures.png = figures.mni.png;

end

function scene = make_one_scene(cfg, dirs, rois, vta, sceneSpace)
scene = struct();
scene.fig = fullfile(dirs.figures, [cfg.patientName, '_', cfg.stimLabel, '_', sceneSpace, '_scene.fig']);
scene.png = fullfile(dirs.figures, [cfg.patientName, '_', cfg.stimLabel, '_', sceneSpace, '_scene.png']);
openAfterRun = get_figure_option(cfg, 'openAfterRun', true);

options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options = ea_defaultoptions(options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);
options.leadprod = 'dbs';
options.native = strcmp(sceneSpace, 'native');
options.orignative = options.native;
options.d3.verbose = 'off';
options.d3.elrendering = 1;
options.d3.exportBB = 0;
options.d3.writeatlases = double(get_figure_option(cfg, 'showVisualizationAtlas', true));
options.d3.showactivecontacts = 1;
options.d3.showpassivecontacts = 1;
options.d3.showisovolume = 0;
options.d3.mirrorsides = 0;
if get_figure_option(cfg, 'showVisualizationAtlas', true)
    options.atlasset = char(string(get_figure_option(cfg, 'visualizationAtlas', 'NAc_ALIC (Yu 2021 and Ewert 2017)')));
else
    options.atlasset = 'Use none';
end
options.writeoutstats = 0;

try
    resultfig = ea_elvis(options);
catch ME
    warning('mh_fiber_make_scene:ElvisFailed', ...
        'ea_elvis failed, falling back to a basic MATLAB figure: %s', ME.message);
    resultfig = figure('Color', 'k', 'Visible', visible_state(openAfterRun), 'Name', 'Fiber/VTA scene');
    axes('Parent', resultfig);
    hold on;
    axis equal off;
    view(3);
end

setappdata(resultfig, 'options', options);
setappdata(resultfig, 'mh_fiber_show_region_labels', logical(get_figure_option(cfg, 'showRegionLabels', false)));
initialize_anatomy_togglestates(resultfig, options, cfg);
recolor_electrode_insulation(resultfig, cfg);
set(0, 'CurrentFigure', resultfig);
hold on;

if get_figure_option(cfg, 'plotExtractedRois', false)
    plot_rois(resultfig, rois, cfg);
end
plot_vtas(resultfig, vta, cfg);
plot_fibers(resultfig, dirs, cfg, sceneSpace);

camlight('headlight');
lighting gouraud;
axis equal off;
view(90, 0);
drawnow;
mh_fiber_hide_region_labels(resultfig);

ensure_exportable_figure_size(resultfig);
set(resultfig, 'Visible', visible_state(openAfterRun));
drawnow;
mh_fiber_rebind_scene_controls(resultfig);
open_anatomy_control_if_requested(resultfig, options, cfg);
mh_fiber_hide_region_labels(resultfig);
transientControls = detach_transient_control_windows(resultfig);
savefig(resultfig, scene.fig);
restore_transient_control_windows(resultfig, transientControls);
mh_fiber_hide_region_labels(resultfig);
export_scene_png(resultfig, scene.png, openAfterRun);
if get_figure_option(cfg, 'closeAfterSave', false)
    close(resultfig);
end

end

function export_scene_png(resultfig, pngPath, keepVisible)
if ~isgraphics(resultfig)
    return;
end

previousVisible = get(resultfig, 'Visible');
set(resultfig, 'Visible', 'on');
drawnow;

try
    exportgraphics(resultfig, pngPath, 'Resolution', 300);
catch
    set(resultfig, 'PaperPositionMode', 'auto', 'InvertHardcopy', 'off');
    print(resultfig, pngPath, '-dpng', '-r300');
end

if ~keepVisible && isgraphics(resultfig)
    set(resultfig, 'Visible', previousVisible);
end
end

function ensure_exportable_figure_size(resultfig)
if ~isgraphics(resultfig)
    return;
end

previousUnits = get(resultfig, 'Units');
cleanup = onCleanup(@() set(resultfig, 'Units', previousUnits));
set(resultfig, 'Units', 'pixels');
pos = get(resultfig, 'Position');
if numel(pos) ~= 4
    return;
end

minSize = [1200, 900];
if pos(3) < minSize(1) || pos(4) < minSize(2)
    pos(3:4) = max(pos(3:4), minSize);
    set(resultfig, 'Position', pos);
end
end

function recolor_electrode_insulation(resultfig, cfg)
if ~isfield(cfg.figure, 'colors') || ~isfield(cfg.figure.colors, 'ElectrodeInsulation')
    color = [0.92, 0.92, 0.88];
else
    color = cfg.figure.colors.ElectrodeInsulation;
end

elRender = getappdata(resultfig, 'el_render');
if isempty(elRender)
    return;
end

for i = 1:numel(elRender)
    if ~isprop(elRender(i), 'elpatch') || isempty(elRender(i).elpatch)
        continue;
    end

    patches = mh_fiber_valid_graphics(elRender(i).elpatch);
    for j = 1:numel(patches)
        if ~is_electrode_insulation_patch(patches(j))
            continue;
        end

        alphaValue = get_patch_alpha(patches(j));
        ea_specsurf(patches(j), color, alphaValue, 'insulation');
    end
end
end

function isInsulation = is_electrode_insulation_patch(handle)
isInsulation = false;
if isempty(handle) || ~isgraphics(handle, 'patch')
    return;
end

try
    tag = char(string(get(handle, 'Tag')));
catch
    tag = '';
end
isInsulation = contains(tag, 'Insulation');
end

function alphaValue = get_patch_alpha(handle)
alphaValue = 1;
try
    currentAlpha = get(handle, 'FaceAlpha');
    if isnumeric(currentAlpha) && isscalar(currentAlpha)
        alphaValue = currentAlpha;
    end
catch
end
end

function plot_rois(resultfig, rois, cfg)
set(0, 'CurrentFigure', resultfig);
hold on;
add_roi_object(resultfig, rois.R.NAc, 'NAc R', cfg.figure.colors.NAc, cfg.figure.roiAlpha);
add_roi_object(resultfig, rois.L.NAc, 'NAc L', cfg.figure.colors.NAc, cfg.figure.roiAlpha);
add_roi_object(resultfig, rois.R.ALIC, 'ALIC R', cfg.figure.colors.ALIC, cfg.figure.roiAlpha);
add_roi_object(resultfig, rois.L.ALIC, 'ALIC L', cfg.figure.colors.ALIC, cfg.figure.roiAlpha);
end

function add_roi_object(resultfig, roiPath, label, color, alphaValue)
roiPatch = add_roi_patch(roiPath, label, color, alphaValue);
mh_fiber_add_toggle(resultfig, roiPatch, label, color, 'on', 'roi');
end

function roiPatch = add_roi_patch(roiPath, label, color, alphaValue)
roiPatch = [];
if ~isfile(roiPath)
    warning('mh_fiber_make_scene:MissingRoi', 'ROI file not found: %s', roiPath);
    return;
end

nii = ea_load_nii(roiPath);
img = double(nii.img);
img(~isfinite(img)) = 0;
img = img ~= 0;
if ~any(img(:))
    return;
end

label = char(string(label));
targetTag = matlab.lang.makeValidName(label);
fv = roi_mask_to_surface(img, nii.mat);
if isempty(fv) || isempty(fv.faces) || isempty(fv.vertices)
    return;
end

roiPatch = patch( ...
    'Faces', fv.faces, ...
    'Vertices', fv.vertices, ...
    'FaceColor', color, ...
    'EdgeColor', 'none', ...
    'FaceAlpha', alphaValue, ...
    'EdgeLighting', 'gouraud', ...
    'FaceLighting', 'gouraud', ...
    'Visible', 'on', ...
    'Tag', targetTag, ...
    'UserData', struct('mh_fiber_type', 'roi', 'label', label, 'source', roiPath), ...
    'SpecularColorReflectance', 1, ...
    'SpecularExponent', 3, ...
    'SpecularStrength', 0.3, ...
    'DiffuseStrength', 0.4, ...
    'AmbientStrength', 0.3);
end

function fv = roi_mask_to_surface(img, mat)
imgSize = size(img);
[xVox, yVox, zVox] = meshgrid(1:imgSize(1), 1:imgSize(2), 1:imgSize(3));
xyzMm = ea_vox2mm([xVox(:), yVox(:), zVox(:)], mat);
x = reshape(xyzMm(:, 1), size(xVox));
y = reshape(xyzMm(:, 2), size(yVox));
z = reshape(xyzMm(:, 3), size(zVox));
mask = permute(double(img), [2, 1, 3]);

fv = isosurface(x, y, z, mask, 0.5);
caps = isocaps(x, y, z, mask, 0.5);
if ~isempty(caps.faces)
    caps.faces = caps.faces + size(fv.vertices, 1);
    fv.faces = [fv.faces; caps.faces];
    fv.vertices = [fv.vertices; caps.vertices];
end

if isempty(fv.faces) || isempty(fv.vertices)
    return;
end

prefs = ea_prefs;
if isfield(prefs, 'hullsmooth') && prefs.hullsmooth
    fv = ea_smoothpatch(fv, 1, prefs.hullsmooth);
end
if isfield(prefs, 'hullsimplify') && prefs.hullsimplify
    if prefs.hullsimplify < 1
        fv = reducepatch(fv, prefs.hullsimplify);
    elseif prefs.hullsimplify > 1 && prefs.hullsimplify < numel(fv.faces)
        fv = reducepatch(fv, prefs.hullsimplify / numel(fv.faces));
    end
end
end

function plot_vtas(resultfig, vta, cfg)
rightVta = add_vta_patch(vta.R.binaryMat, cfg.figure.colors.VTA, cfg.figure.vtaAlpha);
leftVta = add_vta_patch(vta.L.binaryMat, cfg.figure.colors.VTA, cfg.figure.vtaAlpha);
mh_fiber_add_toggle(resultfig, rightVta, 'VTA R', cfg.figure.colors.VTA, 'on', 'vta');
mh_fiber_add_toggle(resultfig, leftVta, 'VTA L', cfg.figure.colors.VTA, 'on', 'vta');
end

function vtaPatch = add_vta_patch(vtaMat, color, alphaValue)
data = load(vtaMat, 'vatfv');
vtaPatch = patch('Faces', data.vatfv.faces, 'Vertices', data.vatfv.vertices, ...
    'FaceColor', color, 'EdgeColor', 'none', 'FaceAlpha', alphaValue, ...
    'FaceLighting', 'gouraud', 'Tag', 'mh_fiber_vta');
end

function plot_fibers(resultfig, dirs, cfg, sceneSpace)
if strcmp(sceneSpace, 'native')
    fiberDir = dirs.fibersNative;
else
    fiberDir = dirs.fibersMni;
end

stages = fiber_stage_specs(cfg);
for sideCell = {'R', 'L'}
    side = sideCell{1};
    for i = 1:numel(stages)
        stage = stages(i);
        fiberPath = fullfile(fiberDir, sprintf('%s_hemi-%s_%s.mat', cfg.patientName, side, stage.name));
        label = sprintf('%s %s', side, stage.label);
        show_fiber_file(resultfig, fiberPath, label, stage_color(stage, side), stage.alpha);
    end
end
end

function stages = fiber_stage_specs(cfg)
stages = struct( ...
    'name', {'NAc_only', 'ALIC_only', 'NAc_ALIC_intersection', 'VTA_hit', 'NAc_ALIC_VTA_hit'}, ...
    'label', {'NAc_only', 'ALIC_only', 'NAc_ALIC_intersection', 'VTA_hit', 'NAc_ALIC_VTA_hit'}, ...
    'alpha', {0.16, 0.16, 0.22, 0.18, 0.42});

stages(1).baseColor = cfg.figure.colors.NAc;
stages(2).baseColor = cfg.figure.colors.ALIC;
stages(3).baseColor = [1.00, 0.84, 0.10];
stages(4).baseColor = [1.00, 0.45, 0.05];
stages(5).baseColor = [1.00, 0.10, 0.08];
end

function color = stage_color(stage, side)
color = stage.baseColor;
if strcmp(side, 'L')
    color = 0.75 .* color + 0.25 .* [0.05, 0.35, 1.00];
end
end

function show_fiber_file(resultfig, path, label, color, alphaValue)
if ~isfile(path)
    add_empty_fiber_toggle(resultfig, sprintf('%s (0 fibers)', label), color);
    return;
end
data = load(path, 'fibers', 'idx');
if ~isfield(data, 'idx') || isempty(data.idx)
    add_empty_fiber_toggle(resultfig, sprintf('%s (0 fibers)', label), color);
    return;
end
fiberHandle = ea_showfiber(data.fibers(:, 1:3), data.idx, color, alphaValue);
mh_fiber_add_toggle(resultfig, fiberHandle, sprintf('%s (%d fibers)', label, numel(data.idx)), color, 'on', 'fiber');
end

function toggleH = add_empty_fiber_toggle(resultfig, label, color)
toolbar = ensure_scene_toolbar(resultfig);
toggleH = uitoggletool(toolbar, ...
    'CData', ea_get_icn('atlas', 0.35 .* color + 0.65 .* [0.75, 0.75, 0.75]), ...
    'TooltipString', label, ...
    'OnCallback', @noop_toggle, ...
    'OffCallback', @noop_toggle, ...
    'State', 'on', ...
    'Tag', matlab.lang.makeValidName(label), ...
    'UserData', 'empty_fiber');
setappdata(toggleH, 'mh_fiber_control_label', label);
end

function noop_toggle(src, ~)
if isgraphics(src)
    set(src, 'State', 'on');
end
end

function toolbar = ensure_scene_toolbar(resultfig)
toolbar = getappdata(resultfig, 'addht');
if isempty(toolbar) || ~ishandle(toolbar)
    toolbar = uitoolbar(resultfig);
    setappdata(resultfig, 'addht', toolbar);
end
end

function initialize_anatomy_togglestates(resultfig, options, cfg)
existingStates = getappdata(resultfig, 'togglestates');
if isstruct(existingStates) && all(isfield(existingStates, {'xyzmm', 'template', 'xyztoggles'}))
    return;
end

spacedef = ea_getspacedef;
if isfield(spacedef, 'guidef') && isfield(spacedef.guidef, 'xyzdef')
    xyzmm = spacedef.guidef.xyzdef;
else
    xyzmm = [0, 0, 0];
end
if numel(xyzmm) ~= 3
    xyzmm = [0, 0, 0];
end

backdrop = char(string(get_figure_option(cfg, 'defaultBackdrop', '')));
availableBackdrops = ea_assignbackdrop('list', options, 'Patient', options.native);
if isempty(availableBackdrops)
    error('mh_fiber_make_scene:MissingBackdrops', 'No Lead-DBS anatomy backdrops are available.');
end
if isempty(backdrop) || ~any(strcmp(availableBackdrops, backdrop))
    backdrop = availableBackdrops{1};
end

transparency = get_figure_option(cfg, 'defaultSliceTransparency', [100, 100, 100]);
if numel(transparency) ~= 3
    transparency = [100, 100, 100];
end

togglestates = struct();
togglestates.cutview = '3d';
togglestates.refreshcuts = 1;
togglestates.refreshview = 1;
togglestates.xyzmm = double(reshape(xyzmm, 1, 3));
togglestates.xyztoggles = [1, 1, 1];
togglestates.xyztransparencies = double(reshape(transparency, 1, 3));
togglestates.template = backdrop;
togglestates.tinvert = 0;
togglestates.customfile = '';
setappdata(resultfig, 'togglestates', togglestates);
end

function awin = open_anatomy_control_if_requested(resultfig, options, cfg)
awin = [];
if ~get_figure_option(cfg, 'openAnatomyControl', true)
    return;
end

try
    awin = ea_anatomycontrol(resultfig, options);
    set(awin, 'Visible', 'on');
    setappdata(resultfig, 'awin', awin);
catch ME
    warning('mh_fiber_make_scene:AnatomyControlFailed', ...
        'Could not open Lead-DBS Anatomy Slices control: %s', ME.message);
end
end

function controls = detach_transient_control_windows(resultfig)
controlNames = {'awin', 'aswin', 'conwin', 'stimwin', 'trajcontrolfig', 'mercontrolfig'};
controls = struct();
for i = 1:numel(controlNames)
    name = controlNames{i};
    try
        value = getappdata(resultfig, name);
    catch
        value = [];
    end
    controls.(name) = value;
    if ~isempty(value)
        rmappdata(resultfig, name);
    end
end
end

function restore_transient_control_windows(resultfig, controls)
controlNames = fieldnames(controls);
for i = 1:numel(controlNames)
    name = controlNames{i};
    value = controls.(name);
    if isempty(value)
        continue;
    end
    try
        setappdata(resultfig, name, value);
    catch
    end
end
end

function value = get_figure_option(cfg, fieldName, defaultValue)
if isfield(cfg, 'figure') && isfield(cfg.figure, fieldName)
    value = cfg.figure.(fieldName);
else
    value = defaultValue;
end
end

function state = visible_state(isVisible)
if isVisible
    state = 'on';
else
    state = 'off';
end
end
