function tests = test_ants_d99_preset_ui
% Exercise the real preset and GUIDE controls with isolated preference storage.
tests = functiontests(localfunctions);
end

function setupOnce(test)
test.TestData.originalPath = path;
test.TestData.originalDirectory = pwd;
test.TestData.root = fileparts(fileparts(mfilename('fullpath')));
addpath(test.TestData.root, fullfile(test.TestData.root, 'ext_libs', 'ANTs', 'presets'));
test.TestData.folder = tempname;
mkdir(test.TestData.folder);
writeFixture(fullfile(test.TestData.folder, 'ea_prefs.m'), ...
    ['function prefs=ea_prefs(varargin)' newline ...
     'global LEAD_D99_UI_TEST_PREFS; prefs=LEAD_D99_UI_TEST_PREFS;' newline ...
     'end']);
writeFixture(fullfile(test.TestData.folder, 'ea_setprefs.m'), ...
    ['function ea_setprefs(name,value)' newline ...
     'global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;' newline ...
     'LEAD_D99_UI_TEST_SAVES{end+1}=struct(''name'',name,''value'',value);' newline ...
     'LEAD_D99_UI_TEST_PREFS.machine.(name)=value;' newline ...
     'end']);
writeFixture(fullfile(test.TestData.folder, 'ea_ants_d99_deep_run.m'), ...
    ['function varargout=ea_ants_d99_deep_run(varargin)' newline ...
     'error(''LeadDBS:UnexpectedPresetExecution'',''Opening settings must not run registration.'');' newline ...
     'end']);
addpath(test.TestData.folder, '-begin');
cd(test.TestData.folder);
clear ea_prefs ea_setprefs ea_ants_d99_deep_run;
assert(strcmp(which('ea_prefs'), fullfile(test.TestData.folder, 'ea_prefs.m')));
end

function teardownOnce(test)
cd(test.TestData.originalDirectory);
path(test.TestData.originalPath);
clear ea_prefs ea_setprefs ea_ants_d99_deep_run;
clear global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
end

function setup(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
settings = struct('ants_preset', 'ea_antspreset_ants_wiki', ...
    'ants_metric', 'ANTS Neighborhood Cross Correlation', 'ants_strategy', 'BSplineSyN', ...
    'ants_usefa', 1, 'ants_numcores', '4', 'ants_scrf', 0, ...
    'ants_skullstripped', 1, 'ants_usepreexisting', 2, 'unrelated_setting', 42);
LEAD_D99_UI_TEST_PREFS = struct('machine', struct('normsettings', settings));
LEAD_D99_UI_TEST_SAVES = {};
test.TestData.figure = [];
end

function teardown(test)
if isgraphics(test.TestData.figure)
    delete(test.TestData.figure);
end
end

function testFixedRecipeAndBootstrap(test)
apref = ea_antspreset_macaque_d99_deep(struct('ants_metric', 'Global Correlation', 'ants_strategy', 'BSplineSyN'));
verifyEqual(test, apref.space, 'D99v2');
verifyEqual(test, apref.randomseed, 1);
verifyEqual(test, apref.float, 0);
verifyEqual(test, apref.interpolation, 'Linear');
verifyEqual(test, apref.deepMarginMm, 2);
verifyEqual(test, apref.affine, apref.rigid);
verifyEqual(test, apref.bootstrap.rigid, apref.rigid);
verifyEqual(test, apref.bootstrap.affine, apref.affine);
stages = {apref.rigid, apref.syn, apref.scrf, apref.bootstrap.syn};
expected = {
    '0.1', '1,32,Regular,0.25', '[1000x500x250x100,1e-6,10]', '12x8x4x2', '1.5x1x0.5x0.25mm';
    '0.1,3,0', '1,32,None,1', '[100x70x50x20,1e-6,10]', '8x4x2x1', '1x0.5x0.25x0mm';
    '0.1,3,1', '1,32,None,1', '[50x20,1e-6,10]', '2x1', '0.25x0mm';
    '0.1,3,1', '1,32,None,1', '[100x70x50,1e-6,10]', '8x4x2', '1x0.5x0.25mm'};
for index = 1:numel(stages)
    stage = stages{index};
    verifyEqual(test, stage.metric, 'MI');
    verifyEqual(test, {stage.gradientstep, stage.metricparams, stage.convergence, ...
        stage.shrinkfactors, stage.smoothingsigmas}, expected(index, :));
end
end

function testQueryAvoidsPreparation(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
before = LEAD_D99_UI_TEST_PREFS;
verifyEqual(test, ea_antspreset_macaque_d99_deep('query'), 'Macaque D99v2: Deep Nuclei (T1)');
verifyEqual(test, LEAD_D99_UI_TEST_PREFS, before);
verifyEmpty(test, LEAD_D99_UI_TEST_SAVES);
end

function testMenuDiscoveryAndOpeningDoesNotPersist(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
before = LEAD_D99_UI_TEST_PREFS;
handles = openSettings(test);
presets = getappdata(handles.pcpopup, 'funcell');
index = find(strcmp(presets, 'ea_antspreset_macaque_d99_deep'));
verifyNumElements(test, index, 1);
labels = get(handles.pcpopup, 'String');
verifyEqual(test, labels{index}, 'Macaque D99v2: Deep Nuclei (T1)');
verifyEqual(test, presets{get(handles.pcpopup, 'Value')}, 'ea_antspreset_ants_wiki');
verifyEqual(test, LEAD_D99_UI_TEST_PREFS, before);
verifyEmpty(test, LEAD_D99_UI_TEST_SAVES);
end

function testSelectingPresetLocksControlsWithoutSaving(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
before = LEAD_D99_UI_TEST_PREFS;
handles = openSettings(test);
selectPreset(handles, 'ea_antspreset_macaque_d99_deep');
verifyFixedControls(test, handles);
verifyEqual(test, LEAD_D99_UI_TEST_PREFS, before);
verifyEmpty(test, LEAD_D99_UI_TEST_SAVES);
end

function testLeavingPresetRestoresOrdinaryEditing(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
handles = openSettings(test);
selectPreset(handles, 'ea_antspreset_macaque_d99_deep');
selectPreset(handles, 'ea_antspreset_ants_wiki');
for name = {'strategy', 'metric', 'scrf', 'includefa', 'skullstripped', 'usepreexisting', 'restrcores', 'numcores'}
    verifyEqual(test, get(handles.(name{1}), 'Enable'), 'on');
end
set(handles.strategy, 'Value', 2);
set(handles.metric, 'Value', 3);
set(handles.scrf, 'Value', 0);
set(handles.includefa, 'Value', 1);
set(handles.skullstripped, 'Value', 1);
set(handles.usepreexisting, 'Value', 2);
set(handles.restrcores, 'Value', 0);
ea_normsettings_ants('restrcores_Callback', handles.restrcores, [], handles);
verifyEqual(test, get(handles.numcores, 'Enable'), 'off');
verifyEmpty(test, LEAD_D99_UI_TEST_SAVES);
ea_normsettings_ants('savebutn_Callback', handles.savebutn, [], handles);
saved = LEAD_D99_UI_TEST_PREFS.machine.normsettings;
verifyEqual(test, saved.ants_preset, 'ea_antspreset_ants_wiki');
verifyEqual(test, saved.ants_strategy, 'BSplineSyN');
verifyEqual(test, saved.ants_metric, 'Global Correlation');
verifyEqual(test, [saved.ants_scrf, saved.ants_usefa, saved.ants_skullstripped, saved.ants_usepreexisting, saved.ants_numcores], [0, 1, 1, 2, 0]);
end

function testSavedPresetOpensConstrainedWithoutSaving(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
LEAD_D99_UI_TEST_PREFS.machine.normsettings.ants_preset = 'ea_antspreset_macaque_d99_deep';
before = LEAD_D99_UI_TEST_PREFS;
handles = openSettings(test);
verifyFixedControls(test, handles);
verifyEqual(test, LEAD_D99_UI_TEST_PREFS, before);
verifyEmpty(test, LEAD_D99_UI_TEST_SAVES);
end

function testSavePersistsFixedSettings(test)
global LEAD_D99_UI_TEST_PREFS LEAD_D99_UI_TEST_SAVES;
handles = openSettings(test);
selectPreset(handles, 'ea_antspreset_macaque_d99_deep');
verifyEmpty(test, LEAD_D99_UI_TEST_SAVES);
ea_normsettings_ants('savebutn_Callback', handles.savebutn, [], handles);
verifyNumElements(test, LEAD_D99_UI_TEST_SAVES, 1);
saved = LEAD_D99_UI_TEST_PREFS.machine.normsettings;
verifyEqual(test, saved.ants_preset, 'ea_antspreset_macaque_d99_deep');
verifyEqual(test, saved.ants_strategy, 'SyN');
verifyEqual(test, saved.ants_metric, 'Mutual Information');
verifyEqual(test, [saved.ants_scrf, saved.ants_usefa, saved.ants_skullstripped, saved.ants_usepreexisting], [1, 0, 0, 3]);
verifyEqual(test, saved.ants_numcores, '1');
verifyEqual(test, saved.unrelated_setting, 42);
verifyFalse(test, isgraphics(test.TestData.figure));
end

function handles = openSettings(test)
ea_normsettings_ants('Visible', 'off');
figureHandle = findall(groot, 'Type', 'figure', 'Tag', 'setfig');
assert(isscalar(figureHandle));
test.TestData.figure = figureHandle;
handles = guidata(figureHandle);
end

function selectPreset(handles, preset)
presets = getappdata(handles.pcpopup, 'funcell');
set(handles.pcpopup, 'Value', find(strcmp(presets, preset), 1));
ea_normsettings_ants('pcpopup_Callback', handles.pcpopup, [], handles);
end

function verifyFixedControls(test, handles)
strategy = get(handles.strategy, 'String');
metric = get(handles.metric, 'String');
verifyEqual(test, strategy{get(handles.strategy, 'Value')}, 'SyN');
verifyEqual(test, metric{get(handles.metric, 'Value')}, 'Mutual Information');
verifyEqual(test, [get(handles.scrf, 'Value'), get(handles.includefa, 'Value'), ...
    get(handles.skullstripped, 'Value'), get(handles.usepreexisting, 'Value'), ...
    get(handles.restrcores, 'Value')], [1, 0, 0, 3, 1]);
verifyEqual(test, get(handles.numcores, 'String'), '1');
for name = {'strategy', 'metric', 'scrf', 'includefa', 'skullstripped', 'usepreexisting', 'restrcores', 'numcores'}
    verifyEqual(test, get(handles.(name{1}), 'Enable'), 'off');
end
end

function writeFixture(filename, content)
stream = fopen(filename, 'w');
fprintf(stream, '%s\n', content);
fclose(stream);
end
