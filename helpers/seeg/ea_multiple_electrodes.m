function sel = ea_multiple_electrodes(handles, bids)
% Configure indexed electrode models before or after initial localization.
subject = getappdata(handles.leadfigure, 'subjId');
if numel(subject) ~= 1
    error('LeadDBS:ElectrodeSetupSubject', 'Select exactly one subject for electrode setup.');
end
options = ea_handles2options(handles);
models = ea_resolve_elspec;
recon = bids.getRecon(subject{1});
names = {};
if isfield(options, 'elnames')
    names = options.elnames;
end
if isfile(recon.recon)
    saved = load(recon.recon, 'reco');
    if ~isfield(options, 'elmodels')
        options.elmodels = {saved.reco.props.elmodel};
    end
    if isfield(saved.reco.props, 'elname')
        for i = 1:numel(saved.reco.props)
            if (i > numel(names) || isempty(names{i}) || strcmp(names{i}, sprintf('Electrode %d', i))) && ...
                    ~isempty(saved.reco.props(i).elname)
                names{i} = saved.reco.props(i).elname;
            end
        end
    end
end
if ~isfield(options, 'elmodels') || isempty(options.elmodels)
    options.elmodels = repmat({options.elmodel}, 1, max([2, options.sides]));
end
sel = struct('count', [], 'models', {{}}, 'sameForAll', false, 'canceled', true);
dialog = figure('Name', 'Electrode Setup', 'NumberTitle', 'off', 'MenuBar', 'none', ...
    'ToolBar', 'none', 'Position', [200, 200, 720, 500], 'Tag', 'electrode_setup');
uicontrol(dialog, 'Style', 'text', 'String', 'Number of electrodes:', ...
    'Position', [20, 455, 150, 24]);
count = uicontrol(dialog, 'Style', 'edit', 'String', num2str(numel(options.elmodels)), ...
    'Position', [175, 455, 80, 26], 'Callback', @resizeTable, 'Tag', 'electrode_count');
data = cell(numel(options.elmodels), 3);
for i = 1:size(data, 1)
    data(i, :) = {ismember(i, options.sides), sprintf('Electrode %d', i), options.elmodels{i}};
    if i <= numel(names) && ~isempty(names{i})
        data{i, 2} = names{i};
    end
end
list = uitable(dialog, 'Data', data, 'ColumnName', {'Process', 'Electrode', 'Model'}, ...
    'ColumnFormat', {'logical', 'char', models'}, 'ColumnEditable', [true, true, true], ...
    'ColumnWidth', {65, 150, 420}, 'Position', [20, 70, 680, 370], 'Tag', 'electrode_models');
uicontrol(dialog, 'Style', 'pushbutton', 'String', 'Apply', 'Position', [500, 20, 90, 30], ...
    'Callback', @apply, 'Tag', 'electrode_apply');
uicontrol(dialog, 'Style', 'pushbutton', 'String', 'Cancel', 'Position', [610, 20, 90, 30], ...
    'Callback', @(~, ~) delete(dialog));
waitfor(dialog);

    function resizeTable(~, ~)
        n = str2double(count.String);
        if ~isfinite(n) || n < 1 || n ~= fix(n)
            errordlg('The electrode count must be a positive integer.', 'Electrode Setup');
            return;
        end
        previous = list.Data;
        updated = cell(n, 3);
        for row = 1:n
            if row <= size(previous, 1)
                updated(row, :) = previous(row, :);
            else
                updated(row, :) = {true, sprintf('Electrode %d', row), options.elmodel};
            end
        end
        list.Data = updated;
    end

    function apply(~, ~)
        selected = list.Data;
        chosenModels = selected(:, 3)';
        chosenNames = strtrim(selected(:, 2)');
        if any(cellfun('isempty', chosenNames)) || numel(unique(chosenNames)) ~= numel(chosenNames)
            errordlg('Every electrode requires a distinct nonempty name.', 'Electrode Setup');
            return;
        end
        if any(~ismember(chosenModels, models))
            errordlg('Choose an available model for every electrode.', 'Electrode Setup');
            return;
        end
        sides = find(cell2mat(selected(:, 1)))';
        if isempty(sides)
            errordlg('Select at least one electrode to process.', 'Electrode Setup');
            return;
        end
        if isfile(recon.recon) && size(selected, 1) < numel(saved.reco.props)
            errordlg('Existing reconstructed electrode indices must be retained.', 'Electrode Setup');
            return;
        end
        ea_set_electrode_models(handles, chosenModels, sides, chosenNames);
        ea_storeui(handles);
        sel.count = numel(chosenModels);
        sel.models = chosenModels;
        sel.sameForAll = numel(unique(chosenModels)) == 1;
        sel.canceled = false;
        delete(dialog);
    end
end
