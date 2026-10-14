function tests = test_ants_d99_bulk_reapplication
% Exercise command dispatch without invoking ANTs or touching subject data.
tests = functiontests(localfunctions);
end

function setupOnce(test)
root = fileparts(fileparts(mfilename('fullpath')));
test.TestData.originalPath = path;
test.TestData.originalDirectory = pwd;
test.TestData.directory = tempname;
mkdir(test.TestData.directory);
stubs = fullfile(test.TestData.directory, 'stubs');
mkdir(stubs);
write_stub(stubs, 'ea_libs_helper', {'function ea_libs_helper', 'end'});
write_stub(stubs, 'ea_getExec', {'function result = ea_getExec(executable, varargin)', 'result = executable;', 'end'});
write_stub(stubs, 'ea_runcmd', {'function status = ea_runcmd(command, varargin)', ...
    'global EA_ANTS_REAPPLICATION_TEST', ...
    'EA_ANTS_REAPPLICATION_TEST.commands{end+1} = command;', ...
    'status = EA_ANTS_REAPPLICATION_TEST.commandStatus;', 'end'});
write_stub(stubs, 'loadjson', {'function result = loadjson(filename)', ...
    'global EA_ANTS_REAPPLICATION_TEST', ...
    'EA_ANTS_REAPPLICATION_TEST.parseCount = EA_ANTS_REAPPLICATION_TEST.parseCount + 1;', ...
    'EA_ANTS_REAPPLICATION_TEST.parsedFiles{end+1} = filename;', ...
    'result = jsondecode(fileread(filename));', 'end'});
write_stub(stubs, 'ea_space', {'function result = ea_space(varargin)', ...
    'global EA_ANTS_REAPPLICATION_TEST', 'result = EA_ANTS_REAPPLICATION_TEST.templateDirectory;', 'end'});
write_stub(stubs, 'ea_getspacedef', {'function result = ea_getspacedef(varargin)', ...
    'result = struct(''templates'', {{''t1''}});', 'end'});
write_stub(stubs, 'ea_getleadtempdir', {'function result = ea_getleadtempdir', ...
    'global EA_ANTS_REAPPLICATION_TEST', 'result = EA_ANTS_REAPPLICATION_TEST.temporaryDirectory;', 'end'});
write_stub(stubs, 'ea_generate_uuid', {'function result = ea_generate_uuid', ...
    'global EA_ANTS_REAPPLICATION_TEST', ...
    'EA_ANTS_REAPPLICATION_TEST.uuidIndex = EA_ANTS_REAPPLICATION_TEST.uuidIndex + 1;', ...
    'result = sprintf(''brainshift_%d'', EA_ANTS_REAPPLICATION_TEST.uuidIndex);', 'end'});
write_stub(stubs, 'ea_load_nii', {'function result = ea_load_nii(filename)', ...
    'global EA_ANTS_REAPPLICATION_TEST', ...
    'result = struct(''fname'', filename, ''mat'', EA_ANTS_REAPPLICATION_TEST.sourceAffine);', 'end'});
write_stub(stubs, 'ea_write_nii', {'function ea_write_nii(nii)', ...
    'global EA_ANTS_REAPPLICATION_TEST', ...
    'EA_ANTS_REAPPLICATION_TEST.writtenImages{end+1} = nii;', 'end'});
addpath(fullfile(root, 'ext_libs', 'ANTs'), fullfile(root, 'helpers'), ...
    fullfile(root, 'helpers', 'gui'), fullfile(root, 'ext_libs'), ...
    fullfile(root, 'ext_libs', 'GetFullPath'));
addpath(stubs, '-begin');
cd(test.TestData.directory);
clear_stubs;
end

function teardownOnce(test)
clear_stubs;
cd(test.TestData.originalDirectory);
path(test.TestData.originalPath);
clear global EA_ANTS_REAPPLICATION_TEST
rmdir(test.TestData.directory, 's');
end

function setup(test)
fixture = tempname(test.TestData.directory);
mkdir(fixture);
templateDirectory = fullfile(fixture, 'template');
temporaryDirectory = fullfile(fixture, 'temporary');
mkdir(templateDirectory);
mkdir(temporaryDirectory);
global EA_ANTS_REAPPLICATION_TEST
EA_ANTS_REAPPLICATION_TEST = struct('commands', {{}}, 'parseCount', 0, 'commandStatus', 0, ...
    'parsedFiles', {{}}, ...
    'templateDirectory', [templateDirectory, filesep], ...
    'temporaryDirectory', [temporaryDirectory, filesep], ...
    'uuidIndex', 0, 'writtenImages', {{}}, ...
    'sourceAffine', [2, 0, 0, 10; 0, 3, 0, 20; 0, 0, 4, 30; 0, 0, 0, 1]);
options.subj.coreg.anat.preop.axT1w = fullfile(fixture, 'anchor T1.nii');
options.subj.coreg.anat.preop.axT2w = fullfile(fixture, 'additional T2.nii');
options.subj.norm.anat.preop.axT1w = fullfile(fixture, 'normalized', 'T1.nii');
options.subj.norm.anat.preop.axT2w = fullfile(fixture, 'normalized', 'T2.nii');
options.subj.coreg.anat.postop.CT = fullfile(fixture, 'postoperative CT.nii');
options.subj.norm.anat.postop.CT = fullfile(fixture, 'normalized', 'CT.nii');
options.subj.postopModality = 'CT';
options.subj.AnchorModality = 'axT1w';
options.subj.brainshift.transform.scrf = fullfile(fixture, 'scrf.mat');
options.subj.brainshift.log.method = fullfile(fixture, 'brainshift.json');
options.subj.norm.log.method = fullfile(fixture, 'normmethod.json');
options.subj.norm.transform.forwardBaseName = fullfile(fixture, 'from-native_to-D99_desc-');
options.subj.norm.transform.inverseBaseName = fullfile(fixture, 'from-D99_to-native_desc-');
options.prefs.machine.normsettings.ants_preset = 'ea_antspreset_effective_lowtomidvar';
for filename = [struct2cell(options.subj.coreg.anat.preop); struct2cell(options.subj.coreg.anat.postop)]'
    write_text(filename{1}, 'image fixture');
end
write_text(fullfile(templateDirectory, 't1.nii'), 'template fixture');
test.TestData.options = options;
test.TestData.fixture = fixture;
write_log(options, profile_log);
end

function testBulkProfileUsesStoredSettingsAndAllSources(test)
options = test.TestData.options;
ea_ants_apply_transforms(options);
state = captured_state;
verifyEqual(test, state.parseCount, 1);
verifyNumElements(test, state.commands, 3);
sources = [struct2cell(options.subj.coreg.anat.preop); struct2cell(options.subj.coreg.anat.postop)];
outputs = [struct2cell(options.subj.norm.anat.preop); struct2cell(options.subj.norm.anat.postop)];
for index = 1:3
    verify_command(test, state.commands{index}, sources{index}, outputs{index}, ...
        [state.templateDirectory, 't1.nii'], ...
        [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'Linear', '0');
end
end

function testBulkLegacyIgnoresGlobalProfileAndOtherStoredFields(test)
options = test.TestData.options;
options.prefs.machine.normsettings.ants_preset = 'ea_antspreset_macaque_d99_deep';
log = profile_log;
log.settings = rmfield(log.settings, 'preset_id');
write_log(options, log);
ea_ants_apply_transforms(options);
state = captured_state;
verifyEqual(test, state.parseCount, 1);
verifyNumElements(test, state.commands, 3);
for command = state.commands
    verifyTrue(test, contains(command{1}, ' --float 1 '));
    verifyTrue(test, endsWith(command{1}, ' --interpolation LanczosWindowedSinc'));
end
end

function testManualForwardRetainsLegacyDefaults(test)
options = test.TestData.options;
ea_ants_apply_transforms(options, options.subj.coreg.anat.preop.axT1w, ...
    options.subj.norm.anat.preop.axT1w, false);
state = captured_state;
verifyEqual(test, state.parseCount, 1);
verify_command(test, state.commands{1}, options.subj.coreg.anat.preop.axT1w, ...
    options.subj.norm.anat.preop.axT1w, [state.templateDirectory, 't1.nii'], ...
    [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'LanczosWindowedSinc', '1');
end

function testManualInverseRetainsReferenceAndLabelInterpolation(test)
options = test.TestData.options;
state = captured_state;
source = [state.templateDirectory, 't1.nii'];
destination = fullfile(test.TestData.fixture, 'native label.nii');
ea_ants_apply_transforms(options, source, destination, true);
state = captured_state;
verify_command(test, state.commands{1}, source, destination, ...
    options.subj.coreg.anat.preop.axT1w, ...
    [options.subj.norm.transform.inverseBaseName, 'ants.nii.gz'], 'GenericLabel', '1');
end

function testBulkProfileCommandFailureStopsBeforeFurtherImages(test)
global EA_ANTS_REAPPLICATION_TEST
EA_ANTS_REAPPLICATION_TEST.commandStatus = 7;
verifyError(test, @() ea_ants_apply_transforms(test.TestData.options), ...
    'ea_ants_apply_transforms:CommandFailed');
verifyNumElements(test, EA_ANTS_REAPPLICATION_TEST.commands, 1);
end

function testLegacyAndManualKeepTheirExistingStatusHandling(test)
global EA_ANTS_REAPPLICATION_TEST
EA_ANTS_REAPPLICATION_TEST.commandStatus = 7;
options = test.TestData.options;
write_log(options, struct('method', 'ANTs (Avants 2008)'));
ea_ants_apply_transforms(options);
verifyNumElements(test, EA_ANTS_REAPPLICATION_TEST.commands, 3);
write_log(options, profile_log);
ea_ants_apply_transforms(options, options.subj.coreg.anat.preop.axT1w, ...
    options.subj.norm.anat.preop.axT1w, false);
verifyNumElements(test, EA_ANTS_REAPPLICATION_TEST.commands, 4);
end

function testManualPositionalArgumentsDoNotReadNormalizationLog(test)
options = test.TestData.options;
options.subj.norm.log.method = fullfile(test.TestData.fixture, 'absent.json');
reference = fullfile(test.TestData.fixture, 'manual reference.nii');
transform = fullfile(test.TestData.fixture, 'manual transform.mat');
ea_ants_apply_transforms(options, options.subj.coreg.anat.preop.axT2w, ...
    options.subj.norm.anat.preop.axT2w, true, reference, transform, -1, 4, 3);
state = captured_state;
verifyEqual(test, state.parseCount, 0);
verify_command(test, state.commands{1}, options.subj.coreg.anat.preop.axT2w, ...
    options.subj.norm.anat.preop.axT2w, reference, transform, 'GenericLabel', '1');
verifyTrue(test, contains(state.commands{1}, ' --dimensionality 4 --input-image-type 3 '));
end

function testBulkCTBrainshiftUsesTemporaryHeader(test)
options = test.TestData.options;
mat = [0, -1, 0, 7; 1, 0, 0, -3; 0, 0, 1, 2; 0, 0, 0, 1];
save(options.subj.brainshift.transform.scrf, 'mat');
ea_ants_apply_transforms(options);
state = captured_state;
verifyNumElements(test, state.commands, 3);
verifyNumElements(test, state.writtenImages, 1);
verifyEqual(test, state.writtenImages{1}.mat, mat * state.sourceAffine);
verify_command(test, state.commands{3}, state.writtenImages{1}.fname, ...
    options.subj.norm.anat.postop.CT, [state.templateDirectory, 't1.nii'], ...
    [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'Linear', '0');
verifyEqual(test, fileread(options.subj.coreg.anat.postop.CT), 'image fixture');
end

function testBulkMRIBrainshiftKeepsEveryPostoperativeImage(test)
options = test.TestData.options;
options.subj.postopModality = 'MRI';
options.subj.coreg.anat.postop = struct('T1w', fullfile(test.TestData.fixture, 'postoperative T1.nii'), ...
    'T2w', fullfile(test.TestData.fixture, 'postoperative T2.nii'));
options.subj.norm.anat.postop = struct('T1w', fullfile(test.TestData.fixture, 'normalized', 'postT1.nii'), ...
    'T2w', fullfile(test.TestData.fixture, 'normalized', 'postT2.nii'));
for source = struct2cell(options.subj.coreg.anat.postop)'
    write_text(source{1}, 'image fixture');
end
mat = [0, -1, 0, 7; 1, 0, 0, -3; 0, 0, 1, 2; 0, 0, 0, 1];
save(options.subj.brainshift.transform.scrf, 'mat');
ea_ants_apply_transforms(options);
state = captured_state;
verifyNumElements(test, state.commands, 4);
verifyNumElements(test, state.writtenImages, 2);
outputs = struct2cell(options.subj.norm.anat.postop);
for index = 1:2
    verifyEqual(test, state.writtenImages{index}.mat, mat * state.sourceAffine);
    verify_command(test, state.commands{index + 2}, state.writtenImages{index}.fname, ...
        outputs{index}, [state.templateDirectory, 't1.nii'], ...
        [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'Linear', '0');
end
end

function testBulkProfileSkipsUnapprovedStaleBrainshift(test)
options = test.TestData.options;
write_log(options, profile_requiring_brainshift);
mat = [0, -1, 0, 7; 1, 0, 0, -3; 0, 0, 1, 2; 0, 0, 0, 1];
save(options.subj.brainshift.transform.scrf, 'mat');
write_text(options.subj.brainshift.log.method, jsonencode(struct('approval', 0)));
ea_ants_apply_transforms(options);
state = captured_state;
verifyEmpty(test, state.writtenImages);
verifyEqual(test, sum(strcmp(state.parsedFiles, options.subj.norm.log.method)), 1);
verifyEqual(test, sum(strcmp(state.parsedFiles, options.subj.brainshift.log.method)), 1);
verify_command(test, state.commands{3}, options.subj.coreg.anat.postop.CT, ...
    options.subj.norm.anat.postop.CT, [state.templateDirectory, 't1.nii'], ...
    [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'Linear', '0');
end

function testBulkProfileResumesApprovedRenewedBrainshift(test)
options = test.TestData.options;
write_log(options, profile_requiring_brainshift);
mat = [0, -1, 0, 2; 1, 0, 0, 4; 0, 0, 1, -1; 0, 0, 0, 1];
save(options.subj.brainshift.transform.scrf, 'mat');
write_text(options.subj.brainshift.log.method, jsonencode(struct('approval', 1)));
ea_ants_apply_transforms(options);
state = captured_state;
verifyNumElements(test, state.writtenImages, 1);
verifyEqual(test, state.writtenImages{1}.mat, mat * state.sourceAffine);
verifyEqual(test, sum(strcmp(state.parsedFiles, options.subj.norm.log.method)), 1);
verifyEqual(test, sum(strcmp(state.parsedFiles, options.subj.brainshift.log.method)), 1);
verify_command(test, state.commands{3}, state.writtenImages{1}.fname, ...
    options.subj.norm.anat.postop.CT, [state.templateDirectory, 't1.nii'], ...
    [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'Linear', '0');
end

function testBulkProfileSkipsStaleBrainshiftWithoutApprovalLog(test)
options = test.TestData.options;
write_log(options, profile_requiring_brainshift);
mat = eye(4);
save(options.subj.brainshift.transform.scrf, 'mat');
ea_ants_apply_transforms(options);
state = captured_state;
verifyEmpty(test, state.writtenImages);
verifyEqual(test, state.parseCount, 1);
verify_command(test, state.commands{3}, options.subj.coreg.anat.postop.CT, ...
    options.subj.norm.anat.postop.CT, [state.templateDirectory, 't1.nii'], ...
    [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'Linear', '0');
end

function testBulkLegacyKeepsScrfDespiteDownstreamMarker(test)
options = test.TestData.options;
log = profile_requiring_brainshift;
log.settings = rmfield(log.settings, 'preset_id');
write_log(options, log);
mat = [0, -1, 0, 7; 1, 0, 0, -3; 0, 0, 1, 2; 0, 0, 0, 1];
save(options.subj.brainshift.transform.scrf, 'mat');
write_text(options.subj.brainshift.log.method, jsonencode(struct('approval', 0)));
ea_ants_apply_transforms(options);
state = captured_state;
verifyNumElements(test, state.writtenImages, 1);
verifyEqual(test, state.writtenImages{1}.mat, mat * state.sourceAffine);
verifyEqual(test, state.parseCount, 1);
verify_command(test, state.commands{3}, state.writtenImages{1}.fname, ...
    options.subj.norm.anat.postop.CT, [state.templateDirectory, 't1.nii'], ...
    [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz'], 'LanczosWindowedSinc', '1');
end

function testTransformHelperReturnsParsedProfileWithoutAnotherRead(test)
options = test.TestData.options;
[files, log] = ea_gettransformfiles(options);
state = captured_state;
verifyEqual(test, state.parseCount, 1);
verifyEqual(test, log, profile_log);
verifyEqual(test, files.forward, [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz']);
verifyEqual(test, files.inverse, [options.subj.norm.transform.inverseBaseName, 'ants.nii.gz']);
end

function testTransformHelperRetainsLegacySingleOutput(test)
options = test.TestData.options;
log = struct('method', 'ANTs (Avants 2008)');
write_log(options, log);
files = ea_gettransformfiles(options);
verifyEqual(test, files.forward, [options.subj.norm.transform.forwardBaseName, 'ants.nii.gz']);
[second, returned] = ea_gettransformfiles(options);
verifyEqual(test, second, files);
verifyEqual(test, returned, log);
end

function testTransformHelperConnectomeFallbackHasEmptyLog(test)
options = test.TestData.options;
options.subj.norm.log.method = fullfile(test.TestData.fixture, 'absent.json');
options.root = [fullfile(test.TestData.fixture, 'derivatives'), filesep];
options.patientname = 'sub-test';
[files, log] = ea_gettransformfiles(options);
verifyEmpty(test, log);
directory = fullfile(options.root, options.patientname, 'normalization', 'transformations');
verifyEqual(test, files.forward, fullfile(directory, 'y_ea_normparams.nii'));
verifyEqual(test, files.inverse, fullfile(directory, 'y_ea_inv_normparams.nii'));
end

function log = profile_log
log = struct('method', 'ANTs (Avants 2008)', 'transform', struct('format', 'ants'), ...
    'settings', struct('preset_id', 'ea_antspreset_macaque_d99_deep', ...
    'interpolation', 'Linear', 'precision', 'double'));
end

function log = profile_requiring_brainshift
log = profile_log;
log.downstream.brainshift.requires_rerun = true;
end

function state = captured_state
global EA_ANTS_REAPPLICATION_TEST
state = EA_ANTS_REAPPLICATION_TEST;
end

function verify_command(test, command, source, output, reference, transform, interpolation, precision)
verifyTrue(test, contains(command, [' --input ', ea_path_helper(source), ' --output ', ea_path_helper(output)]));
verifyTrue(test, contains(command, [' --reference-image ', ea_path_helper(reference), ' --transform [', ea_path_helper(transform), ',0]']));
verifyTrue(test, contains(command, [' --float ', precision, ' ']));
verifyTrue(test, endsWith(command, [' --interpolation ', interpolation]));
end

function write_log(options, log)
write_text(options.subj.norm.log.method, jsonencode(log));
end

function write_stub(directory, name, lines)
write_text(fullfile(directory, [name, '.m']), strjoin(lines, newline));
end

function write_text(filename, content)
file = fopen(filename, 'w');
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s', content);
end

function clear_stubs
clear ea_libs_helper ea_getExec ea_runcmd loadjson ea_space ea_getspacedef ...
    ea_getleadtempdir ea_generate_uuid ea_load_nii ea_write_nii
end
