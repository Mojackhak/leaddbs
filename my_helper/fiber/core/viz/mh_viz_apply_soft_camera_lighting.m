function lights = mh_viz_apply_soft_camera_lighting(hAx)
% Apply deterministic camera-relative key, fill, and top lights to scene axes.

if nargin < 1 || ~isgraphics(hAx, 'axes')
    error('mh_viz_apply_soft_camera_lighting:BadAxes', ...
        'hAx must be a valid axes handle.');
end

hFig = ancestor(hAx, 'figure');
[keyLight, rightLight, leftLight, ceilingLight] = ...
    local_resolve_elvis_lights(hAx, hFig);

set(keyLight, ...
    'Style', 'infinite', ...
    'Color', [0.98, 0.98, 0.98], ...
    'Visible', 'on', ...
    'Tag', 'mh_viz_camera_key_light');
camlight(keyLight, 'headlight');
set(keyLight, 'Color', [0.98, 0.98, 0.98], 'Visible', 'on');

set(leftLight, ...
    'Style', 'infinite', ...
    'Color', [0.14, 0.14, 0.14], ...
    'Visible', 'on', ...
    'Tag', 'mh_viz_camera_fill_light');
camlight(leftLight, 'left');
set(leftLight, 'Color', [0.14, 0.14, 0.14], 'Visible', 'on');

set(ceilingLight, ...
    'Style', 'local', ...
    'Position', [0, 0, 10], ...
    'Color', [0.08, 0.08, 0.08], ...
    'Visible', 'on', ...
    'Tag', 'mh_viz_camera_ceiling_light');
set(rightLight, 'Visible', 'off', 'Tag', 'mh_viz_elvis_right_light');
local_publish_elvis_lights( ...
    hFig, keyLight, rightLight, leftLight, ceilingLight);
local_publish_lighting_preset(hFig);
local_bind_elvis_lighting_control(hFig);
local_delete_unretained_lights( ...
    hAx, [keyLight; rightLight; leftLight; ceilingLight]);

lighting(hAx, 'gouraud');
materialObjects = [ ...
    findall(hFig, 'Type', 'patch'); ...
    findall(hFig, 'Type', 'surface')];
for index = 1:numel(materialObjects)
    set(materialObjects(index), ...
        'AmbientStrength', 0.78, ...
        'DiffuseStrength', 0.22, ...
        'SpecularStrength', 0.12, ...
        'SpecularExponent', 24, ...
        'SpecularColorReflectance', 0.20);
end

lights = [keyLight; leftLight; ceilingLight];
end

function [keyLight, rightLight, leftLight, ceilingLight] = ...
        local_resolve_elvis_lights(hAx, hFig)
keyLight = local_get_or_create_light( ...
    hFig, hAx, 'CamLight', 'mh_viz_camera_key_light', ...
    'infinite', [0, 0, 1]);
rightLight = local_get_or_create_light( ...
    hFig, hAx, 'RightLight', 'mh_viz_elvis_right_light', ...
    'infinite', [-1, 0, 0]);
leftLight = local_get_or_create_light( ...
    hFig, hAx, 'LeftLight', 'mh_viz_camera_fill_light', ...
    'infinite', [1, 0, 0]);
ceilingLight = local_get_or_create_light( ...
    hFig, hAx, 'CeilingLight', 'mh_viz_camera_ceiling_light', ...
    'local', [0, 0, 10]);
end

function hLight = local_get_or_create_light( ...
        hFig, hAx, appDataName, tag, style, position)
hLight = gobjects(0, 1);
if isgraphics(hFig, 'figure') && isappdata(hFig, appDataName)
    candidate = getappdata(hFig, appDataName);
    if local_is_axis_light(candidate, hAx)
        hLight = candidate;
    end
end
if isempty(hLight)
    tagged = findall(hAx, 'Type', 'light', 'Tag', tag);
    if ~isempty(tagged)
        hLight = tagged(1);
    end
end
if isempty(hLight)
    hLight = light(hAx, ...
        'Style', style, ...
        'Position', position, ...
        'Color', [0.14, 0.14, 0.14], ...
        'Visible', 'off', ...
        'Tag', tag);
end
end

function tf = local_is_axis_light(candidate, hAx)
tf = isscalar(candidate) && isgraphics(candidate, 'light');
if tf
    tf = isequal(get(candidate, 'Parent'), hAx);
end
end

function local_publish_elvis_lights( ...
        hFig, keyLight, rightLight, leftLight, ceilingLight)
if ~isgraphics(hFig, 'figure')
    return;
end
setappdata(hFig, 'CamLight', keyLight);
setappdata(hFig, 'RightLight', rightLight);
setappdata(hFig, 'LeftLight', leftLight);
setappdata(hFig, 'CeilingLight', ceilingLight);
end

function local_publish_lighting_preset(hFig)
if ~isgraphics(hFig, 'figure')
    return;
end
preset = struct( ...
    'ambient_strength', 0.78, ...
    'diffuse_strength', 0.22, ...
    'specular_strength', 0.12, ...
    'specular_exponent', 24, ...
    'specular_color_reflectance', 0.20);
setappdata(hFig, 'mh_viz_lighting_preset', preset);
end

function local_bind_elvis_lighting_control(hFig)
if ~isgraphics(hFig, 'figure')
    return;
end
tools = findall(hFig, 'Type', 'uipushtool');
for index = 1:numel(tools)
    try
        tooltip = get(tools(index), 'TooltipString');
    catch
        continue;
    end
    if strcmp(tooltip, 'Manually Set Lighting')
        set(tools(index), 'ClickedCallback', ...
            @(~, ~) mh_viz_open_elvis_lighting_control(hFig));
    end
end
end

function local_delete_unretained_lights(hAx, retainedLights)
existingLights = findall(hAx, 'Type', 'light');
for index = 1:numel(existingLights)
    if ~any(existingLights(index) == retainedLights)
        delete(existingLights(index));
    end
end
end
