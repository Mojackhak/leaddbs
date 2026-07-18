function mh_fiber_hide_region_labels(resultfig)
% Hide in-scene text labels for helper-generated Fiber/VTA figures.

if nargin < 1 || isempty(resultfig) || ~isgraphics(resultfig)
    return;
end

if isappdata(resultfig, 'mh_fiber_show_region_labels') && ...
        isequal(getappdata(resultfig, 'mh_fiber_show_region_labels'), true)
    return;
end

regionLabels = findall(resultfig, 'Type', 'text');
if isempty(regionLabels)
    return;
end

set(regionLabels, 'Visible', 'off');
end
