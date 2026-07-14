function headmodel = mh_vta_load_canonical_headmodel(headmodelPath)
% Load and immediately validate one canonical FEM headmodel.

headmodelPath = char(string(headmodelPath));
if ~isfile(headmodelPath)
    error('mh_vta_load_canonical_headmodel:MissingInput', ...
        'Canonical headmodel does not exist: %s', headmodelPath);
end
required = {'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions'};
headmodel = load(headmodelPath, required{:});
if ~all(isfield(headmodel, required))
    error('mh_vta_load_canonical_headmodel:MissingVariables', ...
        'Canonical headmodel is missing required FEM variables: %s', ...
        headmodelPath);
end
mh_vta_validate_canonical_headmodel_units( ...
    headmodel.vol, headmodel.mesh);
end
