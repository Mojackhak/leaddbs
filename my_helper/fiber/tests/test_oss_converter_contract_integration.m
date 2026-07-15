function tests = test_oss_converter_contract_integration
% Verify the serialized MAT contract through the installed OSS converter.
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

function testPinnedConverterDisablesDtiAndPreservesWaveform(testCase)
converterPath = locate_converter();
assumeTrue(testCase, isfile(converterPath), ...
    'The pinned OSS-DBSv2 converter is unavailable.');

root = tempname;
mkdir(root);
cleanup = onCleanup(@() cleanup_fixture(root)); %#ok<NASGU>
subjectDir = fullfile(root, 'generic-converter-subject');
stimulationRoot = fullfile(root, 'stimulation');
connectomeDir = fullfile(stimulationRoot, 'connectome');
environmentPath = fileparts(fileparts(converterPath));
mkdir(subjectDir);
mkdir(stimulationRoot);
mkdir(connectomeDir);
write_text(fullfile(connectomeDir, 'data1.mat'), 'synthetic connectome');
reconstructionPath = fullfile(subjectDir, 'reconstruction.mat');
write_synthetic_reconstruction(reconstructionPath);
templateSegmaskPath = fullfile(root, 'segmask.nii');
write_text(templateSegmaskPath, 'synthetic segmentation');

request = standard_request(subjectDir, reconstructionPath, ...
    templateSegmaskPath, stimulationRoot, connectomeDir, environmentPath);
requestPath = fullfile(root, 'request.json');
manifestPath = fullfile(root, 'manifest.json');
write_text(requestPath, jsonencode(request));
manifest = mh_oss_prepare_canonical_row(requestPath, manifestPath);

converterOutput = fullfile(root, 'converter-output');
mkdir(converterOutput);
command = sprintf('"%s" --hemi_side 0 "%s" --output_path "%s"', ...
    converterPath, manifest.parameter_files{1}, converterOutput);
[status, output] = system(command);
verifyEqual(testCase, status, 0, output);

jsonFiles = dir(fullfile(converterOutput, '*.json'));
verifyEqual(testCase, numel(jsonFiles), 1);
converted = jsondecode(fileread(fullfile(jsonFiles(1).folder, ...
    jsonFiles(1).name)));
verifyFalse(testCase, converted.MaterialDistribution.DiffusionTensorActive);
verifyEqual(testCase, converted.MaterialDistribution.DTIPath, '');
verifyEqual(testCase, converted.DielectricModel.Type, 'ColeCole4');
verifyEqual(testCase, converted.StimulationSignal.Type, 'Rectangle');
verifyFalse(testCase, converted.StimulationSignal.CurrentControlled);
verifyEqual(testCase, converted.StimulationSignal.Frequency_Hz_, 130);
verifyEqual(testCase, converted.StimulationSignal.PulseWidth_us_, 60);
end

function request = standard_request(subjectDir, reconstructionPath, ...
        templateSegmaskPath, stimulationRoot, connectomeDir, environmentPath)
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
source.source_id = 'generic-converter-source';
source.control_mode = 'voltage';
source.amplitude = 2.5;
source.frequency_hz = 130;
source.pulse_width_us = 60;
source.contacts = [contact(1, 'cathode'), contact('case', 'anode')];
request.sources = source;
end

function value = contact(identifier, polarity)
value = struct('contact', identifier, 'polarity', polarity, 'fraction', 1.0);
end

function path = locate_converter()
path = '';
[status, base] = system('conda info --base');
if status == 0
    candidate = fullfile(strtrim(base), 'envs', 'ossdbsv2', 'bin', ...
        'leaddbs2ossdbs');
    if isfile(candidate)
        path = candidate;
    end
end
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
