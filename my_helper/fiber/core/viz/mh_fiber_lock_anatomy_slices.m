function mh_fiber_lock_anatomy_slices(resultfig, anatomyFig)
% Disable direct mouse dragging of Anatomy Slices in helper scenes.

if nargin < 1 || isempty(resultfig) || ~isgraphics(resultfig)
    return;
end
if nargin < 2
    anatomyFig = [];
end

setappdata(resultfig, 'mh_fiber_slice_drag_locked', true);
disable_current_slice_handles(resultfig);
reset_slice_toolbar_mode(resultfig);
wrap_anatomy_control_callbacks(resultfig, anatomyFig);
end

function disable_current_slice_handles(resultfig)
sliceHandles = collect_slice_handles(resultfig);
for i = 1:numel(sliceHandles)
    h = sliceHandles(i);
    if ~isgraphics(h)
        continue;
    end
    if isprop(h, 'ButtonDownFcn')
        set(h, 'ButtonDownFcn', []);
    end
    if isprop(h, 'HitTest')
        set(h, 'HitTest', 'off');
    end
    if isprop(h, 'PickableParts')
        set(h, 'PickableParts', 'none');
    end
end
end

function sliceHandles = collect_slice_handles(resultfig)
sliceHandles = gobjects(0);
for name = {'xsliceplot', 'ysliceplot', 'zsliceplot'}
    if ~isappdata(resultfig, name{1})
        continue;
    end
    h = getappdata(resultfig, name{1});
    if isempty(h)
        continue;
    end
    sliceHandles = [sliceHandles; h(:)]; %#ok<AGROW>
end
sliceHandles = mh_fiber_valid_graphics(sliceHandles);
end

function reset_slice_toolbar_mode(resultfig)
uibjs = getappdata(resultfig, 'uibjs');
if isstruct(uibjs)
    if isfield(uibjs, 'slide3dtog') && isgraphics(uibjs.slide3dtog)
        set(uibjs.slide3dtog, 'State', 'off', 'Enable', 'off');
    end
    if isfield(uibjs, 'rotate3dtog') && isgraphics(uibjs.rotate3dtog)
        set(uibjs.rotate3dtog, 'State', 'on');
    end
end

slideTools = findall(resultfig, 'Type', 'uitoggletool', 'TooltipString', 'Slide Slices');
for i = 1:numel(slideTools)
    if isgraphics(slideTools(i))
        set(slideTools(i), 'State', 'off', 'Enable', 'off');
    end
end

rotateTools = findall(resultfig, 'Type', 'uitoggletool', 'TooltipString', 'Rotate - Pan - Zoom');
for i = 1:numel(rotateTools)
    if isgraphics(rotateTools(i))
        set(rotateTools(i), 'State', 'on');
    end
end

try
    ea_mouse_camera(resultfig);
catch
end
end

function wrap_anatomy_control_callbacks(resultfig, anatomyFig)
if isempty(anatomyFig) || ~isgraphics(anatomyFig)
    if isappdata(resultfig, 'awin')
        anatomyFig = getappdata(resultfig, 'awin');
    else
        return;
    end
end
if isempty(anatomyFig) || ~isgraphics(anatomyFig)
    return;
end

handles = guidata(anatomyFig);
if isempty(handles) || ~isstruct(handles)
    return;
end

callbackControls = {'templatepopup', 'xtoggle', 'ytoggle', 'ztoggle', ...
    'xval', 'yval', 'zval', 'xtrans', 'ytrans', 'ztrans', ...
    'invertcheck', 'slicepopup', 'cortexalpha'};
for i = 1:numel(callbackControls)
    name = callbackControls{i};
    if isfield(handles, name) && isgraphics(handles.(name))
        wrap_graphics_callback(handles.(name), 'Callback', resultfig);
    end
end

if isfield(handles, 'slicebuttongroup') && isgraphics(handles.slicebuttongroup)
    if isprop(handles.slicebuttongroup, 'SelectionChangedFcn')
        wrap_graphics_callback(handles.slicebuttongroup, 'SelectionChangedFcn', resultfig);
    elseif isprop(handles.slicebuttongroup, 'SelectionChangeFcn')
        wrap_graphics_callback(handles.slicebuttongroup, 'SelectionChangeFcn', resultfig);
    end
end

toolbar = getappdata(anatomyFig, 'toolbar');
if ~isempty(toolbar) && isgraphics(toolbar)
    tools = findall(toolbar, '-property', 'ClickedCallback');
    for i = 1:numel(tools)
        wrap_graphics_callback(tools(i), 'ClickedCallback', resultfig);
    end
end
end

function wrap_graphics_callback(h, propertyName, resultfig)
if ~isprop(h, propertyName)
    return;
end

originalCallback = get(h, propertyName);
if callback_is_wrapped(originalCallback)
    return;
end

set(h, propertyName, {@mh_fiber_anatomy_callback_wrapper, originalCallback, resultfig});
end

function tf = callback_is_wrapped(callbackSpec)
tf = false;
if isa(callbackSpec, 'function_handle')
    tf = strcmp(func2str(callbackSpec), 'mh_fiber_anatomy_callback_wrapper');
elseif iscell(callbackSpec) && ~isempty(callbackSpec)
    first = callbackSpec{1};
    if isa(first, 'function_handle')
        tf = strcmp(func2str(first), 'mh_fiber_anatomy_callback_wrapper');
    elseif ischar(first) || isstring(first)
        tf = strcmp(char(first), 'mh_fiber_anatomy_callback_wrapper');
    end
end
end
