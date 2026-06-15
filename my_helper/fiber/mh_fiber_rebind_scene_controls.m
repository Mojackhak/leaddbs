function mh_fiber_rebind_scene_controls(resultfig)
% Rebind helper-scene toolbar callbacks after creation or reopening a saved FIG.

if nargin < 1 || isempty(resultfig) || ~isgraphics(resultfig)
    return;
end

rebind_helper_targets(resultfig);
rebind_atlas_targets(resultfig);
rebind_lead_targets(resultfig);
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

    target = collect_lead_handles(elRender(i));
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

keep = false(size(objects));
for i = 1:numel(objects)
    objectType = '';
    try
        objectType = char(string(get(objects(i), 'Type')));
    catch
    end
    keep(i) = any(strcmp(objectType, {'patch', 'surface', 'line', 'text'}));
end

target = objects(keep);
end

function target = collect_lead_handles(elRender)
parts = {};

if isprop(elRender, 'elpatch')
    parts{end+1} = elRender.elpatch;
end
if isprop(elRender, 'patchMacro')
    parts{end+1} = elRender.patchMacro;
end

target = mh_fiber_valid_graphics(parts);
end
