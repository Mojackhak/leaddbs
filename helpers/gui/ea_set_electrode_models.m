function ea_set_electrode_models(handles, models, sides, names)
% Synchronize the Custom configuration with the existing subject controls.
models = cellfun(@(model) strrep(model, 'St. Jude', 'Abbott'), models, 'UniformOutput', false);
setappdata(handles.leadfigure, 'elmodels', models);
if nargin < 4 || isempty(names)
    names = arrayfun(@(i) sprintf('Electrode %d', i), 1:numel(models), 'UniformOutput', false);
end
setappdata(handles.leadfigure, 'elnames', names);
buttons = sum(~cellfun('isempty', regexp(fieldnames(handles), '^side\d+$', 'match')));
setappdata(handles.leadfigure, 'extra_electrode_sides', sides(sides > buttons));
for side = 1:buttons
    set(handles.(['side', num2str(side)]), 'Value', ismember(side, sides));
end
if isempty(models)
    handles.electrode_model_popup.Enable = 'on';
else
    index = find(strcmp(handles.electrode_model_popup.String, models{1}), 1);
    set(handles.electrode_model_popup, 'Value', index);
end
mixed = numel(models) > 2 || numel(unique(models)) > 1;
current = handles.reconmethod.String{handles.reconmethod.Value};
if mixed
    handles.electrode_model_popup.Enable = 'off';
    allowed = {'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
    % Keep the converter's index valid while replacing the shorter list.
    handles.reconmethod.Value = 1;
    handles.reconmethod.String = allowed;
    selected = find(strcmp(allowed, current), 1);
    if isempty(selected)
        selected = 1;
    end
    handles.reconmethod.Value = selected;
else
    handles.electrode_model_popup.Enable = 'on';
    handles.reconmethod.String = {'TRAC/CORE (Horn 2015)', 'Refined TRAC/CORE', ...
        'PaCER (Husch 2017)', 'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
    handles.reconmethod.Value = find(strcmp(handles.reconmethod.String, current), 1);
end
end
