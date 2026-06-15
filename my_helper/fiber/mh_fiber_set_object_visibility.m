function mh_fiber_set_object_visibility(~, ~, objectHandle, state)
% Set visibility for a saved helper-scene object handle group.

objectHandle = mh_fiber_valid_graphics(objectHandle);
if isempty(objectHandle)
    return;
end

set(objectHandle, 'Visible', char(string(state)));
end
