function tests = test_oss_prepare_canonical_row
% Verify project-neutral OSS row preparation without running FEM or OSS-DBS.
tests = functiontests(localfunctions);
end

function setupOnce(testCase)
testDirectory = fileparts(mfilename('fullpath'));
modelDirectory = fullfile(testDirectory, '..', 'core', ...
    'stimulation', 'model');
electrodeDirectory = fullfile(testDirectory, '..', '..', '..', 'templates', ...
    'electrode_models');
addpath(modelDirectory);
addpath(electrodeDirectory);
testCase.TestData.modelDirectory = modelDirectory;
testCase.TestData.electrodeDirectory = electrodeDirectory;
end

function teardownOnce(testCase)
rmpath(testCase.TestData.modelDirectory);
rmpath(testCase.TestData.electrodeDirectory);
end

function testRightVoltageRowProducesTenStrictParameterFiles(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() cleanup_fixture(root)); %#ok<NASGU>

subjectDir = fullfile(root, 'generic-subject-zeta-47');
stimulationRoot = fullfile(root, 'stimulation');
connectomeDir = fullfile(stimulationRoot, 'connectome');
environmentPath = fullfile(root, 'fake-oss-environment');
mkdir(subjectDir);
mkdir(stimulationRoot);
mkdir(connectomeDir);
mkdir(fullfile(environmentPath, 'bin'));
touch_file(fullfile(environmentPath, 'bin', 'python'), 'fake python');
touch_file(fullfile(connectomeDir, 'data1.mat'), 'synthetic connectome');

reconstructionPath = fullfile(subjectDir, 'reconstruction.mat');
write_synthetic_reconstruction(reconstructionPath);
templateSegmaskPath = fullfile(root, 'segmask.nii');
touch_file(templateSegmaskPath, 'synthetic segmentation');

request = struct();
request.schema_version = 'dual_frequency_oss_matlab_request_v1';
request.subject_dir = subjectDir;
request.reconstruction_path = reconstructionPath;
request.transform_path = '';
request.template_segmask_path = templateSegmaskPath;
request.stimulation_root = stimulationRoot;
request.connectome_dir = connectomeDir;
request.connectome_label = 'generic-formal-connectome';
request.electrode_model = 'Medtronic 3387';
request.reconstruction_lead_id = 1;
request.contact_count = 4;
request.side = 'R';
request.frequency_hz = 130;
request.pulse_width_us = 60;
request.control_mode = 'voltage';
request.delivery_mode = 'alternating';
request.environment_path = environmentPath;
request.diameters_um = linspace(1, 4, 10);
source = struct();
source.source_id = 'generic-source-alpha';
source.control_mode = 'voltage';
source.amplitude = 2.5;
source.frequency_hz = 130;
source.pulse_width_us = 60;
source.contacts = [contact(1, 'cathode'), contact('case', 'anode')];
request.sources = source;

requestPath = fullfile(root, 'request.json');
manifestPath = fullfile(root, 'manifest.json');
write_text(requestPath, jsonencode(request));
manifest = mh_oss_prepare_canonical_row(requestPath, manifestPath);

verifyTrue(testCase, isfile(manifestPath));
verifyEqual(testCase, manifest.schema_version, ...
    'dual_frequency_oss_matlab_manifest_v1');
verifyEqual(testCase, numel(manifest.parameter_files), 10);
verifyEqual(testCase, manifest.control_mode, 'voltage');
verifyEqual(testCase, manifest.frequency_hz, 130);
verifyEqual(testCase, manifest.pulse_width_us, 60);
verifyEqual(testCase, cell2mat(manifest.active_contact_locations_mm), ...
    [10, -10, -10], 'AbsTol', 0);
verifyEqual(testCase, fileread(manifest.segmask_path), ...
    fileread(templateSegmaskPath));

expectedDiameters = linspace(1, 4, 10);
for sampleIndex = 1:10
    parameterPath = manifest.parameter_files{sampleIndex};
    verifyTrue(testCase, isfile(parameterPath));
    loaded = load(parameterPath, 'settings');
    verifyEqual(testCase, loaded.settings.Electrode_type, 'Medtronic 3387');
    verifyEqual(testCase, loaded.settings.Phi_vector(1, 1), -2.5, ...
        'AbsTol', 0);
    verifyTrue(testCase, all(isnan(loaded.settings.Phi_vector(1, 2:4))));
    verifyEqual(testCase, loaded.settings.current_control(1), 0);
    verifyEqual(testCase, loaded.settings.Case_grounding(1), 1);
    verifyEqual(testCase, loaded.settings.fiberDiameter, ...
        expectedDiameters(sampleIndex), 'AbsTol', 1e-12);
    verifyEqual(testCase, loaded.settings.axonLength, 10, 'AbsTol', 0);
    verifyEqual(testCase, loaded.settings.cond_model, 'ColeCole4');
    verifyEqual(testCase, loaded.settings.DTI_data_name, 'no dti');
end
end

function testRejectsPureXAxisDirectionalLead(testCase)
root = tempname;
mkdir(root);
cleanup = onCleanup(@() cleanup_fixture(root)); %#ok<NASGU>

subjectDir = fullfile(root, 'generic-directional-subject');
stimulationRoot = fullfile(root, 'stimulation');
connectomeDir = fullfile(stimulationRoot, 'connectome');
environmentPath = fullfile(root, 'fake-oss-environment');
mkdir(subjectDir);
mkdir(stimulationRoot);
mkdir(connectomeDir);
mkdir(fullfile(environmentPath, 'bin'));
touch_file(fullfile(environmentPath, 'bin', 'python'), 'fake python');
touch_file(fullfile(connectomeDir, 'data1.mat'), 'synthetic connectome');

reconstructionPath = fullfile(subjectDir, 'reconstruction.mat');
write_directional_x_axis_reconstruction(reconstructionPath);
templateSegmaskPath = fullfile(root, 'segmask.nii');
touch_file(templateSegmaskPath, 'synthetic segmentation');

request = struct();
request.schema_version = 'dual_frequency_oss_matlab_request_v1';
request.subject_dir = subjectDir;
request.reconstruction_path = reconstructionPath;
request.transform_path = '';
request.template_segmask_path = templateSegmaskPath;
request.stimulation_root = stimulationRoot;
request.connectome_dir = connectomeDir;
request.connectome_label = 'generic-formal-connectome';
request.electrode_model = 'Medtronic B33005';
request.reconstruction_lead_id = 1;
request.contact_count = 8;
request.side = 'R';
request.frequency_hz = 130;
request.pulse_width_us = 60;
request.control_mode = 'voltage';
request.delivery_mode = 'alternating';
request.environment_path = environmentPath;
request.diameters_um = linspace(1, 4, 10);
source = struct();
source.source_id = 'generic-directional-source';
source.control_mode = 'voltage';
source.amplitude = 2.5;
source.frequency_hz = 130;
source.pulse_width_us = 60;
source.contacts = [contact(1, 'cathode'), contact('case', 'anode')];
request.sources = source;

requestPath = fullfile(root, 'request.json');
manifestPath = fullfile(root, 'manifest.json');
write_text(requestPath, jsonencode(request));
verifyError(testCase, ...
    @() mh_oss_prepare_canonical_row(requestPath, manifestPath), ...
    'mh_oss:UnsupportedDirectionalGeometry');
verifyFalse(testCase, isfile(manifestPath));
end

function value = contact(identifier, polarity)
value = struct('contact', identifier, 'polarity', polarity, 'fraction', 1.0);
end

function write_synthetic_reconstruction(path)
right = [10, -10, -10; 10, -10, -7; 10, -10, -4; 10, -10, -1];
left = [-10, -10, -10; -10, -10, -7; -10, -10, -4; -10, -10, -1];
rightMarkers = struct( ...
    'head', right(1, :), ...
    'tail', right(end, :), ...
    'x', right(1, :) + [0.6, 0, 0], ...
    'y', right(1, :) + [0, 0.6, 0]);
leftMarkers = struct( ...
    'head', left(1, :), ...
    'tail', left(end, :), ...
    'x', left(1, :) + [0.6, 0, 0], ...
    'y', left(1, :) + [0, 0.6, 0]);
reco = struct();
reco.props = [ ...
    struct('elmodel', 'Medtronic 3387', 'manually_corrected', 1), ...
    struct('elmodel', 'Medtronic 3387', 'manually_corrected', 1)];
reco.mni = struct( ...
    'coords_mm', {{right, left}}, ...
    'markers', [rightMarkers, leftMarkers]);
save(path, 'reco');
end

function write_directional_x_axis_reconstruction(path)
x = (10:17)';
right = [x, -10 * ones(8, 1), -5 * ones(8, 1)];
left = [-x, -10 * ones(8, 1), -5 * ones(8, 1)];
rightMarkers = struct( ...
    'head', right(1, :), ...
    'tail', right(end, :), ...
    'x', right(1, :) + [0, 0.6, 0], ...
    'y', right(1, :) + [0, 0, 0.6]);
leftMarkers = struct( ...
    'head', left(1, :), ...
    'tail', left(end, :), ...
    'x', left(1, :) + [0, 0.6, 0], ...
    'y', left(1, :) + [0, 0, 0.6]);
reco = struct();
reco.props = [ ...
    struct('elmodel', 'Medtronic B33005', 'manually_corrected', 1), ...
    struct('elmodel', 'Medtronic B33005', 'manually_corrected', 1)];
reco.mni = struct( ...
    'coords_mm', {{right, left}}, ...
    'markers', [rightMarkers, leftMarkers]);
save(path, 'reco');
end

function touch_file(path, contents)
write_text(path, contents);
end

function write_text(path, contents)
[fileId, message] = fopen(path, 'w', 'n', 'UTF-8');
if fileId < 0
    error('test_oss:WriteFailed', 'Could not create %s: %s', path, message);
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s', contents);
clear cleanup;
end

function cleanup_fixture(root)
if isfolder(root)
    rmdir(root, 's');
end
end
