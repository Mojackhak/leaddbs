function reco = legui2reco(options, sourceFile, space)
% Import explicitly modeled LeGUI depth contacts into the standard reconstruction.
if nargin < 2
    sourceFile = fullfile(options.root, options.patientname, 'reconstruction', ...
        [options.patientname, '_electrodes.mat']);
end
if nargin < 3
    space = 'native';
end
source = load(sourceFile);
if strcmp(space, 'native')
    positions = source.ElecXYZRaw;
elseif strcmp(space, 'mni')
    positions = source.ElecXYZMNIRaw;
else
    error('LeadDBS:InvalidImportSpace', 'Import space must be native or mni.');
end
labels = source.ElecMapRaw(:, 1);
parts = regexp(labels, '^(.*?)(\d+)$', 'tokens', 'once');
if any(cellfun('isempty', parts)) || size(positions, 1) ~= numel(labels) || ...
        size(positions, 2) ~= 3 || any(~isfinite(positions(:)))
    error('LeadDBS:InvalidLeGUIContacts', 'LeGUI contacts require finite XYZ coordinates and labels ending in a contact number.');
end
names = cellfun(@(p) p{1}, parts, 'UniformOutput', false);
numbers = cellfun(@(p) str2double(p{2}), parts);
electrodes = unique(names(source.DepthElecRaw));
if isempty(electrodes)
    error('LeadDBS:InvalidLeGUIContacts', 'No depth electrodes were found.');
end
if isfile(options.subj.recon.recon)
    saved = load(options.subj.recon.recon, 'reco');
    reco = saved.reco;
else
    reco = struct;
end
if ~isfield(options, 'elmodels') || isempty(options.elmodels)
    if ~usejava('desktop')
        error('LeadDBS:ElectrodeModelsRequired', 'Configure the electrode models before importing LeGUI contacts.');
    end
    available = ea_resolve_elspec;
    for i = 1:numel(electrodes)
        selected = listdlg('PromptString', ['Model for ', electrodes{i}], ...
            'ListString', available, 'SelectionMode', 'single');
        if isempty(selected)
            return;
        end
        options.elmodels{i} = available{selected};
    end
    options.sides = 1:numel(electrodes);
end
coords = cell(1, numel(options.elmodels));
trajectory = cell(size(coords));
markers = repmat(struct('head', [], 'tail', [], 'x', [], 'y', []), size(coords));
indices = zeros(1, numel(electrodes));
aliases = {};
defaultNames = arrayfun(@(i) sprintf('Electrode %d',i), 1:numel(options.elmodels), 'UniformOutput', false);
if isfield(options, 'elnames') && ~isempty(options.elnames)
    options.elnames = reshape(options.elnames, 1, []);
end
if isfield(options, 'elnames') && ~isempty(options.elnames) && ~isequal(options.elnames, defaultNames)
    aliases = options.elnames;
elseif isfield(reco, 'props') && isfield(reco.props, 'elname') && ...
        ~isequal({reco.props.elname}, defaultNames)
    aliases = {reco.props.elname};
end
if isempty(aliases) && numel(electrodes) ~= numel(options.elmodels)
    error('LeadDBS:AmbiguousElectrodeImport', 'Configure electrode names for a partial LeGUI import.');
end
for i = 1:numel(electrodes)
    index = i;
    if ~isempty(aliases)
        index = find(strcmp(aliases, electrodes{i}));
        if numel(index) ~= 1
            error('LeadDBS:AmbiguousElectrodeImport', 'Electrode %s must match exactly one configured electrode name.', electrodes{i});
        end
    end
    if ~ismember(index, options.sides)
        continue;
    end
    indices(i) = index;
    rows = find(strcmp(names, electrodes{i}));
    [contactNumbers, order] = sort(numbers(rows));
    rows = rows(order);
    current = ea_resolve_elspec(options, index);
    if numel(rows) ~= current.elspec.numContacts || numel(unique(contactNumbers)) ~= numel(rows)
        error('LeadDBS:LeGUIModelMismatch', 'Electrode %s has %d contacts; model %s requires %d distinct contacts.', ...
            electrodes{i}, numel(rows), current.elmodel, current.elspec.numContacts);
    end
    coords{index} = positions(rows, :);
    model = load(fullfile(ea_getearoot, 'templates', 'electrode_models', current.elspec.matfname), 'electrode');
    template = model.electrode;
    if current.elspec.isdirected
        transform = [template.coords_mm, ones(numel(rows), 1)] \ coords{index};
        head = [template.head_position, 1] * transform;
        tail = [template.tail_position, 1] * transform;
        y = [template.y_position, 1] * transform;
        yvec = y - head;
    else
        transform = [template.coords_mm(:, 3), ones(numel(rows), 1)] \ coords{index};
        head = [template.head_position(3), 1] * transform;
        tail = [template.tail_position(3), 1] * transform;
        yvec = [];
    end
    if norm(tail-head) == 0
        error('LeadDBS:InvalidLeGUIContacts', 'Electrode %s has no defined trajectory.', electrodes{i});
    end
    if isempty(yvec)
        [xunitv, yunitv] = ea_calcxy(head, tail);
    else
        [xunitv, yunitv] = ea_calcxy(head, tail, yvec);
    end
    markers(index).head = head;
    markers(index).tail = tail;
    markers(index).x = head + xunitv * current.elspec.lead_diameter/2;
    markers(index).y = head + yunitv * current.elspec.lead_diameter/2;
    current.sides = index;
    [~, generated] = ea_resolvecoords(markers, current);
    trajectory{index} = generated{index};
    imported(index).elname = electrodes{i};
    imported(index).labels = labels(rows);
end
options.sides = indices(indices > 0);
if isempty(options.sides)
    error('LeadDBS:InvalidLeGUIContacts', 'The import contains no selected electrode indices.');
end
if isfield(options, 'elside')
    options = rmfield(options, 'elside');
end
options.native = strcmp(space, 'native');
if isfield(options, 'hybridsave')
    options = rmfield(options, 'hybridsave');
end
options.elmodel = options.elmodels{options.sides(1)};
ea_save_reconstruction(coords, trajectory, markers, options.elmodel, [], options);
saved = load(options.subj.recon.recon, 'reco');
reco = saved.reco;
for index = options.sides
    reco.props(index).elname = imported(index).elname;
    reco.props(index).labels = imported(index).labels;
    reco.props(index).manually_corrected = 1;
end
save(options.subj.recon.recon, 'reco');
if options.native
    ea_reconstruction2mni(options);
else
    ea_reconstruction2native(options);
end
reco = ea_recalc_angles(options.subj.recon.recon, options.sides);
end
