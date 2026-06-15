function resultfig = mh_fiber_open_scene(figPath)
% Open a saved Fiber/VTA helper scene and show the Lead-DBS Anatomy Slices UI.

if nargin < 1 || strlength(string(figPath)) == 0
    error('mh_fiber_open_scene:MissingFigurePath', 'figPath is required.');
end

figPath = char(string(figPath));
if ~isfile(figPath)
    error('mh_fiber_open_scene:MissingFigure', 'Figure file does not exist: %s', figPath);
end

resultfig = openfig(figPath, 'new', 'visible');
set(resultfig, 'Visible', 'on');
figure(resultfig);

options = getappdata(resultfig, 'options');
if isempty(options)
    warning('mh_fiber_open_scene:MissingOptions', ...
        'The figure does not contain Lead-DBS options appdata; Anatomy Slices cannot be opened automatically.');
    drawnow;
    return;
end

if ~isfield(options, 'd3') || ~isstruct(options.d3)
    options.d3 = struct();
end
options.d3.verbose = 'on';
setappdata(resultfig, 'options', options);

try
    awin = ea_anatomycontrol(resultfig, options);
    set(awin, 'Visible', 'on');
    setappdata(resultfig, 'awin', awin);
catch ME
    warning('mh_fiber_open_scene:AnatomyControlFailed', ...
        'Could not open Lead-DBS Anatomy Slices control: %s', ME.message);
end

drawnow;
end
