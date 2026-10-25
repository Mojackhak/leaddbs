function elstruct = ea_load_group_reconstruction(options, elstruct, model)
% Load indexed display geometry while retaining the group's subject metadata.
% An empty model selects the saved per-electrode models; an override is display-only.
if isfield(options, 'sides')
    options = rmfield(options, 'sides');
end
[coords, trajectory, markers, firstModel, ~, acpc, reco] = ea_load_reconstruction(options);
models = {reco.props.elmodel};
labels = cell(size(coords));
if isfield(reco.props, 'labels')
    labels = {reco.props.labels};
end
if ~isempty(model)
    options.elmodels = repmat({model}, 1, numel(markers));
    options.elmodel = model;
    options.sides = find(~arrayfun(@(m) isempty(m.head), markers));
    [coords, trajectory, markers] = ea_resolvecoords(markers, options, 0);
    changed = ~strcmp(strrep(models, 'St. Jude', 'Abbott'), model);
    labels(changed) = {[]};
    models = options.elmodels;
    firstModel = model;
end
elstruct.coords_mm = coords;
elstruct.trajectory = trajectory;
elstruct.markers = markers;
elstruct.coords_acpc = acpc;
elstruct.elmodel = firstModel;
elstruct.elmodels = models;
elstruct.labels = labels;
elstruct.name = options.patientname;
end
