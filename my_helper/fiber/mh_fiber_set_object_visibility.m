function mh_fiber_set_object_visibility(~, ~, objectHandle, state)
% Set visibility for a saved helper-scene object handle group.

objectHandle = mh_fiber_valid_graphics(objectHandle);
if isempty(objectHandle)
    return;
end

set(objectHandle, 'Visible', char(string(state)));

resultfig = ancestor(objectHandle(1), 'figure');
if ~isempty(resultfig) && isgraphics(resultfig)
    mh_fiber_hide_region_labels(resultfig);
end
end
