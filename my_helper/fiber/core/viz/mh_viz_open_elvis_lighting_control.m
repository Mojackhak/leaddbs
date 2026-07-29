function app = mh_viz_open_elvis_lighting_control(hFig)
% Open the native Elvis lighting app with the active scene preset.

if nargin < 1 || ~isgraphics(hFig, 'figure')
    error('mh_viz_open_elvis_lighting_control:BadFigure', ...
        'hFig must be a valid figure handle.');
end
if exist('ea_set_lighting', 'file') ~= 2
    error('mh_viz_open_elvis_lighting_control:MissingNativeApp', ...
        'ea_set_lighting is unavailable.');
end

app = ea_set_lighting(hFig);
preset = getappdata(hFig, 'mh_viz_lighting_preset');
if isempty(preset)
    return;
end

requiredFields = { ...
    'ambient_strength', ...
    'diffuse_strength', ...
    'specular_strength', ...
    'specular_exponent', ...
    'specular_color_reflectance'};
for index = 1:numel(requiredFields)
    fieldName = requiredFields{index};
    if ~isfield(preset, fieldName)
        error('mh_viz_open_elvis_lighting_control:BadPreset', ...
            'Lighting preset field %s is missing.', fieldName);
    end
    value = preset.(fieldName);
    if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value)
        error('mh_viz_open_elvis_lighting_control:BadPreset', ...
            'Lighting preset field %s must be a finite numeric scalar.', ...
            fieldName);
    end
end

app.AmbientStrengthSlider.Value = preset.ambient_strength;
app.DiffuseStrengthSlider.Value = preset.diffuse_strength;
app.SpecularStrengthSlider.Value = preset.specular_strength;
app.SpecularExponentSlider.Value = preset.specular_exponent;
app.SpecularColorReflectanceSlider.Value = ...
    preset.specular_color_reflectance;
end
