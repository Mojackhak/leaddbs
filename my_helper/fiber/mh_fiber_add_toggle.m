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

objectHandle = objectHandle(ishandle(objectHandle));
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
    'OnCallback', {@set_object_visibility, objectHandle, 'on'}, ...
    'OffCallback', {@set_object_visibility, objectHandle, 'off'}, ...
    'State', state, ...
    'Tag', matlab.lang.makeValidName(label), ...
    'UserData', userData);

end

function set_object_visibility(~, ~, objectHandle, state)
objectHandle = objectHandle(ishandle(objectHandle));
if ~isempty(objectHandle)
    set(objectHandle, 'Visible', state);
end
end
