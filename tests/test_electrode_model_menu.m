function tests = test_electrode_model_menu
tests = functiontests(localfunctions);
end

function setupOnce(test)
root = fileparts(fileparts(mfilename('fullpath')));
test.TestData.path = path;
addpath(root, fullfile(root, 'helpers', 'gui'), fullfile(root, 'ext_libs', 'cprintf'));
end

function teardownOnce(test)
path(test.TestData.path);
end

function setup(test)
handles.leadfigure = uifigure('Visible', 'off');
test.TestData.figure = handles.leadfigure;
tabs = uitabgroup(handles.leadfigure);
handles.registrationtab = uitab(tabs);
handles.localizationtab = uitab(tabs);
handles.optionaltab = uitab(tabs);
menu = uidropdown(handles.localizationtab, 'Items', fullMethods);
handles.reconmethod = appdesigner.appmigration.UIControlPropertiesConverter(menu);
models = {'Medtronic 3389', 'Abbott Directed 6172 (short)'};
popup = uidropdown(handles.localizationtab, 'Items', models);
handles.electrode_model_popup = appdesigner.appmigration.UIControlPropertiesConverter(popup);
for side = 1:15
    button = uicheckbox(handles.localizationtab);
    handles.(['side', num2str(side)]) = appdesigner.appmigration.UIControlPropertiesConverter(button);
end
handles.overwriteapproved = uicheckbox(handles.leadfigure);
handles.MRCT = appdesigner.appmigration.UIControlPropertiesConverter( ...
    uidropdown(handles.registrationtab, 'Items', {'MRI', 'CT', 'No postoperative scan'}));
handles.targetpopup = appdesigner.appmigration.UIControlPropertiesConverter( ...
    uidropdown(handles.localizationtab, 'Items', {'STN, GPi or ViM', 'Manual'}));
handles.atlassetpopup = appdesigner.appmigration.UIControlPropertiesConverter( ...
    uidropdown(handles.optionaltab, 'Items', {'Use none'}));
handles.patientlist = struct('Data', table({'test'}, 'VariableNames', {'subjId'}), 'Selection', 1);
prefsFile = [tempname, '.mat'];
bids.getPrefs = @(varargin) prefsFile;
setappdata(handles.leadfigure, 'bids', bids);
setappdata(handles.leadfigure, 'subjId', {'test'});
test.TestData.handles = handles;
test.TestData.menu = menu;
test.TestData.prefsFile = prefsFile;
end

function teardown(test)
delete(test.TestData.figure);
end

function testRestrictionPreservesMethodNames(test)
handles = test.TestData.handles;
allowed = {'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
expected = [1, 1, 1, 1, 2, 3];
configurations = {{'Medtronic 3389', 'Abbott Directed 6172 (short)'}, ...
    {'Medtronic 3389', 'Medtronic 3389', 'Medtronic 3389'}};
for configuration = configurations
    for method = 1:6
        ea_set_electrode_models(handles, {}, []);
        handles.reconmethod.Value = method;
        ea_set_electrode_models(handles, configuration{1}, 1:numel(configuration{1}));
        verifyEqual(test, handles.reconmethod.String(:), allowed(:));
        verifyEqual(test, handles.reconmethod.Value, expected(method));
        verifyEqual(test, test.TestData.menu.Items(:), allowed(:));
        verifyEqual(test, test.TestData.menu.Value, allowed{expected(method)});
        verifyEqual(test, handles.electrode_model_popup.Enable, 'off');
    end
end
end

function testHomogeneousMenuRestoresMethodNames(test)
handles = test.TestData.handles;
allowed = {'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
methods = fullMethods;
for method = 1:3
    ea_set_electrode_models(handles, {'Medtronic 3389', 'Abbott Directed 6172 (short)'}, [1, 2]);
    handles.reconmethod.Value = method;
    ea_set_electrode_models(handles, {'Medtronic 3389', 'Medtronic 3389'}, [1, 2]);
    verifyEqual(test, handles.reconmethod.String(:), methods(:));
    verifyEqual(test, handles.reconmethod.Value, method + 3);
    verifyEqual(test, test.TestData.menu.Items(:), methods(:));
    verifyEqual(test, test.TestData.menu.Value, allowed{method});
    verifyEqual(test, handles.electrode_model_popup.Enable, 'on');
end
end

function testRepeatedPreferenceReloadPreservesSavedMethod(test)
handles = test.TestData.handles;
allowed = {'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
options = mixedOptions;
handles.reconmethod.Value = 6;
for method = 1:3
    options.reconmethod = allowed{method};
    save(test.TestData.prefsFile, '-struct', 'options');
    for reload = 1:2
        ea_getui(handles);
        verifyEqual(test, handles.reconmethod.Value, method);
        verifyEqual(test, test.TestData.menu.Value, allowed{method});
        verifyEqual(test, getappdata(handles.leadfigure, 'elmodels'), options.elmodels);
        verifyEqual(test, getappdata(handles.leadfigure, 'elnames'), options.elnames);
        verifyEqual(test, [handles.side1.Value, handles.side2.Value, handles.side3.Value], [1, 0, 1]);
    end
end
end

function testUnavailableAtlasDoesNotPreventPreferenceReload(test)
handles = test.TestData.handles;
options = mixedOptions;
options.reconmethod = 'Slicer (Manual)';
options.atlasset = 'DISTAL Minimal (Ewert 2017)';
save(test.TestData.prefsFile, '-struct', 'options');
handles.reconmethod.Value = 5;
output = evalc('ea_getui(handles);');
verifyTrue(test, contains(output, 'Specified atlas not found: DISTAL Minimal (Ewert 2017)'));
verifyEqual(test, handles.atlassetpopup.String, {'Use none'});
verifyEqual(test, handles.atlassetpopup.Value, 1);
verifyEqual(test, test.TestData.menu.Value, 'Slicer (Manual)');
end

function methods = fullMethods
methods = {'TRAC/CORE (Horn 2015)', 'Refined TRAC/CORE', 'PaCER (Husch 2017)', ...
    'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
end

function options = mixedOptions
options = struct('modality', 1, 'elmodels', ...
    {{'Medtronic 3389', 'Abbott Directed 6172 (short)', 'Medtronic 3389'}}, ...
    'elnames', {{'A', 'B', 'C'}}, 'sides', [1, 3]);
end

function testListValuedMethodKeepsCurrentSelection(test)
handles = test.TestData.handles;
methods = {'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'};
for stored = {methods, methods'}
    options = struct('modality', 2, 'sides', []);
    options.reconmethod = stored{1};
    save(test.TestData.prefsFile, '-struct', 'options');
    handles.reconmethod.Value = 4;
    output = evalc('ea_getui(handles);');
    verifyTrue(test, contains(output, 'Saved reconstruction method contains multiple names'));
    verifyEqual(test, test.TestData.menu.Value, 'Manual');
end
end

function testScalarCellAndStringMethodsLoad(test)
handles = test.TestData.handles;
for stored = {{'Slicer (Manual)'}, "SLICER (MANUAL)"}
    options = mixedOptions;
    options.reconmethod = stored{1};
    save(test.TestData.prefsFile, '-struct', 'options');
    ea_getui(handles);
    verifyEqual(test, test.TestData.menu.Value, 'Slicer (Manual)');
end
end

function testSavingOptionsStoresOnlySelectedName(test)
handles = test.TestData.handles;
handles.reconmethod.Value = 4;
options = ea_handles2options(handles);
verifyEqual(test, options.reconmethod, 'Manual');
legacyFigure = figure('Visible', 'off');
cleanup = onCleanup(@() delete(legacyFigure));
handles.reconmethod = uicontrol(legacyFigure, 'Style', 'popupmenu', ...
    'String', {'Manual', 'Slicer (Manual)', 'LeGUI (Davis 2021)'}, 'Value', 6);
options = ea_handles2options(handles);
verifyFalse(test, isfield(options, 'reconmethod'));
end

function testImplicitModalityRefreshPreservesLoadedMethod(test)
handles = test.TestData.handles;
handles.prod = 'dbs';
handles.statusone = appdesigner.appmigration.UIControlPropertiesConverter(uilabel(handles.leadfigure));
handles.doreconstruction = uicheckbox(handles.leadfigure);
handles.refinelocalization = uicheckbox(handles.leadfigure);
handles.maskwindow_txt = uieditfield(handles.leadfigure);
setappdata(handles.leadfigure, 'subjId', {'test', 'second'});
bids = getappdata(handles.leadfigure, 'bids');
bids.settings.reco.method.CT = 'PaCER (Husch 2017)';
setappdata(handles.leadfigure, 'bids', bids);
handles.reconmethod.Value = 4;
ea_switchctmr(handles);
verifyEqual(test, test.TestData.menu.Value, 'Manual');
ea_switchctmr(handles, 2);
verifyEqual(test, test.TestData.menu.Value, 'PaCER (Husch 2017)');
end
