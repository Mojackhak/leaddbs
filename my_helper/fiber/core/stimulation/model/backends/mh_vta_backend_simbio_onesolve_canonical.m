function status = mh_vta_backend_simbio_onesolve_canonical(task, varargin)
% Execute one canonical voltage- or current-controlled SimBio solve.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('NativeAnchorPath', '', ...
    @(value) ischar(value) || isstring(value));
parser.parse(varargin{:});

actions = mh_vta_resolve_output_actions(task);
headmodelState = 'not_required';
options = struct();
sideIndex = NaN;
mesh = struct();
gradient = [];
activeNodeIndices = [];
anchorPath = '';

if actions.solve_native_efield
    [options, S, sideIndex, defaultAnchorPath] = build_context(task);
    anchorPath = mh_vta_resolve_native_anchor(defaultAnchorPath, ...
        parser.Results.NativeAnchorPath);
    stimLabel = ['canonical-', task.task_id(1:12)];
    [headmodelPath, headmodelState] = mh_vta_prepare_canonical_headmodel( ...
        S, sideIndex, options, stimLabel);
    hm = load(headmodelPath, ...
        'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions');
    mh_vta_validate_canonical_headmodel_units(hm.vol, hm.mesh);
    activeidx = ea_getactiveidx(S, sideIndex, hm.centroids, hm.mesh, ...
        hm.elfv, options.elspec, hm.meshregions);
    controlMode = lower(char(string(task.sources(1).control_mode)));
    boundary = mh_vta_assemble_boundary( ...
        task.sources, activeidx, controlMode);
    potential = mh_vta_fem_apply_dbs( ...
        hm.vol, boundary.node_indices, boundary.values_and_groups, ...
        boundary.unipolar, boundary.constvol, hm.wmboundary);
    gradient = mh_vta_fem_calc_gradient(hm.vol, potential);
    mesh = hm.mesh;
    activeNodeIndices = boundary.node_indices;
end

status = mh_vta_export_canonical_outputs(task, options, sideIndex, ...
    mesh, gradient, activeNodeIndices, anchorPath, headmodelState);
end

function [options, S, sideIndex, anchorPath] = build_context(task)
subjectDir = char(string(task.subject_dir));
options = ea_getptopts(subjectDir, struct());
options.root = [fileparts(subjectDir), filesep];
[~, options.patientname] = fileparts(subjectDir);
options.leadprod = 'dbs';
options.native = 1;
options.orignative = 1;
options.subj.recon.recon = char(string(task.reconstruction_path));
options.elmodel = char(string(task.electrode_model));
options = ea_resolve_elspec(options);
options = mh_vta_configure_canonical_options(options, task);

sideIndex = side_to_index(task.hemisphere);
if double(task.reconstruction_lead_id) ~= sideIndex
    error('mh_vta:ReconstructionLeadMismatch', ...
        'reconstruction_lead_id does not match hemisphere %s.', ...
        char(string(task.hemisphere)));
end
verify_reconstruction_model(task, sideIndex);
S = geometry_stimulation(task, options, sideIndex);
anchorPath = options.subj.preopAnat.(options.subj.AnchorModality).coreg;
end

function verify_reconstruction_model(task, sideIndex)
loaded = load(char(string(task.reconstruction_path)), 'reco');
if ~isfield(loaded, 'reco') || numel(loaded.reco.props) < sideIndex
    error('mh_vta:InvalidReconstruction', ...
        'Reconstruction does not contain lead %d.', sideIndex);
end
actual = char(string(loaded.reco.props(sideIndex).elmodel));
expected = char(string(task.electrode_model));
if ~strcmp(actual, expected)
    error('mh_vta:ElectrodeModelMismatch', ...
        'Reconstruction model %s does not match task model %s.', ...
        actual, expected);
end
end

function S = geometry_stimulation(task, options, sideIndex)
S = ea_initializeS(['canonical-', task.task_id(1:12)], options);
S.model = 'SimBio/FieldTrip (see Horn 2017)';
S.sources = 1;
sideCode = index_to_side(sideIndex);
sourceField = [sideCode, 's1'];
S.amplitude{sideIndex} = zeros(1, 4);
S.amplitude{sideIndex}(1) = max(double([task.sources.amplitude]));
S.(sourceField).amp = S.amplitude{sideIndex}(1);
S.(sourceField).va = 1;
S.(sourceField).case.perc = 0;
S.(sourceField).case.pol = 0;
for contactIndex = 1:S.numContacts
    contactField = ['k', num2str(contactIndex)];
    S.(sourceField).(contactField).perc = 0;
    S.(sourceField).(contactField).pol = 0;
end
contacts = [task.sources.contacts];
for index = 1:numel(contacts)
    if ischar(contacts(index).contact) || isstring(contacts(index).contact)
        S.(sourceField).case.perc = 100;
        S.(sourceField).case.pol = polarity_code(contacts(index).polarity);
        continue;
    end
    contactField = ['k', num2str(contacts(index).contact)];
    S.(sourceField).(contactField).perc = 100;
    S.(sourceField).(contactField).pol = polarity_code(contacts(index).polarity);
end
S = ea_activecontacts(S);
end

function sideIndex = side_to_index(side)
if strcmpi(char(string(side)), 'R')
    sideIndex = 1;
else
    sideIndex = 2;
end
end

function side = index_to_side(sideIndex)
if sideIndex == 1
    side = 'R';
else
    side = 'L';
end
end

function code = polarity_code(polarity)
if strcmpi(char(string(polarity)), 'cathode')
    code = 1;
else
    code = 2;
end
end
