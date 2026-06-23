function mh_fiber_rebind_scene_controls(resultfig)
% Rebind helper-scene toolbar callbacks after creation or reopening a saved FIG.

if nargin < 1 || isempty(resultfig) || ~isgraphics(resultfig)
    return;
end

rebind_helper_targets(resultfig);
rebind_atlas_targets(resultfig);
rebind_lead_targets(resultfig);
mh_fiber_hide_region_labels(resultfig);
end

function rebind_helper_targets(resultfig)
toggles = findall(resultfig, 'Type', 'uitoggletool');
for i = 1:numel(toggles)
    target = getappdata(toggles(i), 'mh_fiber_target_handles');
    if isempty(target)
        continue;
    end
    bind_toggle_to_target(toggles(i), target, get(toggles(i), 'TooltipString'));
end
end

function rebind_atlas_targets(resultfig)
toggles = findall(resultfig, 'Type', 'uitoggletool');
for i = 1:numel(toggles)
    tag = char(string(get(toggles(i), 'Tag')));
    if isempty(tag) || startsWith(tag, 'Patient:') || startsWith(tag, 'Group:')
        continue;
    end
    if strcmp(tag, 'Labels') || strcmp(tag, 'Atlas Control') || strcmp(tag, 'elLabelToggle')
        continue;
    end

    target = find_tagged_scene_objects(resultfig, tag);
    if isempty(target)
        continue;
    end

    currentUserData = get(toggles(i), 'UserData');
    if isempty(currentUserData)
        set(toggles(i), 'UserData', 'atlas_roi');
    end
    bind_toggle_to_target(toggles(i), target, get(toggles(i), 'TooltipString'));
end
end

function rebind_lead_targets(resultfig)
elRender = getappdata(resultfig, 'el_render');
if isempty(elRender)
    return;
end

for i = 1:numel(elRender)
    if ~isprop(elRender(i), 'toggleH') || isempty(elRender(i).toggleH) || ~isgraphics(elRender(i).toggleH)
        continue;
    end

    target = collect_lead_handles(elRender(i), resultfig);
    if isempty(target)
        continue;
    end

    set(elRender(i).toggleH, 'UserData', 'lead');
    bind_toggle_to_target(elRender(i).toggleH, target, get(elRender(i).toggleH, 'TooltipString'));
end
end

function bind_toggle_to_target(toggleH, target, label)
target = mh_fiber_valid_graphics(target);
if isempty(target) || isempty(toggleH) || ~isgraphics(toggleH)
    return;
end

label = char(string(label));
setappdata(toggleH, 'mh_fiber_target_handles', target);
setappdata(toggleH, 'mh_fiber_control_label', label);
set(toggleH, ...
    'OnCallback', {@mh_fiber_set_object_visibility, target, 'on'}, ...
    'OffCallback', {@mh_fiber_set_object_visibility, target, 'off'});
mh_fiber_bind_toolbar_context(toggleH, target, label);
end

function target = find_tagged_scene_objects(resultfig, tag)
objects = findall(resultfig, '-property', 'Visible', 'Tag', tag);
objects = mh_fiber_valid_graphics(objects);

visibleObjectTypes = {'patch', 'surface', 'line'};
if region_labels_enabled(resultfig)
    visibleObjectTypes{end+1} = 'text';
end

keep = false(size(objects));
for i = 1:numel(objects)
    objectType = '';
    try
        objectType = char(string(get(objects(i), 'Type')));
    catch
    end
    keep(i) = any(strcmp(objectType, visibleObjectTypes));
end

target = objects(keep);
end

function enabled = region_labels_enabled(resultfig)
enabled = false;
if isappdata(resultfig, 'mh_fiber_show_region_labels')
    enabled = isequal(getappdata(resultfig, 'mh_fiber_show_region_labels'), true);
end
end

function target = collect_lead_handles(elRender, resultfig)
parts = {};

if has_member(elRender, 'elpatch')
    parts{end+1} = elRender.elpatch;
end
if has_member(elRender, 'patchMacro')
    parts{end+1} = elRender.patchMacro;
end

side = lead_side(elRender);
if ~isnan(side)
    parts{end+1} = findall(resultfig, '-regexp', 'Tag', ...
        sprintf('^mhFiberElectrodeExtension_Side%d$', side));
else
    parts{end+1} = findall(resultfig, '-regexp', 'Tag', ...
        '^mhFiberElectrodeExtension_Side[0-9]+$');
end

target = mh_fiber_valid_graphics(parts);
end

function side = lead_side(elRender)
side = NaN;
try
    if has_member(elRender, 'side')
        candidate = elRender.side;
    else
        return;
    end
    if isnumeric(candidate) && isscalar(candidate) && isfinite(candidate)
        side = double(candidate);
    end
catch
end
end

function tf = has_member(value, memberName)
tf = false;
try
    if isstruct(value)
        tf = isfield(value, memberName);
    else
        tf = isprop(value, memberName);
    end
catch
end
end
