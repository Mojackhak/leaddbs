function mh_fiber_style_electrodes(resultfig, cfg)
% Apply helper-figure electrode styling without changing Lead-DBS geometry.

if nargin < 1 || isempty(resultfig) || ~isgraphics(resultfig)
    return;
end

elRender = getappdata(resultfig, 'el_render');
if isempty(elRender)
    return;
end

contactColor = figure_color(cfg, 'ElectrodeContact', [0, 0, 0]);
insulationColor = figure_color(cfg, 'ElectrodeInsulation', [0.92, 0.92, 0.88]);
displayLengthMm = figure_number(cfg, 'electrodeDisplayLengthMm', 200);
displayRadiusMm = figure_number(cfg, 'electrodeDisplayRadiusMm', 0.65);

for i = 1:numel(elRender)
    if ~has_member(elRender(i), 'elpatch') || isempty(elRender(i).elpatch)
        continue;
    end

    patches = mh_fiber_valid_graphics(elRender(i).elpatch);
    for j = 1:numel(patches)
        if is_electrode_contact_patch(patches(j))
            ea_specsurf(patches(j), contactColor, get_patch_alpha(patches(j)), 'metal');
        elseif is_electrode_insulation_patch(patches(j))
            ea_specsurf(patches(j), insulationColor, get_patch_alpha(patches(j)), 'insulation');
        end
    end

    extensionHandle = add_visual_extension(resultfig, elRender(i), displayLengthMm, displayRadiusMm, insulationColor);
    if ~isempty(extensionHandle) && isgraphics(extensionHandle)
        try
            elRender(i).elpatch = [elRender(i).elpatch(:); extensionHandle];
        catch ME
            warning('mh_fiber_style_electrodes:AppendExtensionFailed', ...
                'Could not attach electrode extension to Lead toggle target: %s', ME.message);
        end
    end
end

setappdata(resultfig, 'el_render', elRender);
end

function color = figure_color(cfg, fieldName, defaultColor)
color = defaultColor;
if isfield(cfg, 'figure') && isfield(cfg.figure, 'colors') && isfield(cfg.figure.colors, fieldName)
    candidate = cfg.figure.colors.(fieldName);
    if isnumeric(candidate) && numel(candidate) == 3
        color = double(reshape(candidate, 1, 3));
    end
end
end

function value = figure_number(cfg, fieldName, defaultValue)
value = defaultValue;
if isfield(cfg, 'figure') && isfield(cfg.figure, fieldName)
    candidate = cfg.figure.(fieldName);
    if isnumeric(candidate) && isscalar(candidate) && isfinite(candidate)
        value = double(candidate);
    end
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

function isContact = is_electrode_contact_patch(handle)
isContact = patch_tag_contains(handle, 'Contact');
end

function isInsulation = is_electrode_insulation_patch(handle)
isInsulation = patch_tag_contains(handle, 'Insulation');
end

function tf = patch_tag_contains(handle, pattern)
tf = false;
if isempty(handle) || ~isgraphics(handle, 'patch')
    return;
end

try
    tag = char(string(get(handle, 'Tag')));
catch
    tag = '';
end
tf = contains(tag, pattern);
end

function alphaValue = get_patch_alpha(handle)
alphaValue = 1;
try
    currentAlpha = get(handle, 'FaceAlpha');
    if isnumeric(currentAlpha) && isscalar(currentAlpha)
        alphaValue = currentAlpha;
    end
catch
end
end

function extensionHandle = add_visual_extension(resultfig, elRender, displayLengthMm, radiusMm, color)
extensionHandle = gobjects(0);
if displayLengthMm <= 0 || radiusMm <= 0 || ~has_member(elRender, 'elstruct')
    return;
end

try
    side = elRender.side;
    coords = elRender.elstruct.coords_mm{side};
catch
    return;
end

if size(coords, 1) < 2 || size(coords, 2) ~= 3 || any(~isfinite(coords(:)))
    return;
end

distal = coords(1, :);
proximal = coords(end, :);
axisVector = proximal - distal;
currentLength = norm(axisVector);
if currentLength <= 0
    return;
end

extensionLength = displayLengthMm - currentLength;
if extensionLength <= 0
    return;
end

axisVector = axisVector ./ currentLength;
startPoint = proximal;
endPoint = distal + displayLengthMm .* axisVector;
if norm(endPoint - startPoint) <= 0
    return;
end

set(0, 'CurrentFigure', resultfig);
hold on;
try
    [extensionHandle, ~] = ea_plot3t( ...
        [startPoint(1), endPoint(1)], ...
        [startPoint(2), endPoint(2)], ...
        [startPoint(3), endPoint(3)], ...
        radiusMm, color, 24, 1);
    set(extensionHandle, ...
        'Tag', sprintf('mhFiberElectrodeExtension_Side%d', side), ...
        'UserData', struct('mh_fiber_type', 'electrode_extension', ...
        'side', side, 'display_length_mm', displayLengthMm), ...
        'FaceLighting', 'gouraud', ...
        'EdgeColor', 'none', ...
        'FaceAlpha', 1);
    ea_specsurf(extensionHandle, color, 1, 'insulation');
catch ME
    warning('mh_fiber_style_electrodes:ExtensionFailed', ...
        'Could not draw electrode visual extension: %s', ME.message);
    extensionHandle = gobjects(0);
end
end
