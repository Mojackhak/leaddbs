function figures = mh_fiber_make_scene(cfg, dirs, rois, vta)
% Generate a Lead-DBS/MATLAB scene figure with electrodes, ROI, VTA, and fibers.

figures = struct();
figures.fig = fullfile(dirs.figures, [cfg.patientName, '_', cfg.stimLabel, '_mni_scene.fig']);
figures.png = fullfile(dirs.figures, [cfg.patientName, '_', cfg.stimLabel, '_mni_scene.png']);

options = struct();
options = ea_getptopts(cfg.subjectDir, options);
options = ea_defaultoptions(options);
options.root = [fileparts(cfg.subjectDir), filesep];
[~, options.patientname] = fileparts(cfg.subjectDir);
options.leadprod = 'dbs';
options.native = 0;
options.orignative = 0;
options.d3.verbose = 'off';
options.d3.elrendering = 1;
options.d3.exportBB = 0;
options.d3.writeatlases = 0;
options.d3.showactivecontacts = 1;
options.d3.showpassivecontacts = 1;
options.d3.showisovolume = 0;
options.d3.mirrorsides = 0;
options.atlasset = 'Use none';

try
    resultfig = ea_elvis(options);
catch ME
    warning('mh_fiber_make_scene:ElvisFailed', ...
        'ea_elvis failed, falling back to a basic MATLAB figure: %s', ME.message);
    resultfig = figure('Color', 'k', 'Visible', 'off', 'Name', 'Fiber/VTA scene');
    axes('Parent', resultfig);
    hold on;
    axis equal off;
    view(3);
end

set(0, 'CurrentFigure', resultfig);
hold on;

plot_rois(resultfig, rois, cfg);
plot_vtas(resultfig, vta, cfg);
plot_fibers(resultfig, dirs, cfg);

camlight('headlight');
lighting gouraud;
axis equal off;
view(90, 0);
drawnow;

savefig(resultfig, figures.fig);
try
    exportgraphics(resultfig, figures.png, 'Resolution', 300);
catch
    print(resultfig, figures.png, '-dpng', '-r300');
end
close(resultfig);

end

function plot_rois(resultfig, rois, cfg)
toolbar = ensure_scene_toolbar(resultfig);
pobj = struct();
pobj.plotFigureH = resultfig;
pobj.htH = toolbar;
pobj.openedit = 0;
pobj.color = cfg.figure.colors.NAc;
configure_roi_toggle(ea_roi(rois.R.NAc, pobj), 'NAc R', cfg.figure.colors.NAc, cfg.figure.roiAlpha);
configure_roi_toggle(ea_roi(rois.L.NAc, pobj), 'NAc L', cfg.figure.colors.NAc, cfg.figure.roiAlpha);

pobj.color = cfg.figure.colors.ALIC;
configure_roi_toggle(ea_roi(rois.R.ALIC, pobj), 'ALIC R', cfg.figure.colors.ALIC, cfg.figure.roiAlpha);
configure_roi_toggle(ea_roi(rois.L.ALIC, pobj), 'ALIC L', cfg.figure.colors.ALIC, cfg.figure.roiAlpha);
end

function configure_roi_toggle(roiObj, label, color, alphaValue)
if isempty(roiObj)
    return;
end
roiObj.alpha = alphaValue;
if ~isempty(roiObj.toggleH) && ishandle(roiObj.toggleH)
    set(roiObj.toggleH, ...
        'CData', ea_get_icn('atlas', color), ...
        'TooltipString', label, ...
        'Tag', matlab.lang.makeValidName(label), ...
        'UserData', 'roi', ...
        'State', 'on');
end
end

function plot_vtas(resultfig, vta, cfg)
rightVta = add_vta_patch(vta.mni.R.binaryMat, cfg.figure.colors.VTA, cfg.figure.vtaAlpha);
leftVta = add_vta_patch(vta.mni.L.binaryMat, cfg.figure.colors.VTA, cfg.figure.vtaAlpha);
mh_fiber_add_toggle(resultfig, rightVta, 'VTA R', cfg.figure.colors.VTA, 'on', 'vta');
mh_fiber_add_toggle(resultfig, leftVta, 'VTA L', cfg.figure.colors.VTA, 'on', 'vta');
end

function vtaPatch = add_vta_patch(vtaMat, color, alphaValue)
data = load(vtaMat, 'vatfv');
vtaPatch = patch('Faces', data.vatfv.faces, 'Vertices', data.vatfv.vertices, ...
    'FaceColor', color, 'EdgeColor', 'none', 'FaceAlpha', alphaValue, ...
    'FaceLighting', 'gouraud', 'Tag', 'mh_fiber_vta');
end

function plot_fibers(resultfig, dirs, cfg)
fiberSpecs = {
    'R NAc-ALIC', fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-R_NAc_ALIC_intersection.mat']), [1.00, 0.84, 0.10], 0.16
    'L NAc-ALIC', fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-L_NAc_ALIC_intersection.mat']), [0.10, 0.58, 1.00], 0.16
    'R VTA-hit', fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-R_VTA_hit.mat']), [1.00, 0.45, 0.05], 0.30
    'L VTA-hit', fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-L_VTA_hit.mat']), [0.05, 0.35, 1.00], 0.30
    'R NAc-ALIC VTA-hit', fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-R_NAc_ALIC_VTA_hit.mat']), [1.00, 0.10, 0.08], 0.42
    'L NAc-ALIC VTA-hit', fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-L_NAc_ALIC_VTA_hit.mat']), [0.05, 1.00, 0.35], 0.42
    };

for i = 1:size(fiberSpecs, 1)
    show_fiber_file(resultfig, fiberSpecs{i, 2}, fiberSpecs{i, 1}, fiberSpecs{i, 3}, fiberSpecs{i, 4});
end
end

function show_fiber_file(resultfig, path, label, color, alphaValue)
if ~isfile(path)
    return;
end
data = load(path, 'fibers', 'idx');
if ~isfield(data, 'idx') || isempty(data.idx)
    return;
end
fiberHandle = ea_showfiber(data.fibers(:, 1:3), data.idx, color, alphaValue);
mh_fiber_add_toggle(resultfig, fiberHandle, sprintf('%s (%d fibers)', label, numel(data.idx)), color, 'on', 'fiber');
end

function toolbar = ensure_scene_toolbar(resultfig)
toolbar = getappdata(resultfig, 'addht');
if isempty(toolbar) || ~ishandle(toolbar)
    toolbar = uitoolbar(resultfig);
    setappdata(resultfig, 'addht', toolbar);
end
end
