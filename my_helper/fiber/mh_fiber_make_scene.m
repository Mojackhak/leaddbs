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
plot_vtas(resultfig, vta);
plot_fibers(dirs, cfg);

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
pobj = struct();
pobj.plotFigureH = resultfig;
pobj.openedit = 0;
pobj.color = cfg.figure.colors.NAc;
ea_roi(rois.R.NAc, pobj);
ea_roi(rois.L.NAc, pobj);

pobj.color = cfg.figure.colors.ALIC;
ea_roi(rois.R.ALIC, pobj);
ea_roi(rois.L.ALIC, pobj);
end

function plot_vtas(resultfig, vta)
try
    options = getappdata(resultfig, 'options');
    ea_addobj(resultfig, {vta.mni.R.binaryMat, vta.mni.L.binaryMat}, options);
catch
    add_vta_patch(vta.mni.R.binaryMat, [0.95, 0.12, 0.10], 0.35);
    add_vta_patch(vta.mni.L.binaryMat, [0.95, 0.12, 0.10], 0.35);
end
end

function add_vta_patch(vtaMat, color, alphaValue)
data = load(vtaMat, 'vatfv');
patch('Faces', data.vatfv.faces, 'Vertices', data.vatfv.vertices, ...
    'FaceColor', color, 'EdgeColor', 'none', 'FaceAlpha', alphaValue);
end

function plot_fibers(dirs, cfg)
rightNacAlic = fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-R_NAc_ALIC_intersection.mat']);
leftNacAlic = fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-L_NAc_ALIC_intersection.mat']);
rightVta = fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-R_NAc_ALIC_VTA_hit.mat']);
leftVta = fullfile(dirs.fibersMni, [cfg.patientName, '_hemi-L_NAc_ALIC_VTA_hit.mat']);

show_fiber_file(rightNacAlic, [1.00, 0.84, 0.10], 0.16);
show_fiber_file(leftNacAlic, [0.10, 0.58, 1.00], 0.16);
show_fiber_file(rightVta, [1.00, 0.10, 0.08], 0.42);
show_fiber_file(leftVta, [0.05, 1.00, 0.35], 0.42);
end

function show_fiber_file(path, color, alphaValue)
if ~isfile(path)
    return;
end
data = load(path, 'fibers', 'idx');
if ~isfield(data, 'idx') || isempty(data.idx)
    return;
end
ea_showfiber(data.fibers(:, 1:3), data.idx, color, alphaValue);
end
