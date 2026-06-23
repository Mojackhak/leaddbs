function didBind = mh_fiber_bind_toolbar_context(toggleH, objectHandle, label)
% Bind right-click on a toolbar toggle to the helper object display control.

didBind = false;
if nargin < 3 || strlength(string(label)) == 0
    label = get(toggleH, 'TooltipString');
end

if isempty(toggleH) || ~isgraphics(toggleH)
    return;
end

objectHandle = mh_fiber_valid_graphics(objectHandle);
if isempty(objectHandle)
    return;
end

try
    drawnow limitrate;
    jtoggle = findjobj(toggleH);
    if isempty(jtoggle)
        return;
    end
    set(jtoggle, 'MouseReleasedCallback', {@open_control_on_right_click, toggleH, objectHandle, char(string(label))});
    didBind = true;
catch
    didBind = false;
end
end

function open_control_on_right_click(~, eventData, toggleH, objectHandle, label)
isRightClick = false;
try
    isRightClick = eventData.getButton() == 3 || eventData.isPopupTrigger();
catch
end

if isRightClick
    mh_fiber_open_object_control(objectHandle, label, toggleH);
end
end
