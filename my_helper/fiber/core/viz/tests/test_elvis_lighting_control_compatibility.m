% Verify that scene lighting preserves native Elvis lighting-control handles.

testRoot = fileparts(mfilename('fullpath'));
vizRoot = fileparts(testRoot);
addpath(vizRoot);

hFig = figure('Visible', 'off');
figureCleanup = onCleanup(@() local_close_figure(hFig));
hAx = axes('Parent', hFig);
toolbar = uitoolbar(hFig);
manualLightingTool = uipushtool(toolbar, ...
    'TooltipString', 'Manually Set Lighting', ...
    'ClickedCallback', @(~, ~) error('Original callback was not replaced.'));
surfacePatch = patch(hAx, ...
    'Faces', [1, 2, 3], ...
    'Vertices', [0, 0, 0; 1, 0, 0; 0, 1, 0], ...
    'FaceColor', [0.8, 0.2, 0.2], ...
    'EdgeColor', 'none');
wireframePatch = patch(hAx, ...
    'Faces', [1, 2, 3], ...
    'Vertices', [0, 0, 1; 1, 0, 1; 0, 1, 1], ...
    'FaceColor', 'none', ...
    'EdgeColor', [0.1, 0.8, 0.1]);
anatomySurface = surface(hAx, ...
    [0, 1; 0, 1], [0, 0; 1, 1], zeros(2), ...
    'FaceColor', 'texturemap', ...
    'CData', repmat(reshape([0.5, 0.5, 0.5], 1, 1, 3), 2, 2));

camLight = light(hAx, ...
    'Style', 'infinite', 'Position', [0, 0, 1], 'Visible', 'on');
rightLight = light(hAx, ...
    'Style', 'infinite', 'Position', [-1, 0, 0], 'Visible', 'on');
leftLight = light(hAx, ...
    'Style', 'infinite', 'Position', [1, 0, 0], 'Visible', 'on');
ceilingLight = light(hAx, ...
    'Style', 'local', 'Position', [0, 0, 10], 'Visible', 'on');
staleLight = light(hAx, ...
    'Style', 'infinite', 'Position', [0, 1, 0], 'Visible', 'on');

setappdata(hFig, 'CamLight', camLight);
setappdata(hFig, 'RightLight', rightLight);
setappdata(hFig, 'LeftLight', leftLight);
setappdata(hFig, 'CeilingLight', ceilingLight);

activeLights = mh_viz_apply_soft_camera_lighting(hAx);

assert(isequal(activeLights, [camLight; leftLight; ceilingLight]));
assert(isgraphics(camLight, 'light'));
assert(isgraphics(rightLight, 'light'));
assert(isgraphics(leftLight, 'light'));
assert(isgraphics(ceilingLight, 'light'));
assert(~isgraphics(staleLight));
assert(isequal(getappdata(hFig, 'CamLight'), camLight));
assert(isequal(getappdata(hFig, 'RightLight'), rightLight));
assert(isequal(getappdata(hFig, 'LeftLight'), leftLight));
assert(isequal(getappdata(hFig, 'CeilingLight'), ceilingLight));
assert(strcmp(get(camLight, 'Visible'), 'on'));
assert(strcmp(get(rightLight, 'Visible'), 'off'));
assert(strcmp(get(leftLight, 'Visible'), 'on'));
assert(strcmp(get(ceilingLight, 'Visible'), 'on'));
assert(isequal(get(camLight, 'Color'), [0.98, 0.98, 0.98]));
assert(isequal(get(leftLight, 'Color'), [0.14, 0.14, 0.14]));
assert(isequal(get(ceilingLight, 'Color'), [0.08, 0.08, 0.08]));
assert(get(surfacePatch, 'AmbientStrength') == 0.78);
assert(get(surfacePatch, 'DiffuseStrength') == 0.22);
assert(get(surfacePatch, 'SpecularStrength') == 0.12);
assert(get(surfacePatch, 'SpecularExponent') == 24);
assert(get(surfacePatch, 'SpecularColorReflectance') == 0.20);
assert(get(wireframePatch, 'AmbientStrength') == 0.78);
assert(get(wireframePatch, 'DiffuseStrength') == 0.22);
assert(get(wireframePatch, 'SpecularStrength') == 0.12);
assert(get(wireframePatch, 'SpecularExponent') == 24);
assert(get(wireframePatch, 'SpecularColorReflectance') == 0.20);
assert(get(anatomySurface, 'AmbientStrength') == 0.78);
assert(get(anatomySurface, 'DiffuseStrength') == 0.22);
assert(get(anatomySurface, 'SpecularStrength') == 0.12);
assert(get(anatomySurface, 'SpecularExponent') == 24);
assert(get(anatomySurface, 'SpecularColorReflectance') == 0.20);
preset = getappdata(hFig, 'mh_viz_lighting_preset');
assert(preset.ambient_strength == 0.78);
assert(preset.diffuse_strength == 0.22);
assert(preset.specular_strength == 0.12);
assert(preset.specular_exponent == 24);
assert(preset.specular_color_reflectance == 0.20);
manualCallback = get(manualLightingTool, 'ClickedCallback');
assert(contains( ...
    func2str(manualCallback), 'mh_viz_open_elvis_lighting_control'));

secondLights = mh_viz_apply_soft_camera_lighting(hAx);
assert(isequal(secondLights, activeLights));
assert(isequal(getappdata(hFig, 'CamLight'), camLight));
assert(isequal(getappdata(hFig, 'LeftLight'), leftLight));

fprintf('Elvis lighting-control compatibility test passed.\n');

function local_close_figure(hFig)
if isgraphics(hFig, 'figure')
    close(hFig);
end
end
