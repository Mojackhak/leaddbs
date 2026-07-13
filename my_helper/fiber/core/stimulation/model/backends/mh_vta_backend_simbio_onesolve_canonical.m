function status = mh_vta_backend_simbio_onesolve_canonical(task)
% Execute one canonical voltage- or current-controlled SimBio solve.

nativeLeaf = char(string(task.output_leaves.native));
mniLeaf = char(string(task.output_leaves.MNI152NLin2009bAsym));
nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
mniEfield = fullfile(mniLeaf, 'efield.nii.gz');
actions = mh_vta_resolve_output_actions(task);
headmodelState = 'not_required';

if actions.solve_native_efield
    [options, S, sideIndex, anchorPath] = build_context(task);
    stimLabel = ['canonical-', task.task_id(1:12)];
    [headmodelPath, headmodelState] = mh_vta_prepare_canonical_headmodel( ...
        S, sideIndex, options, stimLabel);
    hm = load(headmodelPath, ...
        'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions');
    activeidx = ea_getactiveidx(S, sideIndex, hm.centroids, hm.mesh, ...
        hm.elfv, options.elspec, hm.meshregions);
    controlMode = lower(char(string(task.sources(1).control_mode)));
    boundary = mh_vta_assemble_onesolve_boundary( ...
        task.sources, activeidx, controlMode);
    potential = mh_vta_fem_apply_dbs( ...
        hm.vol, boundary.node_indices, boundary.values_and_groups, ...
        boundary.unipolar, boundary.constvol, hm.wmboundary);
    gradient = mh_vta_fem_calc_gradient(hm.vol, potential);
    gradient = fill_electrode_tetrahedra(hm.mesh, gradient, ...
        boundary.node_indices);
    fieldValues = sqrt(sum(double(gradient).^2, 2));
    meshPointsMm = tetrahedron_midpoints_mm(hm.mesh);
    mh_vta_publish_atomic(nativeEfield, @(temporaryPath) ...
        mh_vta_export_common_grid(meshPointsMm, fieldValues, ...
            anchorPath, temporaryPath));
end

write_requested_thresholds(nativeEfield, nativeLeaf, ...
    task.model.thresholds_v_per_m, actions.native_threshold_names);

if actions.transform_mni_efield
    require_file(nativeEfield, 'native E-field');
    [transformOptions, mniReference] = transform_context(task);
    mh_vta_publish_atomic(mniEfield, @(temporaryPath) ...
        mh_vta_transform_efield_to_mni(nativeEfield, transformOptions, ...
            mniReference, temporaryPath));
end

write_requested_thresholds(mniEfield, mniLeaf, ...
    task.model.thresholds_v_per_m, actions.mni_threshold_names);

status = struct( ...
    'task_id', task.task_id, ...
    'execution', 'solve', ...
    'headmodel_state', headmodelState, ...
    'native_efield', nativeEfield, ...
    'mni_efield', mniEfield);
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
options.atlasset = char(string(task.model.atlas_set));
options.prefs.vat.gm = 'atlas';
options.prefs.machine.vatsettings.horn_cgm = ...
    double(task.model.gray_matter_s_per_m);
options.prefs.machine.vatsettings.horn_cwm = ...
    double(task.model.white_matter_s_per_m);
options.prefs.machine.vatsettings.horn_useatlas = 1;
options.prefs.machine.vatsettings.horn_atlasset = ...
    char(string(task.model.atlas_set));
options.prefs.machine.vatsettings.horn_removeElectrode = 1;

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

function [options, mniReference] = transform_context(task)
options = ea_getptopts(char(string(task.subject_dir)), struct());
options.subj.recon.recon = char(string(task.reconstruction_path));
mniReference = fullfile(ea_space(options), 't1.nii');
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

function points = tetrahedron_midpoints_mm(mesh)
points = mean(cat(3, ...
    mesh.pnt(mesh.tet(:, 1), :), ...
    mesh.pnt(mesh.tet(:, 2), :), ...
    mesh.pnt(mesh.tet(:, 3), :), ...
    mesh.pnt(mesh.tet(:, 4), :)), 3);
if isfield(mesh, 'unit') && strcmpi(mesh.unit, 'm')
    points = points * 1000;
end
end

function gradient = fill_electrode_tetrahedra(mesh, gradient, nodeIndices)
electrodeTetrahedra = sum(ismember(mesh.tet, unique(nodeIndices)), 2) == 4;
if ~any(electrodeTetrahedra)
    return;
end
magnitudes = sqrt(sum(double(gradient).^2, 2));
finiteValues = sort(magnitudes(isfinite(magnitudes)), 'descend');
if isempty(finiteValues)
    return;
end
count = max(1, ceil(numel(finiteValues) * 0.001));
replacementMagnitude = mean(finiteValues(1:count));
gradient(electrodeTetrahedra, :) = 0;
gradient(electrodeTetrahedra, 1) = replacementMagnitude;
end

function write_requested_thresholds(efieldPath, leaf, thresholds, requestedNames)
if isempty(requestedNames)
    return;
end
require_file(efieldPath, 'threshold source E-field');
for threshold = double(thresholds(:)')
    token = strrep(sprintf('%.2f', threshold / 1000), '.', 'p');
    name = "vta_threshold-" + token + "Vpermm.nii.gz";
    if ~any(requestedNames == name)
        continue;
    end
    output = fullfile(leaf, char(name));
    mh_vta_publish_atomic(output, @(temporaryPath) ...
        mh_vta_threshold_efield(efieldPath, threshold, temporaryPath));
end
end

function require_file(path, label)
if ~isfile(path)
    error('mh_vta:MissingCanonicalDependency', ...
        'Missing %s: %s', label, path);
end
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
