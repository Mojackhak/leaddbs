function figures = mh_fiber_make_seed_vta_sift2_scene(cfg, dirs, seedRois, vta, result)
% Generate native- and MNI-space 3D scenes for SIFT2 seed-VTA-target outputs.

figures = struct();
figures.nativeFig = fullfile(dirs.seedVtaSift2.figures, ...
    [cfg.patientName, '_', cfg.stimLabel, '_seed_vta_sift2_native_scene.fig']);
figures.nativePng = fullfile(dirs.seedVtaSift2.figures, ...
    [cfg.patientName, '_', cfg.stimLabel, '_seed_vta_sift2_native_scene.png']);
figures.mniFig = fullfile(dirs.seedVtaSift2.figures, ...
    [cfg.patientName, '_', cfg.stimLabel, '_seed_vta_sift2_mni_scene.fig']);
figures.mniPng = fullfile(dirs.seedVtaSift2.figures, ...
    [cfg.patientName, '_', cfg.stimLabel, '_seed_vta_sift2_mni_scene.png']);

make_one_scene(cfg, seedRois, vta, result, scene_spec('native'), figures.nativeFig, figures.nativePng);
make_one_scene(cfg, seedRois, vta, result, scene_spec('mni'), figures.mniFig, figures.mniPng);
end

function make_one_scene(cfg, seedRois, vta, result, scene, figPath, pngPath)
openAfterRun = get_figure_option(cfg, 'openAfterRun', true);
options = lead_options(cfg, scene);
options.d3.verbose = 'off';
options.d3.elrendering = 1;
options.d3.exportBB = 0;
options.d3.writeatlases = 0;
options.d3.showactivecontacts = 1;
options.d3.showpassivecontacts = 1;
options.d3.showisovolume = 0;
options.d3.mirrorsides = 0;
options.writeoutstats = 0;

try
    resultfig = ea_elvis(options);
catch ME
    warning('mh_fiber_make_seed_vta_sift2_scene:ElvisFailed', ...
        'ea_elvis failed, falling back to a basic MATLAB figure: %s', ME.message);
    resultfig = figure('Color', 'k', 'Visible', visible_state(openAfterRun), ...
        'Name', ['Seed-VTA SIFT2 scene ', scene.name]);
    axes('Parent', resultfig);
    hold on;
    axis equal off;
    view(3);
end

setappdata(resultfig, 'options', options);
initialize_anatomy_togglestates(resultfig, options, cfg);
set(0, 'CurrentFigure', resultfig);
hold on;

handles = struct();
handles.rois = plot_anatomical_seed_rois(resultfig, seedRois, cfg, scene);
handles.vtas = plot_stimulation_vtas(resultfig, vta, cfg, scene);
handles.seedVta = plot_seed_vta_rois(resultfig, result, cfg, scene);
handles.targets = plot_target_rois(resultfig, seedRois, result, scene);
handles.fibers = plot_display_fibers(resultfig, result, scene);
add_global_toggles(resultfig, handles, cfg);

camlight('headlight');
lighting gouraud;
axis equal off;
view(90, 0);
drawnow;

mh_fiber_hide_region_labels(resultfig);
open_anatomy_control_if_requested(resultfig, options, cfg);
set(resultfig, 'Visible', visible_state(openAfterRun));
drawnow;
transientControls = detach_transient_control_windows(resultfig);
savefig(resultfig, figPath);
restore_transient_control_windows(resultfig, transientControls);
export_scene_png(resultfig, pngPath, openAfterRun);
if get_figure_option(cfg, 'closeAfterSave', false)
    close(resultfig);
end
end

function scene = scene_spec(name)
switch lower(name)
    case 'native'
        scene.name = 'native';
        scene.roiField = 'anchorNative';
        scene.vtaField = 'native';
        scene.displayColumn = 'native_display_mat';
        scene.seedVtaSuffix = 'space-anchorNative.nii';
        scene.native = true;
    case 'mni'
        scene.name = 'mni';
        scene.roiField = 'mni';
        scene.vtaField = 'mni';
        scene.displayColumn = 'mni_display_mat';
        scene.seedVtaSuffix = 'space-MNI152NLin2009bAsym.nii';
        scene.native = false;
    otherwise
        error('mh_fiber_make_seed_vta_sift2_scene:UnknownSceneSpace', ...
            'Unknown scene space: %s', name);
end
end

function options = lead_options(cfg, scene)
options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options = ea_defaultoptions(options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);
options.leadprod = 'dbs';
options.native = double(scene.native);
options.orignative = double(scene.native);
end

function roiHandles = plot_anatomical_seed_rois(resultfig, seedRois, cfg, scene)
roiHandles = gobjects(0);
roiSet = seedRois.(scene.roiField);
for sideCell = {'R', 'L'}
    side = sideCell{1};
    roiHandles(end+1) = add_roi(resultfig, roiSet.(side).NAc, ...
        sprintf('NAc %s', side), cfg.figure.colors.NAc, 0.12, 'roi', 'on'); %#ok<AGROW>
    roiHandles(end+1) = add_roi(resultfig, roiSet.(side).ALIC, ...
        sprintf('ALIC %s', side), cfg.figure.colors.ALIC, 0.12, 'roi', 'on'); %#ok<AGROW>
end
roiHandles = mh_fiber_valid_graphics(roiHandles);
end

function vtaHandles = plot_stimulation_vtas(resultfig, vta, cfg, scene)
vtaHandles = gobjects(0);
vtaSet = vta.(scene.vtaField);
for sideCell = {'R', 'L'}
    side = sideCell{1};
    data = load(vtaSet.(side).binaryMat, 'vatfv');
    h = patch('Faces', data.vatfv.faces, 'Vertices', data.vatfv.vertices, ...
        'FaceColor', cfg.figure.colors.VTA, 'EdgeColor', 'none', ...
        'FaceAlpha', cfg.figure.vtaAlpha, 'FaceLighting', 'gouraud', ...
        'Tag', ['StimVTA', side], ...
        'UserData', struct('mh_fiber_type', 'stimulation_vta', 'side', side, 'space', scene.name));
    mh_fiber_add_toggle(resultfig, h, sprintf('Stim VTA %s', side), cfg.figure.colors.VTA, 'on', 'stimulation_vta');
    vtaHandles(end+1) = h; %#ok<AGROW>
end
vtaHandles = mh_fiber_valid_graphics(vtaHandles);
end

function seedVtaHandles = plot_seed_vta_rois(resultfig, result, cfg, scene)
seedVtaHandles = gobjects(0);
colors = seed_vta_colors();
defaultVisible = seed_vta_default_state(cfg);
for sideCell = {'R', 'L'}
    side = sideCell{1};
    for seedCell = {'NAc', 'ALIC'}
        seedName = seedCell{1};
        path = fullfile(result.dirs.work, sprintf('%s_hemi-%s_seed-%s_intersect-stimulationVTA_%s', ...
            cfg.patientName, side, seedName, scene.seedVtaSuffix));
        if ~isfile(path)
            continue;
        end
        key = [seedName, side];
        h = add_roi(resultfig, path, sprintf('%s%sVTA %s', seedName, char(8745), side), ...
            colors.(key), 0.62, 'seed_vta', defaultVisible);
        seedVtaHandles(end+1) = h; %#ok<AGROW>
    end
end
seedVtaHandles = mh_fiber_valid_graphics(seedVtaHandles);
end

function targetHandles = plot_target_rois(resultfig, seedRois, result, scene)
targetHandles = gobjects(0);
summary = result.summaryTable;
targets = unique(string(summary.target(summary.target_streamline_count > 0)), 'stable');
roiSet = seedRois.(scene.roiField);
for sideCell = {'R', 'L'}
    side = sideCell{1};
    for i = 1:numel(targets)
        targetName = char(targets(i));
        if ~isfield(roiSet, side) || ~isfield(roiSet.(side), targetName)
            continue;
        end
        color = target_color(targetName);
        label = target_label(targetName, side);
        h = add_roi(resultfig, roiSet.(side).(targetName), label, color, 0.10, 'target_roi', 'on');
        targetHandles(end+1) = h; %#ok<AGROW>
    end
end
targetHandles = mh_fiber_valid_graphics(targetHandles);
end

function fiberHandles = plot_display_fibers(resultfig, result, scene)
fiberHandles = gobjects(0);
display = result.displayTable;
for i = 1:height(display)
    path = table_char(display, scene.displayColumn, i);
    if ~isfile(path)
        continue;
    end
    data = load(path, 'fibers', 'idx');
    if ~isfield(data, 'idx') || isempty(data.idx)
        continue;
    end
    targetName = table_char(display, 'target', i);
    side = table_char(display, 'side', i);
    seedName = table_char(display, 'seed', i);
    color = target_color(targetName);
    h = ea_showfiber(data.fibers(:, 1:3), data.idx, color, 0.36);
    label = sprintf('%s %s%sVTA to %s (%d)', side, seedName, char(8745), targetName, ...
        display.display_streamline_count(i));
    mh_fiber_add_toggle(resultfig, h, label, color, 'on', 'seed_vta_sift2_fiber');
    fiberHandles = [fiberHandles; mh_fiber_valid_graphics(h(:))]; %#ok<AGROW>
end
fiberHandles = mh_fiber_valid_graphics(fiberHandles);
end

function h = add_roi(resultfig, path, label, color, alphaValue, userData, state)
h = [];
if nargin < 7
    state = 'on';
end
if ~isfile(path)
    return;
end
nii = ea_load_nii(path);
mask = double(nii.img) ~= 0;
if ~any(mask(:))
    return;
end
fv = roi_mask_to_surface(mask, nii.mat);
if isempty(fv) || isempty(fv.faces) || isempty(fv.vertices)
    return;
end
h = patch('Faces', fv.faces, 'Vertices', fv.vertices, ...
    'FaceColor', color, 'EdgeColor', 'none', 'FaceAlpha', alphaValue, ...
    'FaceLighting', 'gouraud', 'Tag', matlab.lang.makeValidName(label), ...
    'UserData', struct('mh_fiber_type', userData, 'label', label, 'source', path));
mh_fiber_add_toggle(resultfig, h, label, color, state, userData);
end

function fv = roi_mask_to_surface(mask, mat)
imgSize = size(mask);
[xVox, yVox, zVox] = meshgrid(1:imgSize(1), 1:imgSize(2), 1:imgSize(3));
xyzMm = ea_vox2mm([xVox(:), yVox(:), zVox(:)], mat);
x = reshape(xyzMm(:, 1), size(xVox));
y = reshape(xyzMm(:, 2), size(yVox));
z = reshape(xyzMm(:, 3), size(zVox));
mask = permute(double(mask), [2, 1, 3]);
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
try
    fv = reducepatch(fv, 0.45);
catch
end
end

function add_global_toggles(resultfig, handles, cfg)
roiGroup = mh_fiber_valid_graphics([handles.rois(:); handles.targets(:)]);
seedVtaGroup = mh_fiber_valid_graphics(handles.seedVta(:));
fiberGroup = mh_fiber_valid_graphics(handles.fibers(:));
vtaGroup = mh_fiber_valid_graphics(handles.vtas(:));
if ~isempty(roiGroup)
    mh_fiber_add_toggle(resultfig, roiGroup, 'All ROIs', [0.85, 0.85, 0.85], 'on', 'global_roi');
end
if ~isempty(seedVtaGroup)
    mh_fiber_add_toggle(resultfig, seedVtaGroup, 'All seed-VTA ROIs', [0.95, 0.86, 0.20], ...
        seed_vta_default_state(cfg), 'global_seed_vta');
end
if ~isempty(fiberGroup)
    mh_fiber_add_toggle(resultfig, fiberGroup, 'All fibers', [0.95, 0.95, 0.95], 'on', 'global_fiber');
end
if ~isempty(vtaGroup)
    mh_fiber_add_toggle(resultfig, vtaGroup, 'All stimulation VTA', cfg.figure.colors.VTA, 'on', 'global_vta');
end
end

function colors = seed_vta_colors()
colors = struct();
colors.NAcR = [1.00, 0.88, 0.05];
colors.NAcL = [0.95, 0.78, 0.18];
colors.ALICR = [0.00, 0.88, 0.50];
colors.ALICL = [0.12, 0.74, 0.58];
end

function color = target_color(targetName)
switch lower(targetName)
    case 'mpfc'
        color = [0.20, 0.52, 0.95];
    case 'ofc'
        color = [1.00, 0.50, 0.05];
    case 'acc'
        color = [0.58, 0.34, 0.92];
    case 'amygdala'
        color = [0.86, 0.18, 0.55];
    case 'hippocampus'
        color = [0.15, 0.70, 0.78];
    case 'thalamus'
        color = [0.62, 0.62, 0.16];
    case 'vta'
        color = [0.95, 0.08, 0.08];
    otherwise
        color = [0.80, 0.80, 0.80];
end
end

function label = target_label(targetName, side)
if strcmpi(targetName, 'VTA')
    label = sprintf('Anatomical VTA %s', side);
else
    label = sprintf('%s %s', targetName, side);
end
end

function initialize_anatomy_togglestates(resultfig, options, cfg)
if isappdata(resultfig, 'togglestates')
    return;
end
spacedef = ea_getspacedef;
if isfield(spacedef, 'guidef') && isfield(spacedef.guidef, 'xyzdef')
    xyzmm = spacedef.guidef.xyzdef;
else
    xyzmm = [0, 0, 0];
end
availableBackdrops = ea_assignbackdrop('list', options, 'Patient', options.native);
if isempty(availableBackdrops)
    backdrop = '';
else
    requested = char(string(get_figure_option(cfg, 'defaultBackdrop', availableBackdrops{1})));
    if any(strcmp(availableBackdrops, requested))
        backdrop = requested;
    else
        backdrop = availableBackdrops{1};
    end
end
togglestates = struct();
togglestates.cutview = '3d';
togglestates.refreshcuts = 1;
togglestates.refreshview = 1;
togglestates.xyzmm = double(reshape(xyzmm, 1, 3));
togglestates.xyztoggles = [1, 1, 1];
togglestates.xyztransparencies = double(reshape(get_figure_option(cfg, 'defaultSliceTransparency', [100, 100, 100]), 1, 3));
togglestates.template = backdrop;
togglestates.tinvert = 0;
togglestates.customfile = '';
setappdata(resultfig, 'togglestates', togglestates);
end

function open_anatomy_control_if_requested(resultfig, options, cfg)
if ~get_figure_option(cfg, 'openAnatomyControl', true)
    return;
end
try
    awin = ea_anatomycontrol(resultfig, options);
    set(awin, 'Visible', 'on');
    setappdata(resultfig, 'awin', awin);
catch ME
    warning('mh_fiber_make_seed_vta_sift2_scene:AnatomyControlFailed', ...
        'Could not open Anatomy Slices control: %s', ME.message);
end
end

function export_scene_png(resultfig, pngPath, keepVisible)
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

function controls = detach_transient_control_windows(resultfig)
controlNames = {'awin', 'aswin', 'conwin', 'stimwin', 'trajcontrolfig', 'mercontrolfig'};
controls = struct();
for i = 1:numel(controlNames)
    name = controlNames{i};
    if isappdata(resultfig, name)
        controls.(name) = getappdata(resultfig, name);
        rmappdata(resultfig, name);
    else
        controls.(name) = [];
    end
end
end

function restore_transient_control_windows(resultfig, controls)
names = fieldnames(controls);
for i = 1:numel(names)
    if ~isempty(controls.(names{i}))
        setappdata(resultfig, names{i}, controls.(names{i}));
    end
end
end

function state = seed_vta_default_state(cfg)
visible = false;
if isfield(cfg, 'seedVtaSift2') && isfield(cfg.seedVtaSift2, 'seedVtaRoiDefaultVisible')
    visible = logical(cfg.seedVtaSift2.seedVtaRoiDefaultVisible);
end
state = visible_state(visible);
end

function value = table_char(tableData, columnName, row)
value = tableData.(columnName);
if iscell(value)
    value = value{row};
else
    value = value(row);
end
value = char(string(value));
end

function state = visible_state(tf)
if tf
    state = 'on';
else
    state = 'off';
end
end

function value = get_figure_option(cfg, fieldName, defaultValue)
if isfield(cfg, 'figure') && isfield(cfg.figure, fieldName)
    value = cfg.figure.(fieldName);
else
    value = defaultValue;
end
end
