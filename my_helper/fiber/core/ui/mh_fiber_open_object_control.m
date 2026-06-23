function controlFig = mh_fiber_open_object_control(objectHandle, label, toggleH)
% Open a lightweight display-control window for helper-scene objects.

if nargin < 2 || strlength(string(label)) == 0
    label = 'Object';
end
if nargin < 3
    toggleH = [];
end

objectHandle = mh_fiber_valid_graphics(objectHandle);
if isempty(objectHandle)
    controlFig = [];
    return;
end

if ~isempty(toggleH) && isgraphics(toggleH)
    existingFig = getappdata(toggleH, 'mh_fiber_control_figure');
    if ~isempty(existingFig) && isgraphics(existingFig)
        figure(existingFig);
        controlFig = existingFig;
        return;
    end
end

label = char(string(label));
controlFig = figure( ...
    'Name', label, ...
    'NumberTitle', 'off', ...
    'MenuBar', 'none', ...
    'ToolBar', 'none', ...
    'Color', 'w', ...
    'Position', [100, 100, 360, 300]);

if ~isempty(toggleH) && isgraphics(toggleH)
    setappdata(toggleH, 'mh_fiber_control_figure', controlFig);
end

uicontrol(controlFig, ...
    'Style', 'checkbox', ...
    'String', 'Visible', ...
    'Value', object_is_visible(objectHandle), ...
    'BackgroundColor', 'w', ...
    'Position', [28, 246, 180, 28], ...
    'Callback', @(src, ~) set_visible(src.Value));

uicontrol(controlFig, ...
    'Style', 'checkbox', ...
    'String', 'Face Color', ...
    'Value', has_supported_property(objectHandle, 'FaceColor'), ...
    'Enable', enabled_state(has_supported_property(objectHandle, 'FaceColor')), ...
    'BackgroundColor', 'w', ...
    'Position', [28, 195, 180, 28], ...
    'Callback', @(src, ~) set_face_color_enabled(src.Value));

faceButton = uicontrol(controlFig, ...
    'Style', 'pushbutton', ...
    'String', '', ...
    'BackgroundColor', first_numeric_color(objectHandle, 'FaceColor', [1, 0, 0]), ...
    'Enable', enabled_state(has_supported_property(objectHandle, 'FaceColor')), ...
    'Position', [230, 196, 100, 30], ...
    'Callback', @(~, ~) choose_face_color());

uicontrol(controlFig, ...
    'Style', 'checkbox', ...
    'String', 'Edge Color', ...
    'Value', edge_color_is_enabled(objectHandle), ...
    'Enable', enabled_state(has_supported_property(objectHandle, 'EdgeColor')), ...
    'BackgroundColor', 'w', ...
    'Position', [28, 145, 180, 28], ...
    'Callback', @(src, ~) set_edge_color_enabled(src.Value));

edgeButton = uicontrol(controlFig, ...
    'Style', 'pushbutton', ...
    'String', '', ...
    'BackgroundColor', first_numeric_color(objectHandle, 'EdgeColor', [1, 1, 1]), ...
    'Enable', enabled_state(has_supported_property(objectHandle, 'EdgeColor')), ...
    'Position', [230, 146, 100, 30], ...
    'Callback', @(~, ~) choose_edge_color());

uicontrol(controlFig, ...
    'Style', 'text', ...
    'String', 'Alpha:', ...
    'HorizontalAlignment', 'left', ...
    'BackgroundColor', 'w', ...
    'Position', [28, 92, 100, 24]);

alphaText = uicontrol(controlFig, ...
    'Style', 'text', ...
    'String', sprintf('%.2f', first_numeric_scalar(objectHandle, 'FaceAlpha', 1)), ...
    'HorizontalAlignment', 'right', ...
    'BackgroundColor', 'w', ...
    'Position', [242, 92, 88, 24]);

uicontrol(controlFig, ...
    'Style', 'slider', ...
    'Min', 0, ...
    'Max', 1, ...
    'Value', first_numeric_scalar(objectHandle, 'FaceAlpha', 1), ...
    'Enable', enabled_state(has_supported_property(objectHandle, 'FaceAlpha')), ...
    'Position', [28, 54, 302, 28], ...
    'Callback', @(src, ~) set_alpha(src.Value));

    function set_visible(isVisible)
        if isVisible
            state = 'on';
        else
            state = 'off';
        end
        mh_fiber_set_object_visibility([], [], objectHandle, state);
        if ~isempty(toggleH) && isgraphics(toggleH)
            set(toggleH, 'State', state);
        end
    end

    function set_face_color_enabled(isEnabled)
        if isEnabled
            set_supported_property(objectHandle, 'FaceColor', faceButton.BackgroundColor);
        else
            set_supported_property(objectHandle, 'FaceColor', 'none');
        end
    end

    function choose_face_color()
        color = uisetcolor(faceButton.BackgroundColor, ['Face Color: ', label]);
        if numel(color) == 3
            faceButton.BackgroundColor = color;
            set_supported_property(objectHandle, 'FaceColor', color);
        end
    end

    function set_edge_color_enabled(isEnabled)
        if isEnabled
            set_supported_property(objectHandle, 'EdgeColor', edgeButton.BackgroundColor);
        else
            set_supported_property(objectHandle, 'EdgeColor', 'none');
        end
    end

    function choose_edge_color()
        color = uisetcolor(edgeButton.BackgroundColor, ['Edge Color: ', label]);
        if numel(color) == 3
            edgeButton.BackgroundColor = color;
            set_supported_property(objectHandle, 'EdgeColor', color);
        end
    end

    function set_alpha(alphaValue)
        set_supported_property(objectHandle, 'FaceAlpha', alphaValue);
        alphaText.String = sprintf('%.2f', alphaValue);
    end
end

function visible = object_is_visible(objectHandle)
visibleValues = get_property_values(objectHandle, 'Visible');
if isempty(visibleValues)
    visible = true;
else
    visible = any(strcmp(visibleValues, 'on'));
end
end

function enabled = edge_color_is_enabled(objectHandle)
edgeColors = get_property_values(objectHandle, 'EdgeColor');
enabled = false;
for i = 1:numel(edgeColors)
    if isnumeric(edgeColors{i}) || ~strcmp(edgeColors{i}, 'none')
        enabled = true;
        return;
    end
end
end

function hasProperty = has_supported_property(objectHandle, propertyName)
hasProperty = any(arrayfun(@(h) isprop(h, propertyName), objectHandle));
end

function state = enabled_state(isEnabled)
if isEnabled
    state = 'on';
else
    state = 'off';
end
end

function color = first_numeric_color(objectHandle, propertyName, defaultColor)
values = get_property_values(objectHandle, propertyName);
color = defaultColor;
for i = 1:numel(values)
    if isnumeric(values{i}) && isequal(size(values{i}), [1, 3])
        color = values{i};
        return;
    end
end
end

function value = first_numeric_scalar(objectHandle, propertyName, defaultValue)
values = get_property_values(objectHandle, propertyName);
value = defaultValue;
for i = 1:numel(values)
    if isnumeric(values{i}) && isscalar(values{i})
        value = values{i};
        return;
    end
end
end

function values = get_property_values(objectHandle, propertyName)
values = {};
for i = 1:numel(objectHandle)
    if isprop(objectHandle(i), propertyName)
        try
            values{end+1} = objectHandle(i).(propertyName); %#ok<AGROW>
        catch
        end
    end
end
end

function set_supported_property(objectHandle, propertyName, value)
for i = 1:numel(objectHandle)
    if isprop(objectHandle(i), propertyName)
        try
            objectHandle(i).(propertyName) = value;
        catch
        end
    end
end
end
