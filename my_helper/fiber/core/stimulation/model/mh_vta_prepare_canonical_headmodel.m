function [headmodelPath, state, headmodel] = mh_vta_prepare_canonical_headmodel( ...
        S, sideIndex, options, stimulationLabel)
% Build or reuse a canonical native head model by fixed path.

validateattributes(sideIndex, {'numeric'}, {'scalar', 'integer', '>=', 1, '<=', 2}, ...
    mfilename, 'sideIndex');
if ~isstruct(options) || ~isfield(options, 'subj') || ...
        ~isfield(options.subj, 'subjDir') || ~isfield(options.subj, 'subjId')
    error('mh_vta_prepare_canonical_headmodel:InvalidOptions', ...
        'options.subj.subjDir and options.subj.subjId are required.');
end
subjectId = char(string(options.subj.subjId));
subjectId = regexprep(subjectId, '^sub-', '');
headmodelDir = fullfile(char(string(options.subj.subjDir)), 'headmodel', 'native');
headmodelPath = fullfile(headmodelDir, sprintf( ...
    'sub-%s_desc-headmodel%d.mat', subjectId, sideIndex));

if isfile(headmodelPath)
    required = {'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions'};
    try
        inventory = whos('-file', headmodelPath);
    catch ME
        wrapped = MException( ...
            'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel', ...
            'Existing canonical head model is unreadable: %s', headmodelPath);
        wrapped = addCause(wrapped, ME);
        throw(wrapped);
    end
    if ~all(ismember(required, {inventory.name}))
        error('mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel', ...
            'Existing canonical head model is missing required FEM variables: %s', ...
            headmodelPath);
    end
    try
        headmodel = mh_vta_load_canonical_headmodel(headmodelPath);
    catch ME
        wrapped = MException( ...
            'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel', ...
            ['Existing canonical head model is unreadable or violates ', ...
             'the coordinate-unit contract: %s'], headmodelPath);
        wrapped = addCause(wrapped, ME);
        throw(wrapped);
    end
    state = 'reused';
    return;
end

if ~isfolder(headmodelDir)
    mkdir(headmodelDir);
end
nativeOptions = options;
nativeOptions.native = 1;
nativeOptions.orignative = 1;
nativeOptions.subj.subjId = subjectId;
nativeOptions.mh_vta_headmodel_only = true;
mh_vta_run_horn_with_retry( ...
    S, sideIndex, nativeOptions, char(string(stimulationLabel)), headmodelPath);
if ~isfile(headmodelPath)
    error('mh_vta_prepare_canonical_headmodel:BuildFailed', ...
        'Head-model preparation did not create the canonical MAT file: %s', ...
        headmodelPath);
end

state = 'built';
headmodel = mh_vta_load_canonical_headmodel(headmodelPath);
end
