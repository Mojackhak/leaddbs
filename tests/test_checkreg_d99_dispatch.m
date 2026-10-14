function tests = test_checkreg_d99_dispatch
% Exercise the real recompute callback and normalization dispatcher in isolation.
tests = functiontests(localfunctions);
end

function setupOnce(test)
test.TestData.path = path;
test.TestData.cwd = pwd;
root = fileparts(fileparts(mfilename('fullpath')));
addpath(root, fullfile(root, 'helpers'));
folder = tempname;
mkdir(folder);
mocks = fullfile(folder, 'mocks');
mkdir(mocks);
writeMock(mocks, 'ea_prefs', [
    "function value=ea_prefs(varargin)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.prefReads=D99_CHECKREG_TEST.prefReads+1;"
    "value=D99_CHECKREG_TEST.savedPrefs;"
    "end"]);
writeMock(mocks, 'ea_busyaction', "function ea_busyaction(varargin), end");
writeMock(mocks, 'ea_chirp', "function ea_chirp(varargin), end");
writeMock(mocks, 'ea_space', "function value=ea_space(varargin), value=[tempdir,'template',filesep]; end");
writeMock(mocks, 'ea_init_normpopup', "function ea_init_normpopup(varargin), end");
writeMock(mocks, 'ea_stripext', "function value=ea_stripext(p), [~,value]=fileparts(p); end");
writeMock(mocks, 'loadjson', "function value=loadjson(p), value=jsondecode(fileread(p)); end");
writeMock(mocks, 'savejson', [
    "function savejson(~,value,p)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.logWrites=D99_CHECKREG_TEST.logWrites+1;"
    "f=fopen(p,'w'); fprintf(f,'%s',jsonencode(value)); fclose(f);"
    "end"]);
writeMock(mocks, 'ea_delete', [
    "function ea_delete(paths,varargin)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.deleteCalls=D99_CHECKREG_TEST.deleteCalls+1;"
    "for i=1:numel(paths), [~,name,ext]=fileparts(paths{i}); movefile(paths{i},fullfile(D99_CHECKREG_TEST.trash,[name,ext])); end"
    "end"]);
writeMock(mocks, 'ea_ants_d99_deep_run', [
    "function ea_ants_d99_deep_run(varargin)"
    "error('D99Checkreg:UnexpectedRegistration','Callback tests must not execute registration.');"
    "end"]);
writeMock(mocks, 'ea_normalize_ants_d99_deep', [
    "function ea_normalize_ants_d99_deep(options)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.publisherOptions=options;"
    "D99_CHECKREG_TEST.publisherCalls=D99_CHECKREG_TEST.publisherCalls+1;"
    "if D99_CHECKREG_TEST.failPublisher, error('D99Checkreg:PublisherFailed','Simulated staged publication failure.'); end"
    "end"]);
writeMock(mocks, 'ea_norm_refine_prepare', [
    "function [options,context]=ea_norm_refine_prepare(options)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.legacyCalls=D99_CHECKREG_TEST.legacyCalls+1;"
    "D99_CHECKREG_TEST.legacyOptions=options; context=struct('cancelled',true);"
    "end"]);
writeMock(mocks, 'ea_gencheckregfigs', [
    "function ea_gencheckregfigs(varargin)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.qcCalls=D99_CHECKREG_TEST.qcCalls+1;"
    "end"]);
writeMock(mocks, 'ea_segmask_cleanup', [
    "function ea_segmask_cleanup(varargin)"
    "global D99_CHECKREG_TEST; D99_CHECKREG_TEST.segmaskCalls=D99_CHECKREG_TEST.segmaskCalls+1;"
    "end"]);
addpath(mocks, '-begin');
cd(mocks);
clear ea_prefs ea_busyaction ea_chirp ea_space ea_init_normpopup ea_stripext ...
    loadjson savejson ea_delete ea_ants_d99_deep_run ea_normalize_ants_d99_deep ...
    ea_norm_refine_prepare ea_gencheckregfigs ea_segmask_cleanup;
assert(strcmp(which('ea_prefs'), fullfile(mocks, 'ea_prefs.m')));
test.TestData.folder = folder;
end

function teardownOnce(test)
cd(test.TestData.cwd);
path(test.TestData.path);
clear ea_prefs ea_busyaction ea_chirp ea_space ea_init_normpopup ea_stripext ...
    loadjson savejson ea_delete ea_ants_d99_deep_run ea_normalize_ants_d99_deep ...
    ea_norm_refine_prepare ea_gencheckregfigs ea_segmask_cleanup;
clear global D99_CHECKREG_TEST;
end

function setup(test)
global D99_CHECKREG_TEST;
folder = tempname(test.TestData.folder);
mkdir(folder);
trash = fullfile(folder, 'preserved');
mkdir(trash);
D99_CHECKREG_TEST = struct('savedPrefs', struct('machine', struct('normsettings', ...
    struct('ants_preset', 'ea_antspreset_macaque_d99_deep'))), ...
    'prefReads', 0, 'publisherCalls', 0, 'legacyCalls', 0, 'qcCalls', 0, ...
    'segmaskCalls', 0, 'deleteCalls', 0, 'logWrites', 0, 'failPublisher', false, 'trash', trash);
options.subj.subjDir = folder;
options.subj.subjId = 'callback_test';
options.subj.AnchorModality = 'ax_T1w';
options.subj.postopModality = 'CT';
options.subj.normDir = fullfile(folder, 'normalization');
options.subj.brainshiftDir = fullfile(folder, 'brainshift');
options.subj.coreg.anat.preop.ax_T1w = fullfile(folder, 'anchor.nii');
options.subj.coreg.log.method = fullfile(folder, 'coregistration', 'method.json');
options.subj.norm.anat.preop.ax_T1w = fullfile(options.subj.normDir, 'anat', 'T1.nii');
options.subj.norm.anat.preop.ax_T2w = fullfile(options.subj.normDir, 'anat', 'T2.nii');
options.subj.norm.anat.postop.CT = fullfile(options.subj.normDir, 'anat', 'CT.nii');
options.subj.norm.anat.postop.tonemapCT = fullfile(options.subj.normDir, 'anat', 'toneCT.nii');
options.subj.norm.log.method = fullfile(options.subj.normDir, 'log', 'method.json');
options.subj.norm.checkreg.preop.ax_T1w = fullfile(options.subj.normDir, 'checkreg', 'T1.png');
options.subj.preopAnat.ax_T1w.norm = options.subj.norm.anat.preop.ax_T1w;
options.primarytemplate = 't1';
options.normalize.method = 'EasyReg (Iglesias 2023)';
options.prefs.diary = false;
options.prefs.normalize.default = 'ANTs (Avants 2008)';
options.prefs.subjectSpecificPath = fullfile(folder, 'keep_this_path');
options.prefs.machine.normsettings.ants_preset = 'ea_antspreset_ants_wiki';
images = [struct2cell(options.subj.norm.anat.preop); struct2cell(options.subj.norm.anat.postop)];
for i = 1:numel(images)
    writeFile(images{i}, ['previous-', num2str(i)]);
end
writeFile(options.subj.norm.log.method, '{"method":"ANTs (Avants 2008)","approval":1}');
mkdir(fileparts(options.subj.norm.checkreg.preop.ax_T1w));
imwrite(uint8(ones(8, 8) * 80), options.subj.norm.checkreg.preop.ax_T1w);

handles.leadfigure = figure('Visible', 'off', 'Name', 'Callback test');
for name = {'recomputebutn', 'disapprovebutn', 'approvebutn', 'checkatl', ...
        'anchortxt', 'coregresultstxt', 'normsettings', 'substitute', 'anchormod', 'imgfn', 'depvolume'}
    handles.(name{1}) = uicontrol(handles.leadfigure, 'Style', 'text');
end
handles.coregmrmethod = uicontrol(handles.leadfigure, 'Style', 'popupmenu', ...
    'String', {'ANTs (Avants 2008)', 'EasyReg (Iglesias 2023)'}, 'Value', 1);
handles.standardax = axes('Parent', handles.leadfigure, 'Visible', 'off');
setappdata(handles.leadfigure, 'options', options);
setappdata(handles.leadfigure, 'checkregImages', {options.subj.norm.anat.preop.ax_T1w});
setappdata(handles.leadfigure, 'activevolume', 1);
setappdata(handles.leadfigure, 'b0restanchor', {''});
test.TestData.handles = handles;
test.TestData.options = options;
test.TestData.images = images;
end

function teardown(test)
delete(test.TestData.handles.leadfigure);
end

function testNewlySavedPresetDispatchesBeforeDeletion(test)
global D99_CHECKREG_TEST;
runCallback(test);
verifyEqual(test, D99_CHECKREG_TEST.publisherCalls, 1);
verifyEqual(test, D99_CHECKREG_TEST.publisherOptions.normalize.method, 'ANTs (Avants 2008)');
verifyEqual(test, D99_CHECKREG_TEST.publisherOptions.prefs.machine.normsettings.ants_preset, 'ea_antspreset_macaque_d99_deep');
verifyEqual(test, [D99_CHECKREG_TEST.deleteCalls, D99_CHECKREG_TEST.legacyCalls, ...
    D99_CHECKREG_TEST.qcCalls, D99_CHECKREG_TEST.segmaskCalls, D99_CHECKREG_TEST.logWrites], zeros(1, 5));
verifyEqual(test, D99_CHECKREG_TEST.prefReads, 1);
verifyPriorFiles(test);
stored = getappdata(test.TestData.handles.leadfigure, 'options');
verifyEqual(test, stored.prefs.machine.normsettings, D99_CHECKREG_TEST.savedPrefs.machine.normsettings);
verifyEqual(test, stored.prefs.subjectSpecificPath, test.TestData.options.prefs.subjectSpecificPath);
verifyEqual(test, stored.subj, test.TestData.options.subj);
verifyEqual(test, stored.normalize.method, 'ANTs (Avants 2008)');
end

function testFailedD99PublicationPreservesPriorOutputs(test)
global D99_CHECKREG_TEST;
D99_CHECKREG_TEST.failPublisher = true;
verifyError(test, @() runCallback(test), 'D99Checkreg:PublisherFailed');
verifyPriorFiles(test);
verifyEqual(test, [D99_CHECKREG_TEST.publisherCalls, D99_CHECKREG_TEST.deleteCalls, ...
    D99_CHECKREG_TEST.qcCalls, D99_CHECKREG_TEST.segmaskCalls, D99_CHECKREG_TEST.logWrites], [1, 0, 0, 0, 0]);
stored = getappdata(test.TestData.handles.leadfigure, 'options');
verifyEqual(test, stored.prefs.machine.normsettings.ants_preset, 'ea_antspreset_macaque_d99_deep');
end

function testSavingLegacyPresetRestoresLegacyCallback(test)
global D99_CHECKREG_TEST;
options = test.TestData.options;
options.prefs.machine.normsettings.ants_preset = 'ea_antspreset_macaque_d99_deep';
setappdata(test.TestData.handles.leadfigure, 'options', options);
D99_CHECKREG_TEST.savedPrefs.machine.normsettings.ants_preset = 'ea_antspreset_ants_wiki';
runCallback(test);
verifyLegacyBehavior(test, 'ANTs (Avants 2008)');
verifyEqual(test, D99_CHECKREG_TEST.legacyOptions.prefs.machine.normsettings.ants_preset, 'ea_antspreset_ants_wiki');
end

function testOtherMethodDoesNotUseD99Publisher(test)
set(test.TestData.handles.coregmrmethod, 'Value', 2);
runCallback(test);
verifyLegacyBehavior(test, 'EasyReg (Iglesias 2023)');
end

function runCallback(test)
handles = test.TestData.handles;
ea_checkreg('recomputebutn_Callback', handles.recomputebutn, [], handles);
end

function verifyPriorFiles(test)
for i = 1:numel(test.TestData.images)
    verifyEqual(test, fileread(test.TestData.images{i}), ['previous-', num2str(i)]);
end
verifyEqual(test, fileread(test.TestData.options.subj.norm.log.method), ...
    '{"method":"ANTs (Avants 2008)","approval":1}');
verifyEqual(test, imread(test.TestData.options.subj.norm.checkreg.preop.ax_T1w), uint8(ones(8, 8) * 80));
end

function verifyLegacyBehavior(test, method)
global D99_CHECKREG_TEST;
verifyEqual(test, [D99_CHECKREG_TEST.publisherCalls, D99_CHECKREG_TEST.deleteCalls, ...
    D99_CHECKREG_TEST.legacyCalls, D99_CHECKREG_TEST.qcCalls, D99_CHECKREG_TEST.segmaskCalls, ...
    D99_CHECKREG_TEST.logWrites], [0, 2, 1, 1, 1, 1]);
verifyEqual(test, D99_CHECKREG_TEST.legacyOptions.normalize.method, method);
record = jsondecode(fileread(test.TestData.options.subj.norm.log.method));
verifyEqual(test, record.approval, 0);
for i = 1:numel(test.TestData.images)
    verifyFalse(test, isfile(test.TestData.images{i}));
end
end

function writeMock(folder, name, lines)
writeFile(fullfile(folder, [name, '.m']), char(join(lines, newline)));
end

function writeFile(path, content)
folder = fileparts(path);
if ~isfolder(folder)
    mkdir(folder);
end
stream = fopen(path, 'w');
fprintf(stream, '%s', content);
fclose(stream);
end
