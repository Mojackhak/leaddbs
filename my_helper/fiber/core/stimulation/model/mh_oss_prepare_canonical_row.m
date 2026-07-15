function manifest = mh_oss_prepare_canonical_row(requestJsonPath, outputManifestPath)
% Prepare ten right-canonical OSS-DBSv2 parameter files from one JSON row.
%
% REQUESTJSONPATH is an absolute path to a strict JSON object containing
% explicit subject, reconstruction, transform, template segmentation,
% stimulation, connectome, source, environment, and diameter inputs.
% OUTPUTMANIFESTPATH is the absolute path of the JSON manifest to create.
%
% The function uses template-space Lead-DBS reconstruction geometry, maps a
% left lead with the explicitly supplied transform when required, constructs
% one simultaneous right-canonical boundary, and saves ten v7.3 MAT files.
% It returns the same manifest object written to OUTPUTMANIFESTPATH.

if nargin ~= 2
    error('mh_oss:InvalidRequest', ...
        'Expected requestJsonPath and outputManifestPath.');
end
requestJsonPath = existing_file(requestJsonPath, 'requestJsonPath');
outputManifestPath = absolute_path(outputManifestPath, ...
    'outputManifestPath', true);
if isfile(outputManifestPath) || isfolder(outputManifestPath)
    error('mh_oss:OutputExists', ...
        'Refusing to overwrite outputManifestPath: %s', outputManifestPath);
end
if strcmp(requestJsonPath, outputManifestPath)
    error('mh_oss:InvalidRequest', ...
        'The request and output manifest paths must differ.');
end

try
    request = jsondecode(fileread(requestJsonPath));
catch ME
    wrapped = MException('mh_oss:InvalidJson', ...
        'Could not read strict JSON request: %s', requestJsonPath);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end
if ~isstruct(request) || ~isscalar(request)
    error('mh_oss:InvalidRequest', ...
        'The request JSON root must be one object.');
end
exact_fields(request, {'schema_version', 'subject_dir', ...
    'reconstruction_path', 'transform_path', 'template_segmask_path', ...
    'stimulation_root', 'connectome_dir', 'connectome_label', ...
    'electrode_model', 'reconstruction_lead_id', 'contact_count', ...
    'side', 'frequency_hz', 'pulse_width_us', 'control_mode', ...
    'delivery_mode', 'environment_path', 'diameters_um', 'sources'}, ...
    'request');
if ~strcmp(text_scalar(request.schema_version, 'schema_version'), ...
        'dual_frequency_oss_matlab_request_v1')
    error('mh_oss:InvalidRequest', ...
        'Unsupported request schema_version.');
end

subjectDir = existing_directory(request.subject_dir, 'subject_dir');
reconstructionPath = existing_file(request.reconstruction_path, ...
    'reconstruction_path');
templateSegmaskPath = existing_file(request.template_segmask_path, ...
    'template_segmask_path');
stimulationRoot = existing_directory(request.stimulation_root, ...
    'stimulation_root');
connectomeDir = existing_directory(request.connectome_dir, 'connectome_dir');
environmentPath = existing_directory(request.environment_path, ...
    'environment_path');
if ~isfile(fullfile(connectomeDir, 'data1.mat'))
    error('mh_oss:InvalidRequest', ...
        'connectome_dir must contain data1.mat: %s', connectomeDir);
end
validate_environment(environmentPath);

connectomeLabel = text_scalar(request.connectome_label, 'connectome_label');
electrodeModel = text_scalar(request.electrode_model, 'electrode_model');
side = upper(text_scalar(request.side, 'side'));
if ~ismember(side, {'L', 'R'})
    error('mh_oss:InvalidRequest', 'side must be L or R.');
end
leadId = positive_integer(request.reconstruction_lead_id, ...
    'reconstruction_lead_id');
if ~ismember(leadId, [1, 2]) || ...
        (strcmp(side, 'R') && leadId ~= 1) || ...
        (strcmp(side, 'L') && leadId ~= 2)
    error('mh_oss:InvalidRequest', ...
        'side and reconstruction_lead_id are inconsistent.');
end
contactCount = positive_integer(request.contact_count, 'contact_count');
frequencyHz = positive_scalar(request.frequency_hz, 'frequency_hz');
pulseWidthUs = positive_scalar(request.pulse_width_us, 'pulse_width_us');
controlMode = lower(text_scalar(request.control_mode, 'control_mode'));
if ~ismember(controlMode, {'voltage', 'current'})
    error('mh_oss:InvalidRequest', ...
        'control_mode must be voltage or current.');
end
deliveryMode = lower(text_scalar(request.delivery_mode, 'delivery_mode'));
if ~ismember(deliveryMode, {'continuous', 'alternating'})
    error('mh_oss:InvalidRequest', ...
        'delivery_mode must be continuous or alternating.');
end

transformPath = optional_text_scalar(request.transform_path, 'transform_path');
if strcmp(side, 'L')
    transformPath = existing_file(transformPath, 'transform_path');
elseif ~isempty(transformPath)
    error('mh_oss:InvalidRequest', ...
        'Right rows must not declare transform_path.');
end

diametersUm = linspace(1, 4, 10);
requestedDiameters = numeric_vector(request.diameters_um, 'diameters_um');
if numel(requestedDiameters) ~= 10 || ...
        any(abs(requestedDiameters(:)' - diametersUm) > 1e-12)
    error('mh_oss:InvalidRequest', ...
        'diameters_um must be exactly linspace(1, 4, 10).');
end

[segmaskPath, parameterFiles] = output_paths( ...
    stimulationRoot, templateSegmaskPath);
preflight_outputs(segmaskPath, parameterFiles);

options = ea_resolve_elspec(struct('elmodel', electrodeModel));
if ~isfield(options, 'elspec') || ...
        ~isfield(options.elspec, 'numContacts') || ...
        double(options.elspec.numContacts) ~= contactCount
    error('mh_oss:ElectrodeModelMismatch', ...
        ['electrode_model resolves to a contact count different from ' ...
         'contact_count.']);
end
settings = load_reconstruction_geometry(reconstructionPath, leadId, ...
    electrodeModel, contactCount);
validate_directional_geometry(settings, options.elspec);

if strcmp(side, 'L')
    settings = mh_oss_map_left_coordinates_to_right( ...
        settings, transformPath);
end
contactLocations = right_canonical_geometry(settings, contactCount);
[Phi, currentControl, caseGrounding, stimCenter, activeContacts] = ...
    mh_oss_assemble_boundary(request, contactLocations);

settings = configure_serialized_settings(settings, ...
    subjectDir, electrodeModel, segmaskPath, connectomeDir, ...
    connectomeLabel, Phi, currentControl, caseGrounding, stimCenter, ...
    pulseWidthUs, diametersUm(1));

parameterRoot = fileparts(parameterFiles{1});
parameterRoot = fileparts(parameterRoot);
create_directory(parameterRoot, 'parameter sample root');
[copied, message] = copyfile(templateSegmaskPath, segmaskPath);
if ~copied
    error('mh_oss:SegmaskCopyFailed', ...
        'Could not copy template segmentation: %s', message);
end
for sampleIndex = 1:numel(parameterFiles)
    sampleDirectory = fileparts(parameterFiles{sampleIndex});
    create_directory(sampleDirectory, sprintf('sample %d directory', sampleIndex));
    settings.fiberDiameter = diametersUm(sampleIndex);
    settings.axonLength = 10.0;
    save(parameterFiles{sampleIndex}, 'settings', '-v7.3');
    if ~isfile(parameterFiles{sampleIndex})
        error('mh_oss:ParameterSaveFailed', ...
            'Parameter sample %d was not created.', sampleIndex);
    end
end

activeLocations = contactLocations(activeContacts, :);
manifest = struct();
manifest.schema_version = 'dual_frequency_oss_matlab_manifest_v1';
manifest.parameter_files = parameterFiles(:);
manifest.stimulation_folder = stimulationRoot;
manifest.active_contact_locations_mm = num2cell(activeLocations, 2);
manifest.frequency_hz = frequencyHz;
manifest.pulse_width_us = pulseWidthUs;
manifest.control_mode = controlMode;
manifest.segmask_path = segmaskPath;
write_json(outputManifestPath, manifest);
end

function settings = configure_serialized_settings(settings, ...
        subjectDir, electrodeModel, segmaskPath, connectomeDir, ...
        connectomeLabel, Phi, currentControl, caseGrounding, stimCenter, ...
        pulseWidthUs, fiberDiameter)
contactCount = numel(Phi);
settings.Patient_folder = subjectDir;
settings.Electrode_type = electrodeModel;
settings.Estimate_In_Template = true;
settings.butenko_segmAlg = 'SPM';
settings.GM_index = 1;
settings.WM_index = 2;
settings.CSF_index = 3;
settings.default_material = 'GM';
settings.MRI_data_name = segmaskPath;
settings.DTI_data_name = 'no dti';
settings.cond_model = 'ColeCole4';
settings.butenko_tensorData = 0;
settings.neuronModel = 'McNeal1976';
settings.signalType = 'Train';
settings.biphasic = 0;
settings.removeElectrode = 1;
settings.AdaptiveRef = 0;
settings.encapsulationType = 'None';
settings.adaptive_threshold = 0;
settings.calcAxonActivation = 1;
settings.exportVAT = 0;
settings.prob_PAM = 1;
settings.N_samples = 10;
settings.stimSetMode = 0;
settings.optimizer = 0;
settings.trainANN = 0;
settings.outOfCore = 0;
settings.use_wsl = false;
settings.use_binaries = false;
settings.reuse_warped_connectome = 0;
settings.connectome = connectomeLabel;
settings.connectomePath = connectomeDir;
settings.connectomePathMNI = connectomeDir;
settings.connectomeActivations = fullfile(connectomeDir, 'PAM');
settings.connectomeActivationsMNI = fullfile(connectomeDir, 'PAM');
settings.pathwayParameterFile = 'Allocated_axons_parameters.json';
settings.axonLength = 10.0;
settings.fiberDiameter = fiberDiameter;
settings.multisource = 0;
settings.Phi_vector = nan(2, contactCount);
settings.Phi_vector(1, :) = Phi;
settings.Phi_vector_max = nan(2, contactCount);
active = ~isnan(Phi);
settings.Phi_vector_max(1, active) = abs(Phi(active));
settings.current_control = [currentControl; nan];
settings.Case_grounding = [caseGrounding; nan];
settings.stim_center = nan(2, 3);
settings.stim_center(1, :) = stimCenter;
settings.pulseWidth = [pulseWidthUs; nan];
settings.Activation_threshold_VTA = [-1; -1];
settings.interactiveMode = 0;
end

function settings = load_reconstruction_geometry(reconstructionPath, ...
        leadId, electrodeModel, contactCount)
try
    loaded = load(reconstructionPath, 'reco');
catch ME
    wrapped = MException('mh_oss:ReconstructionFailed', ...
        'Could not load the request-supplied reconstruction MAT: %s', ...
        reconstructionPath);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end
if ~isfield(loaded, 'reco') || ~isstruct(loaded.reco) || ...
        ~isscalar(loaded.reco)
    error('mh_oss:ReconstructionFailed', ...
        'The request-supplied MAT must contain one reco struct.');
end
reco = loaded.reco;
if ~isfield(reco, 'mni') || ~isstruct(reco.mni) || ...
        ~isscalar(reco.mni) || ~isfield(reco.mni, 'coords_mm') || ...
        ~iscell(reco.mni.coords_mm) || numel(reco.mni.coords_mm) < leadId
    error('mh_oss:ReconstructionFailed', ...
        'The requested reconstruction lead has no stored MNI coordinates.');
end
if ~isfield(reco, 'props') || ~isstruct(reco.props) || ...
        numel(reco.props) < leadId || ...
        ~isfield(reco.props(leadId), 'elmodel')
    error('mh_oss:ReconstructionFailed', ...
        'The requested reconstruction lead has no electrode-model metadata.');
end
reconstructedModel = normalize_electrode_model( ...
    text_scalar(reco.props(leadId).elmodel, 'reco.props.elmodel'));
if ~strcmp(reconstructedModel, normalize_electrode_model(electrodeModel))
    error('mh_oss:ElectrodeModelMismatch', ...
        ['electrode_model differs from the exact request-supplied ' ...
         'reconstruction lead.']);
end

contacts = coordinate_matrix(reco.mni.coords_mm{leadId}, ...
    sprintf('reco.mni.coords_mm{%d}', leadId));
if ~isequal(size(contacts), [contactCount, 3])
    error('mh_oss:ElectrodeModelMismatch', ...
        'The exact reconstruction lead does not contain contact_count contacts.');
end
if ~isfield(reco.mni, 'markers') || ~isstruct(reco.mni.markers) || ...
        numel(reco.mni.markers) < leadId
    error('mh_oss:ReconstructionFailed', ...
        'The requested reconstruction lead has no stored MNI markers.');
end
markers = reco.mni.markers(leadId);
head = marker_coordinate(markers, 'head', leadId);
yMarker = marker_coordinate(markers, 'y', leadId);
if contactCount == 1
    second = marker_coordinate(markers, 'tail', leadId);
elseif contains(electrodeModel, 'DIXI D08') || ...
        contains(electrodeModel, 'PMT 2102')
    if contactCount < 4
        error('mh_oss:ElectrodeModelMismatch', ...
            'DIXI/PMT reconstruction requires at least four contacts.');
    end
    second = contacts(4, :);
else
    second = contacts(end, :);
end

% OSS evaluates every producer row in the right-electrode slot. Duplicate the
% selected lead only to satisfy the two-row MAT interface; the second row is
% never stimulated. Left rows are subsequently mapped into the right slot.
settings = struct();
settings.contactLocation = {contacts, contacts};
settings.Implantation_coordinate = repmat(contacts(1, :), 2, 1);
settings.Second_coordinate = repmat(second, 2, 1);
settings.headMNI = repmat(head, 2, 1);
settings.yMarkerMNI = repmat(yMarker, 2, 1);
settings.headNative = nan(2, 3);
settings.yMarkerNative = nan(2, 3);
end

function validate_directional_geometry(settings, electrodeSpecification)
if ~isfield(electrodeSpecification, 'isdirected') || ...
        ~isscalar(electrodeSpecification.isdirected) || ...
        ~logical(electrodeSpecification.isdirected)
    return
end
implantation = settings.Implantation_coordinate(1, :);
second = settings.Second_coordinate(1, :);
if all(implantation(2:3) == second(2:3))
    error('mh_oss:UnsupportedDirectionalGeometry', ...
        ['Implantations perfectly along the x axis are not supported for ' ...
         'directional leads.']);
end
end

function value = marker_coordinate(markers, name, leadId)
if ~isfield(markers, name)
    error('mh_oss:ReconstructionFailed', ...
        'Reconstruction lead %d is missing MNI marker %s.', leadId, name);
end
value = coordinate_matrix(markers.(name), ...
    sprintf('reco.mni.markers(%d).%s', leadId, name));
if ~isequal(size(value), [1, 3])
    error('mh_oss:ReconstructionFailed', ...
        'Reconstruction lead %d marker %s must be 1-by-3.', leadId, name);
end
end

function value = normalize_electrode_model(raw)
value = strrep(strtrim(raw), 'St. Jude', 'Abbott');
end

function contactLocations = right_canonical_geometry(settings, contactCount)
if ~isfield(settings, 'contactLocation') || ...
        ~iscell(settings.contactLocation) || isempty(settings.contactLocation)
    error('mh_oss:InvalidGeometry', ...
        'Reconstruction settings are missing right contact geometry.');
end
contactLocations = coordinate_matrix(settings.contactLocation{1}, ...
    'settings.contactLocation{1}');
if ~isequal(size(contactLocations), [contactCount, 3])
    error('mh_oss:InvalidGeometry', ...
        'Right-canonical contact geometry must be contact_count-by-3.');
end
for name = {'Implantation_coordinate', 'Second_coordinate', ...
        'headMNI', 'yMarkerMNI'}
    fieldName = name{1};
    if ~isfield(settings, fieldName)
        error('mh_oss:InvalidGeometry', ...
            'Reconstruction settings are missing %s.', fieldName);
    end
    geometry = coordinate_matrix(settings.(fieldName), ...
        ['settings.' fieldName]);
    if size(geometry, 1) < 1
        error('mh_oss:InvalidGeometry', ...
            'settings.%s has no right-canonical row.', fieldName);
    end
end
end

function [segmaskPath, parameterFiles] = output_paths( ...
        stimulationRoot, templateSegmaskPath)
lowerPath = lower(templateSegmaskPath);
if endsWith(lowerPath, '.nii.gz')
    segmaskName = 'segmask.nii.gz';
elseif endsWith(lowerPath, '.nii')
    segmaskName = 'segmask.nii';
else
    error('mh_oss:InvalidRequest', ...
        'template_segmask_path must be a .nii or .nii.gz file.');
end
segmaskPath = fullfile(stimulationRoot, segmaskName);
sampleRoot = fullfile(stimulationRoot, 'parameter_samples');
parameterFiles = cell(10, 1);
for sampleIndex = 1:10
    parameterFiles{sampleIndex} = fullfile(sampleRoot, ...
        sprintf('sample_%02d', sampleIndex), 'oss-dbs_parameters.mat');
end
end

function preflight_outputs(segmaskPath, parameterFiles)
sampleRoot = fileparts(fileparts(parameterFiles{1}));
if isfile(segmaskPath) || isfolder(segmaskPath)
    error('mh_oss:OutputExists', ...
        'Refusing to overwrite segmentation output: %s', segmaskPath);
end
if isfile(sampleRoot) || isfolder(sampleRoot)
    error('mh_oss:OutputExists', ...
        'Refusing to reuse parameter sample root: %s', sampleRoot);
end
if numel(unique(parameterFiles)) ~= 10
    error('mh_oss:InternalInvariant', ...
        'Parameter output paths are not unique.');
end
end

function validate_environment(environmentPath)
if ispc
    pythonPath = fullfile(environmentPath, 'python.exe');
else
    pythonPath = fullfile(environmentPath, 'bin', 'python');
end
if ~isfile(pythonPath)
    error('mh_oss:InvalidRequest', ...
        'environment_path does not contain its private Python executable: %s', ...
        pythonPath);
end
end

function create_directory(path, label)
if isfile(path)
    error('mh_oss:OutputExists', '%s is an existing file: %s', label, path);
end
if isfolder(path)
    return;
end
[created, message] = mkdir(path);
if ~created
    error('mh_oss:OutputCreateFailed', ...
        'Could not create %s (%s): %s', label, path, message);
end
end

function write_json(path, value)
parent = fileparts(path);
if isempty(parent)
    error('mh_oss:InvalidRequest', ...
        'outputManifestPath must have an absolute parent directory.');
end
create_directory(parent, 'manifest parent directory');
if isfile(path) || isfolder(path)
    error('mh_oss:OutputExists', ...
        'Refusing to overwrite output manifest: %s', path);
end
encoded = jsonencode(value, 'PrettyPrint', true);
[fileId, message] = fopen(path, 'w', 'n', 'UTF-8');
if fileId < 0
    error('mh_oss:ManifestWriteFailed', ...
        'Could not open output manifest (%s): %s', path, message);
end
cleanup = onCleanup(@() fclose(fileId));
count = fprintf(fileId, '%s\n', encoded);
if count < numel(encoded) + 1
    error('mh_oss:ManifestWriteFailed', ...
        'Could not write the complete output manifest: %s', path);
end
clear cleanup;
end

function exact_fields(value, expected, label)
actual = sort(fieldnames(value));
expected = sort(expected(:));
if ~isequal(actual, expected)
    missing = setdiff(expected, actual);
    extra = setdiff(actual, expected);
    error('mh_oss:InvalidRequest', ...
        '%s fields differ; missing=%s extra=%s.', label, ...
        strjoin(missing, ','), strjoin(extra, ','));
end
end

function path = existing_file(raw, label)
path = absolute_path(raw, label, true);
if ~isfile(path)
    error('mh_oss:InvalidRequest', '%s does not exist: %s', label, path);
end
end

function path = existing_directory(raw, label)
path = absolute_path(raw, label, true);
if ~isfolder(path)
    error('mh_oss:InvalidRequest', ...
        '%s is not an existing directory: %s', label, path);
end
end

function path = absolute_path(raw, label, requireNonempty)
if nargin < 3
    requireNonempty = true;
end
if ischar(raw) && isrow(raw)
    path = raw;
elseif isstring(raw) && isscalar(raw) && ~ismissing(raw)
    path = char(raw);
else
    error('mh_oss:InvalidRequest', '%s must be a text scalar.', label);
end
if requireNonempty && isempty(path)
    error('mh_oss:InvalidRequest', '%s must be nonempty.', label);
end
if ~isempty(path) && ~is_absolute_path(path)
    error('mh_oss:InvalidRequest', '%s must be an absolute path.', label);
end
end

function value = text_scalar(raw, label)
value = optional_text_scalar(raw, label);
if isempty(value)
    error('mh_oss:InvalidRequest', '%s must be nonempty.', label);
end
end

function value = optional_text_scalar(raw, label)
if ischar(raw) && (isrow(raw) || isempty(raw))
    value = strtrim(raw);
elseif isstring(raw) && isscalar(raw) && ~ismissing(raw)
    value = strtrim(char(raw));
else
    error('mh_oss:InvalidRequest', '%s must be a text scalar.', label);
end
end

function value = positive_integer(raw, label)
value = positive_scalar(raw, label);
if value ~= fix(value)
    error('mh_oss:InvalidRequest', '%s must be an integer.', label);
end
end

function value = positive_scalar(raw, label)
if ~(isnumeric(raw) || islogical(raw)) || ~isscalar(raw)
    error('mh_oss:InvalidRequest', '%s must be a numeric scalar.', label);
end
value = double(raw);
if ~isfinite(value) || value <= 0
    error('mh_oss:InvalidRequest', ...
        '%s must be positive and finite.', label);
end
end

function value = numeric_vector(raw, label)
if ~isnumeric(raw) || ~isvector(raw) || isempty(raw)
    error('mh_oss:InvalidRequest', '%s must be a numeric vector.', label);
end
value = double(raw(:));
if any(~isfinite(value))
    error('mh_oss:InvalidRequest', ...
        '%s must contain only finite values.', label);
end
end

function value = coordinate_matrix(raw, label)
if ~isnumeric(raw) || ~ismatrix(raw) || size(raw, 2) ~= 3 || isempty(raw)
    error('mh_oss:InvalidGeometry', ...
        '%s must be a nonempty N-by-3 matrix.', label);
end
value = double(raw);
if any(~isfinite(value), 'all')
    error('mh_oss:InvalidGeometry', ...
        '%s must contain only finite coordinates.', label);
end
end

function tf = is_absolute_path(path)
if ispc
    tf = ~isempty(regexp(path, '^[A-Za-z]:[\\/]', 'once')) || ...
        startsWith(path, '\\');
else
    tf = startsWith(path, filesep);
end
end
