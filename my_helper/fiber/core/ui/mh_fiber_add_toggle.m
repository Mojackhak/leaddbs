function toggleH = mh_fiber_add_toggle(resultfig, objectHandle, label, color, state, userData)
% Add a color-coded toolbar toggle for a plotted object in a Lead-DBS figure.

if nargin < 5 || strlength(string(state)) == 0
    state = 'on';
end
if nargin < 6
    userData = '';
end

toggleH = [];
if isempty(objectHandle)
    return;
end

objectHandle = mh_fiber_valid_graphics(objectHandle);
if isempty(objectHandle)
    return;
end

toolbar = getappdata(resultfig, 'addht');
if isempty(toolbar) || ~ishandle(toolbar)
    toolbar = uitoolbar(resultfig);
    setappdata(resultfig, 'addht', toolbar);
end

if nargin < 4 || isempty(color) || any(isnan(color))
    icon = ea_get_icn('fibers');
else
    icon = ea_get_icn('atlas', color);
end

label = char(string(label));
state = char(string(state));

set(objectHandle, 'Visible', state);
toggleH = uitoggletool(toolbar, ...
    'CData', icon, ...
    'TooltipString', label, ...
    'OnCallback', {@mh_fiber_set_object_visibility, objectHandle, 'on'}, ...
    'OffCallback', {@mh_fiber_set_object_visibility, objectHandle, 'off'}, ...
    'State', state, ...
    'Tag', matlab.lang.makeValidName(label), ...
    'UserData', userData);
setappdata(toggleH, 'mh_fiber_target_handles', objectHandle);
setappdata(toggleH, 'mh_fiber_control_label', label);
mh_fiber_bind_toolbar_context(toggleH, objectHandle, label);

end
