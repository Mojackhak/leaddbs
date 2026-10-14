function tests = test_mixed_model_localization
% Runtime checks against real electrode templates; only image mapping is mocked.
tests = functiontests(localfunctions);
end

function setupOnce(test)
root = fileparts(fileparts(mfilename('fullpath')));
test.TestData.path = path;
addpath(root, fullfile(root, 'helpers'), fullfile(root, 'helpers', 'gui'), ...
    fullfile(root, 'helpers', 'seeg'), fullfile(root, 'templates', 'electrode_models'), ...
    fullfile(root, 'classes', 'ea_trajectory'), fullfile(root, 'common'));
folder = tempname;
mkdir(folder);
mocks = fullfile(folder, 'mapping');
mkdir(mocks);
writeFile(fullfile(mocks, 'ea_load_nii.m'), ...
    'function nii=ea_load_nii(filename), nii=struct(''mat'',eye(4),''fname'',filename); end');
writeFile(fullfile(mocks, 'ea_getspacedef.m'), ...
    'function s=ea_getspacedef, s.templates={''t1''}; end');
writeFile(fullfile(mocks, 'ea_space.m'), ...
    'function s=ea_space, s=''/private/tmp/mixed-template/''; end');
writeFile(fullfile(mocks, 'ea_map_coords.m'), ...
    ['function out=ea_map_coords(coords,~,transform,varargin)' newline ...
     'global LEAD_TEST_WARP; M=LEAD_TEST_WARP;' newline ...
     'if contains(transform,''forwardTransform''), M=inv(M); end' newline ...
     'out=M*[coords;ones(1,size(coords,2))]; out=out(1:3,:); end']);
writeFile(fullfile(mocks, 'ea_getptopts.m'), ...
    'function options=ea_getptopts(varargin), global LEAD_TEST_OPTIONS; options=LEAD_TEST_OPTIONS; end');
addpath(mocks, '-begin');
test.TestData.folder = folder;
test.TestData.root = root;
test.TestData.qa = fullfile(folder, 'qa');
mkdir(test.TestData.qa);
fprintf('LOCALIZATION_QA=%s\n', test.TestData.qa);
end

function teardownOnce(test)
path(test.TestData.path);
clear ea_load_nii ea_getspacedef ea_space ea_map_coords ea_getptopts;
end

function setup(test)
global LEAD_TEST_WARP;
LEAD_TEST_WARP = eye(4);
LEAD_TEST_WARP(1:3,4) = [5;-3;2];
folder = tempname(test.TestData.folder);
mkdir(folder);
options = struct('elmodels', {{'Medtronic 3389', 'Abbott Directed 6172 (short)', 'DIXI D08-12AM'}}, ...
    'elmodel', 'Medtronic 3389', 'sides', 1:3, 'native', 1, 'root', [folder, filesep], ...
    'patientname', 'sub-test', 'leadprod', 'dbs');
options.subj.subjDir = folder;
options.subj.subjId = 'test';
options.subj.recon.recon = fullfile(folder, 'sub-test_desc-reconstruction.mat');
options.subj.AnchorModality = 'T1w';
options.subj.coreg.anat.preop.T1w = fullfile(folder, 'anchor.nii');
options.subj.brainshift.transform.scrf = fullfile(folder, 'scrf.mat');
options.subj.norm.log.method = fullfile(folder, 'method.json');
writeFile(options.subj.norm.log.method, '{"method":"ANTs"}');
options.prefs = ea_prefs_default;
options.prefs.reco.saveACPC = false;
options.d3 = struct('write', false, 'writeatlases', false, 'elrendering', 1, 'hlactivecontacts', false, ...
    'mirrorsides', false, 'showactivecontacts', true, 'showpassivecontacts', true);
options.colorMacroContacts = [];
options = ea_resolve_elspec(options);
markers = repmat(struct('head', [], 'tail', [], 'x', [], 'y', []), 1, 3);
coords = cell(1,3);
for i = 1:3
    current = ea_resolve_elspec(options, i);
    model = load(fullfile(test.TestData.root, 'templates', 'electrode_models', current.elspec.matfname));
    offset = [20*(i-2), 8*i, 0];
    for field = {'head','tail','x','y'}
        markers(i).(field{1}) = model.electrode.([field{1}, '_position']) + offset;
    end
    coords{i} = model.electrode.coords_mm + offset;
end
[~,trajectory] = ea_resolvecoords(markers, options);
test.TestData.options = options;
test.TestData.markers = markers;
test.TestData.coords = coords;
test.TestData.trajectory = trajectory;
end

function testIndividualGeometry(test)
[c,~,m] = ea_resolvecoords(test.TestData.markers, test.TestData.options);
verifyEqual(test, cellfun(@(x) size(x,1), c), [4,8,12]);
for i = 1:3
    verifyEqual(test, c{i}, test.TestData.coords{i}, 'AbsTol', 1e-11);
    current = ea_resolve_elspec(test.TestData.options, i);
    verifyEqual(test, norm(m(i).x-m(i).head), current.elspec.lead_diameter/2, 'AbsTol', 1e-12);
end
end

function testSubsetGeometry(test)
options = test.TestData.options;
options.sides = [1,3];
[c,~,m] = ea_resolvecoords(test.TestData.markers, options, 1);
verifyEmpty(test, c{2});
verifyEqual(test, m(2), test.TestData.markers(2));
verifyEqual(test, size(c{3},1), 12);
end

function testSaveAndSingleElectrodeRefinement(test)
options = saveFixture(test);
before = load(options.subj.recon.recon);
markers = before.reco.native.markers;
for field = {'head','tail','x','y'}
    markers(3).(field{1}) = markers(3).(field{1}) + [1,2,0];
end
options.elside = 3;
ea_save_reconstruction(before.reco.native.coords_mm, before.reco.native.trajectory, markers, ...
    options.elmodel, 1, options);
after = load(options.subj.recon.recon);
verifyEqual(test, after.reco.props(1:2), before.reco.props(1:2));
verifyEqual(test, after.reco.native.coords_mm(1:2), before.reco.native.coords_mm(1:2));
verifyEqual(test, after.reco.native.markers(1:2), before.reco.native.markers(1:2));
verifyEqual(test, after.reco.native.coords_mm{3}, before.reco.native.coords_mm{3}+[1,2,0], 'AbsTol', 1e-11);
[c,~,~,model] = ea_load_reconstruction(options);
verifyEqual(test, model, options.elmodels{3});
verifyEqual(test, c, after.reco.native.coords_mm);
end

function testModelChangeIsLocal(test)
options = saveFixture(test);
before = load(options.subj.recon.recon);
options.elmodels{3} = 'Medtronic 3387';
options.elside = 3;
ea_save_reconstruction(before.reco.native.coords_mm, before.reco.native.trajectory, before.reco.native.markers, ...
    options.elmodel, 1, options);
after = load(options.subj.recon.recon);
verifyEqual(test, size(after.reco.native.coords_mm{3},1), 4);
verifyEmpty(test, after.reco.props(3).labels);
verifyEqual(test, after.reco.props(1:2), before.reco.props(1:2));
verifyEqual(test, after.reco.native.coords_mm(1:2), before.reco.native.coords_mm(1:2));
end

function testPartialScrfPreservesOtherElectrodes(test)
options = saveFixture(test);
saved = load(options.subj.recon.recon);
mat = eye(4); mat(1:3,4) = [2;1;-1];
before = ea_applyscrfmat(mat, saved.reco.native, 1:3);
changed = saved.reco.native;
changed.coords_mm{3} = changed.coords_mm{3} + [1,0,0];
after = ea_applyscrfmat(mat, changed, 3, before);
verifyEqual(test, after.coords_mm(1:2), before.coords_mm(1:2));
verifyEqual(test, after.markers(1:2), before.markers(1:2));
verifyEqual(test, after.coords_mm{3}, before.coords_mm{3}+[1,0,0], 'AbsTol', 1e-12);
end

function testSpaceRoundTripAndPartialPropagation(test)
options = saveFixture(test);
mat = eye(4); mat(1:3,4) = [2;1;-1];
save(options.subj.brainshift.transform.scrf, 'mat');
ea_reconstruction2mni(options);
before = load(options.subj.recon.recon);
for i = 1:3
    verifyEqual(test, before.reco.mni.coords_mm{i}, test.TestData.coords{i}+[7,-2,1], 'AbsTol', 1e-11);
    spec = ea_resolve_elspec(options, i);
    verifyEqual(test, norm(before.reco.mni.markers(i).x-before.reco.mni.markers(i).head), ...
        spec.elspec.lead_diameter/2, 'AbsTol', 1e-11);
end
options.sides = 3;
ea_reconstruction2native(options);
after = load(options.subj.recon.recon);
verifyEqual(test, after.reco.native.coords_mm{3}, test.TestData.coords{3}, 'AbsTol', 1e-11);
verifyEqual(test, after.reco.native.coords_mm(1:2), before.reco.native.coords_mm(1:2));
verifyEqual(test, after.reco.scrf.coords_mm(1:2), before.reco.scrf.coords_mm(1:2));
end

function testRepropagationPreservesImportedContacts(test)
global LEAD_TEST_OPTIONS;
options = saveFixture(test);
saved = load(options.subj.recon.recon);
reco = saved.reco;
reco.native.coords_mm{3}(5,1) = reco.native.coords_mm{3}(5,1)+0.2;
save(options.subj.recon.recon, 'reco');
LEAD_TEST_OPTIONS = options;
ea_recalc_reco([], [], options.subj.subjDir);
after = load(options.subj.recon.recon);
verifyEqual(test, after.reco.native.coords_mm, reco.native.coords_mm);
verifyEqual(test, {after.reco.props.elmodel}, options.elmodels);
verifyEqual(test, [after.reco.props.manually_corrected], [reco.props.manually_corrected]);
end

function testLeGUIImportPreservesLocationsAndLabels(test)
options = test.TestData.options;
source = makeImport(test);
reco = legui2reco(options, source, 'native');
verifyEqual(test, {reco.props.elmodel}, options.elmodels);
verifyEqual(test, [reco.props.manually_corrected], [1,1,1]);
verifyEqual(test, reco.native.coords_mm{3}(5,1), test.TestData.coords{3}(5,1)+0.2, 'AbsTol', 1e-12);
verifyEqual(test, reco.props(2).labels{8}, 'B8');
verifyTrue(test, iscell(reco.native.trajectory));
verifyTrue(test, iscell(reco.mni.trajectory));
verifyEqual(test, cellfun(@(x) size(x,1), reco.native.coords_mm), [4,8,12]);
end

function testLeGUIReimportSubsetPreservesOtherElectrode(test)
options = saveFixture(test);
ea_reconstruction2mni(options);
before = load(options.subj.recon.recon);
options.sides = [1,3];
source = makeImport(test);
reco = legui2reco(options, source, 'native');
verifyEqual(test, reco.native.coords_mm{2}, before.reco.native.coords_mm{2});
verifyEqual(test, reco.mni.coords_mm{2}, before.reco.mni.coords_mm{2});
verifyEqual(test, reco.props(2), before.reco.props(2));
end

function testLeGUIMismatchedModelFailsBeforeSave(test)
options = test.TestData.options;
options.elmodels{2} = 'Medtronic 3389';
source = makeImport(test);
verifyError(test, @() legui2reco(options, source, 'native'), 'LeadDBS:LeGUIModelMismatch');
verifyFalse(test, isfile(options.subj.recon.recon));
end

function testSlicerShuffledSubsetAndLps(test)
filename = fullfile(test.TestData.options.subj.subjDir, 'fiducials.fcsv');
writeFile(filename, ['# Markups fiducial file version = 4.7' newline '# CoordinateSystem = 1' newline ...
    '# columns = id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID' newline ...
    'a,-3,-4,9,0,0,0,1,1,1,0,Tail_3,,' newline ...
    'b,-1,-2,0,0,0,0,1,1,1,0,Head_1,,' newline ...
    'c,-3,-4,0,0,0,0,1,1,1,0,Head_3,,' newline ...
    'd,-1,-2,6,0,0,0,1,1,1,0,Tail_1,,' newline]);
markers = ea_read_slicer_fiducials(filename, [1,3]);
verifyEqual(test, markers(3).tail, [3,4,9]);
verifyEqual(test, markers(1).head, [1,2,0]);
verifyEmpty(test, markers(2).head);
verifyError(test, @() ea_read_slicer_fiducials(filename, [1,2,3]), 'LeadDBS:InvalidFiducials');
end

function testUnsupportedAlgorithmsAreRejected(test)
options = test.TestData.options;
for method = {'TRAC/CORE (Horn 2015)', 'Refined TRAC/CORE', 'PaCER (Husch 2017)'}
    verifyError(test, @() ea_check_localization_method(options, method{1}), 'LeadDBS:UnsupportedMultiElectrodeMethod');
end
verifyError(test, @() ea_runpacer(options), 'LeadDBS:UnsupportedMultiElectrodeMethod');
verifyError(test, @() ea_runtraccore(options), 'LeadDBS:UnsupportedMultiElectrodeMethod');
options.elmodels = {'Medtronic 3389','Medtronic 3389'};
options.sides = [1,2];
ea_check_localization_method(options, 'PaCER (Husch 2017)');
end

function testSetupPersistenceBeyondNumberedButtons(test)
[handles,bids] = makeHandles(test);
cleanup = onCleanup(@() delete(handles.leadfigure));
models = repmat({'Medtronic 3389'}, 1,16);
models(2:3) = test.TestData.options.elmodels(2:3);
ea_set_electrode_models(handles, models, [1,3,16]);
ea_storeui(handles);
saved = load(bids.getPrefs('test','uiprefs','mat'));
verifyEqual(test, saved.elmodels, models);
verifyEqual(test, saved.sides, [1,3,16]);
verifyEqual(test, handles.electrode_model_popup.Enable, 'off');
verifyEqual(test, handles.reconmethod.String, {'Manual';'Slicer (Manual)';'LeGUI (Davis 2021)'});
end

function testCoordinateExportPreservesIdentity(test)
options = saveFixture(test);
filename = fullfile(options.subj.subjDir, 'contacts.fcsv');
ea_exportfiducials(options, filename);
contents = fileread(filename);
verifyTrue(test, contains(contents, 'E2_B8'));
verifyTrue(test, contains(contents, 'E3_C12'));
verifyEqual(test, numel(regexp(contents, 'vtkMRMLMarkupsFiducialNode_', 'match')), 24);
end

function testSingleSubjectRenderingUsesEachModel(test)
options = saveFixture(test);
fig = figure('Visible','off','Color','w');
cleanup = onCleanup(@() delete(fig));
axes(fig); view(35,22); axis equal; hold on;
[rendered,~,sides] = ea_renderelstruct(options, fig);
verifyEqual(test, sides, 1:3);
verifyEqual(test, {rendered.elmodel}, options.elmodels);
for i = 1:3
    contacts = findobj(fig, '-regexp', 'Tag', sprintf('^sub-test_Contact\\d+_Side%d$', i));
    current = ea_resolve_elspec(options, i);
    template = load(fullfile(test.TestData.root, 'templates', 'electrode_models', current.elspec.matfname));
    verifyEqual(test, numel(contacts), numel(template.electrode.contacts));
    verifyEqual(test, size(rendered(i).elstruct.coords_mm{i},1), current.elspec.numContacts);
end
labels = getappdata(fig,'eltext');
verifyEqual(test, get(labels(2,8), 'String'), 'B8');
verifyEqual(test, get(labels(3,12), 'String'), 'C12');
xlabel('x (mm)'); ylabel('y (mm)'); zlabel('z (mm)');
title('Three independently modeled electrodes: 4, 8, and 12 contacts');
exportgraphics(fig, fullfile(test.TestData.qa,'scene.png'), 'Resolution', 160);
end

function testHorizontalImportAndMarkerFrames(test)
options = test.TestData.options;
source = makeImport(test);
data = load(source);
third = startsWith(data.ElecMapRaw, 'C');
z = data.ElecXYZRaw(third,3);
data.ElecXYZRaw(third,:) = [z, 24*ones(size(z)), zeros(size(z))];
save(source, '-struct', 'data');
reco = legui2reco(options, source, 'native');
verifyTrue(test, all(isfinite([reco.native.markers(3).x,reco.native.markers(3).y])));
for axis = [1,2]
    tail = zeros(1,3); tail(axis) = 1;
    [x,y] = ea_calcxy([0,0,0], tail);
    [rx,ry] = ea_calcxy([0,0,0], tail, y);
    verifyEqual(test, [norm(x),norm(y),dot(x,y),dot(x,tail),dot(y,tail)], [1,1,0,0,0], 'AbsTol', 1e-12);
    verifyTrue(test, all(isfinite([rx,ry])));
end
end

function testCustomConfigurationTable(test)
[handles,bids] = makeHandles(test);
cleanup = onCleanup(@() delete(handles.leadfigure));
action = timer('StartDelay',1,'TimerFcn',@(~,~) applySetup(test.TestData.qa));
timeout = timer('StartDelay',20,'TimerFcn',@(~,~) delete(findall(0,'Tag','electrode_setup')));
timerCleanup = onCleanup(@() delete([action,timeout]));
start(action); start(timeout);
selection = ea_multiple_electrodes(handles,bids);
stop(timeout);
verifyFalse(test, selection.canceled);
verifyEqual(test, selection.count, 16);
verifyEqual(test, selection.models{3}, 'DIXI D08-12AM');
settings = load(bids.getPrefs('test','uiprefs','mat'));
verifyEqual(test, settings.sides, [1,3,16]);
end

function testManualRefinementSwitchAndFinish(test)
options = saveFixture(test);
ea_reconstruction2mni(options);
before = load(options.subj.recon.recon);
options = phantomOptions(options);
options.elside = 1;
options.verbose = 3;
options.autoimprove = false;
options.d2.write = false;
fig = figure('Visible','off');
cleanup = onCleanup(@() deleteIfGraphics(fig));
ea_manualreconstruction(fig, options.patientname, options);
verifyEqual(test, numel(getappdata(fig,'elplot')), 4);
pressKey(fig,'','uparrow');
pressKey(fig,' ','space');
verifyEqual(test, numel(getappdata(fig,'elplot')), 8);
verifyEqual(test, string(get(getappdata(fig,'orientationtools'), 'Enable')), repmat("on",3,1));
pressKey(fig,' ','space');
verifyEqual(test, numel(getappdata(fig,'elplot')), 12);
verifyEqual(test, string(get(getappdata(fig,'orientationtools'), 'Enable')), repmat("off",3,1));
pressKey(fig,'','uparrow');
exportgraphics(fig, fullfile(test.TestData.qa,'editor.png'), 'Resolution', 130);
pressKey(fig,' ','space');
verifyFalse(test, isgraphics(fig));
after = load(options.subj.recon.recon);
verifyEqual(test, after.reco.native.coords_mm{2}, before.reco.native.coords_mm{2}, 'AbsTol',1e-11);
verifyEqual(test, after.reco.mni.coords_mm{2}, before.reco.mni.coords_mm{2});
for i = [1,3]
    verifyNotEqual(test, after.reco.native.coords_mm{i}, before.reco.native.coords_mm{i});
    verifyEqual(test, after.reco.mni.coords_mm{i}, after.reco.native.coords_mm{i}+[5,-3,2], 'AbsTol',1e-10);
end
end

function testNamedFirstPartialImportUsesConfiguredIndex(test)
options = test.TestData.options;
options.elnames = {'A','B','C'};
options.sides = 3;
source = makeImport(test);
data = load(source);
keep = startsWith(data.ElecMapRaw,'C');
data.ElecMapRaw = data.ElecMapRaw(keep,:);
data.ElecXYZRaw = data.ElecXYZRaw(keep,:);
data.DepthElecRaw = true(nnz(keep),1);
save(source,'-struct','data');
reco = legui2reco(options,source,'native');
verifyEmpty(test, reco.native.coords_mm{1});
verifyEmpty(test, reco.native.coords_mm{2});
verifyEqual(test, size(reco.native.coords_mm{3},1), 12);
verifyEqual(test, reco.props(3).elname, 'C');
[~,~,~,model,corrected] = ea_load_reconstruction(options);
verifyEqual(test, model, options.elmodels{3});
verifyEqual(test, corrected, 1);
end

function testAmbiguousPartialImportIsRejected(test)
options = test.TestData.options;
source = makeImport(test);
data = load(source);
keep = startsWith(data.ElecMapRaw,'C');
data.ElecMapRaw = data.ElecMapRaw(keep,:);
data.ElecXYZRaw = data.ElecXYZRaw(keep,:);
data.DepthElecRaw = true(nnz(keep),1);
save(source,'-struct','data');
verifyError(test,@() legui2reco(options,source,'native'),'LeadDBS:AmbiguousElectrodeImport');
verifyFalse(test,isfile(options.subj.recon.recon));
end

function testHomogeneousBilateralScalarInterface(test)
options = test.TestData.options;
options = rmfield(options,'elmodels');
options.sides = [1,2];
markers = test.TestData.markers(1:2);
for field = {'head','tail','x','y'}
    markers(2).(field{1}) = markers(1).(field{1}) + [40,8,0];
end
[c,t] = ea_resolvecoords(markers, options);
ea_save_reconstruction(c,t,markers,options.elmodel,0,options);
[c2,~,~,model] = ea_load_reconstruction(options);
verifyEqual(test,c2,c);
verifyEqual(test,model,options.elmodel);
verifyEqual(test,cellfun(@(x)size(x,1),c2),[4,4]);
ea_check_localization_method(options,'PaCER (Husch 2017)');
fig = figure('Visible','off');
cleanup = onCleanup(@() delete(fig));
axes(fig); hold on;
rendered = ea_renderelstruct(options,fig);
verifyEqual(test,{rendered.elmodel},{options.elmodel,options.elmodel});
end

function testManualInitialLocalizationUsesEachTemplate(test)
options = phantomOptions(test.TestData.options);
folder = fullfile(options.subj.subjDir,'manual_clicks'); mkdir(folder);
writeFile(fullfile(folder,'spm_input.m'), ...
    'function answer=spm_input(prompt,varargin), answer=~strcmp(prompt,''Adjust contrast''); end');
writeFile(fullfile(folder,'spm_orthviews.m'), ...
    ['function result=spm_orthviews(command,varargin)' newline ...
     'global LEAD_TEST_CLICKS; result=[];' newline ...
     'if strcmp(command,''Pos''), result=LEAD_TEST_CLICKS(1,:)''; LEAD_TEST_CLICKS(1,:)=[];' newline ...
     'elseif strcmp(command,''Image''), axes; result=1; end; end']);
originalPath = path;
cleanup = onCleanup(@() restoreManualMocks(originalPath));
addpath(folder,'-begin');
global LEAD_TEST_CLICKS;
LEAD_TEST_CLICKS = zeros(6,3);
for i = 1:3
    LEAD_TEST_CLICKS(2*i-1,:) = test.TestData.markers(i).head;
    LEAD_TEST_CLICKS(2*i,:) = test.TestData.markers(i).head+[0,0,20];
end
[c,~,markers] = ea_runmanual(options);
verifyEqual(test,cellfun(@(x)size(x,1),c),[4,8,12]);
for i = 1:3
    verifyEqual(test,c{i},test.TestData.coords{i},'AbsTol',1e-11);
    verifyEqual(test,markers(i).tail,test.TestData.markers(i).tail,'AbsTol',1e-11);
end
end

function testThirdElectrodeSliceDisplayAndExport(test)
options = saveFixture(test);
options = phantomOptions(options);
options.sides = 3;
options.d2 = struct('backdrop',options.subj.coreg.anat.postop.ax_MRI, 'writeatlases',false, ...
    'bbsize',15,'fid_overlay',true,'showlegend',false);
options.d3.showisovolume = false;
options.atlasset = 'Use none';
folder = fullfile(options.subj.subjDir,'capture'); mkdir(folder);
writeFile(fullfile(folder,'ea_screenshot.m'), ...
    'function ea_screenshot(filename,varargin), frame=getframe(gcf); imwrite(frame.cdata,filename); end');
originalPath = path;
cleanup = onCleanup(@() restoreScreenshot(originalPath));
addpath(folder,'-begin');
ea_writeplanes(options);
export = fullfile(options.root,options.patientname,'export','2D');
images = dir(fullfile(export,'*_E3_C*.png'));
verifyEqual(test,numel(images),36);
log = fileread(fullfile(export,[options.patientname,'_desc-2D_viewplane.txt']));
verifyTrue(test,contains(log,'E3_C12'));
verifyTrue(test,contains(log,'39.5 mm'));
copyfile(fullfile(export,[options.patientname,'_desc-2D_view-ax_E3_C12.png']),fullfile(test.TestData.qa,'slice.png'));
end

function restoreManualMocks(originalPath)
path(originalPath); clear spm_input spm_orthviews;
end

function restoreScreenshot(originalPath)
path(originalPath); clear ea_screenshot;
end

function testUnselectedAnglesArePreserved(test)
options = saveFixture(test);
saved = load(options.subj.recon.recon); reco = saved.reco;
reco.angles.native(2).roll = 42;
reco.angles.orientationmethod{2} = 'accepted';
save(options.subj.recon.recon,'reco');
markers = reco.native.markers;
for field = {'head','tail','x','y'}
    markers(3).(field{1}) = markers(3).(field{1})+[0,0,1];
end
options.elside = 3;
ea_save_reconstruction(reco.native.coords_mm,reco.native.trajectory,markers,options.elmodel,1,options);
after = load(options.subj.recon.recon);
verifyEqual(test,after.reco.angles.native(2),reco.angles.native(2));
verifyEqual(test,after.reco.angles.orientationmethod{2},'accepted');
end

function testMarkerMetadataDoesNotRegenerateContacts(test)
options = saveFixture(test);
saved = load(options.subj.recon.recon); reco = saved.reco;
for i = 1:3, reco.native.markers(i).note = 'original'; end
reco.native.coords_mm{3}(5,1) = reco.native.coords_mm{3}(5,1)+0.2;
save(options.subj.recon.recon,'reco');
markers = reco.native.markers; markers(3).note = 'updated';
options.elside = 3;
options.elnames = {'Electrode 1','Electrode 2','Electrode 3'};
changed = ea_save_reconstruction(reco.native.coords_mm,reco.native.trajectory,markers,options.elmodel,1,options);
after = load(options.subj.recon.recon);
verifyEmpty(test,changed);
verifyEqual(test,after.reco.native.coords_mm,reco.native.coords_mm);
verifyEqual(test,after.reco.props(3).elname,'C');
end

function testExternalImportHonorsDeclaredMniSpace(test)
global LEAD_TEST_OPTIONS;
options = test.TestData.options;
LEAD_TEST_OPTIONS = options;
source = makeImport(test); data = load(source);
data.ElecXYZMNIRaw = data.ElecXYZRaw+[5,-3,2];
data.ElecXYZMNIProjRaw = data.ElecXYZMNIRaw+1000;
data.ElecXYZRaw = data.ElecXYZRaw+2000;
folder = fullfile(options.subj.subjDir,'legui'); mkdir(folder); mkdir(fullfile(folder,'Registered'));
source = fullfile(folder,'Registered','Electrodes.mat');
save(source,'-struct','data');
ea_import_LeGUI(options.subj.subjDir,'sub-test',folder,'mni');
after = load(options.subj.recon.recon);
verifyEqual(test,after.reco.native.coords_mm{1},test.TestData.coords{1},'AbsTol',1e-11);
verifyEqual(test,after.reco.mni.coords_mm{1},test.TestData.coords{1}+[5,-3,2],'AbsTol',1e-11);
verifyEqual(test,load(source),data);
end

function testDirectionalControlsUpdateOnlyCurrentElectrode(test)
options = saveFixture(test);
ea_reconstruction2mni(options);
before = load(options.subj.recon.recon);
options = phantomOptions(options); options.sides = 2; options.elside = 2;
options.verbose = 3; options.autoimprove = false; options.d2.write = false;
fig = figure('Visible','off'); cleanup = onCleanup(@() deleteIfGraphics(fig));
ea_manualreconstruction(fig,options.patientname,options);
tools = getappdata(fig,'orientationtools');
other = figure('Visible','off'); otherCleanup = onCleanup(@() deleteIfGraphics(other));
callback = get(tools(2),'ClickedCallback');
feval(callback{1},tools(2),[],callback{2:end});
folder = fullfile(options.subj.subjDir,'angle_entry'); mkdir(folder);
writeFile(fullfile(folder,'inputdlg.m'),'function answer=inputdlg(varargin), answer={''30''}; end');
originalPath = path; restore = onCleanup(@() restoreAngleInput(originalPath));
addpath(folder,'-begin');
callback = get(tools(1),'ClickedCallback');
feval(callback{1},tools(1),[],callback{2:end});
pressKey(fig,' ','space');
after = load(options.subj.recon.recon);
verifyEqual(test,after.reco.native.coords_mm([1,3]),before.reco.native.coords_mm([1,3]));
verifyEqual(test,after.reco.mni.coords_mm([1,3]),before.reco.mni.coords_mm([1,3]));
verifyEqual(test,after.reco.angles.native(2).roll,30,'AbsTol',1e-10);
verifyEqual(test,after.reco.mni.coords_mm{2},after.reco.native.coords_mm{2}+[5,-3,2],'AbsTol',1e-10);
verifyEqual(test,after.reco.angles.orientationmethod{2},'manual');
end

function testRefinementLoadsStoredIndexedModels(test)
options = saveFixture(test);
options = rmfield(options,'elmodels');
options = phantomOptions(options); options.sides = 3; options.elside = 3;
options.verbose = 3; options.autoimprove = false; options.d2.write = false;
fig = figure('Visible','off'); cleanup = onCleanup(@() deleteIfGraphics(fig));
ea_manualreconstruction(fig,options.patientname,options);
current = getappdata(fig,'options');
verifyEqual(test,current.elmodels,test.TestData.options.elmodels);
verifyEqual(test,numel(getappdata(fig,'elplot')),12);
end

function restoreAngleInput(originalPath)
path(originalPath); clear inputdlg;
end

function testEquivalentModelNamesDoNotRegenerateGeometry(test)
options = saveFixture(test);
saved = load(options.subj.recon.recon); reco = saved.reco;
reco.props(2).elmodel = 'St. Jude Directed 6172 (short)';
save(options.subj.recon.recon,'reco');
options.elside = 2;
changed = ea_save_reconstruction(reco.native.coords_mm,reco.native.trajectory,reco.native.markers,options.elmodel,1,options);
after = load(options.subj.recon.recon);
verifyEmpty(test,changed);
verifyEqual(test,after.reco.native.coords_mm,reco.native.coords_mm);
verifyEqual(test,after.reco.props(2).labels,reco.props(2).labels);
options.elmodels = {'Abbott Directed 6172 (short)','St. Jude Directed 6172 (short)'};
options.sides = [1,2];
ea_check_localization_method(options,'PaCER (Husch 2017)');
end

function testEquivalentConfigurationVectorSerialization(test)
options = test.TestData.options;
options.elmodels = options.elmodels';
options.elnames = {'Electrode 1';'Electrode 2';'Electrode 3'};
source = makeImport(test);
reco = legui2reco(options,source,'native');
verifyEqual(test,{reco.props.elmodel},test.TestData.options.elmodels);
verifyEqual(test,reco.props(3).elname,'C');
end

function options = phantomOptions(options)
filename = fullfile(options.subj.subjDir,'phantom.nii');
[x,y,z] = ndgrid(single(1:128));
image = exp(-((x-64).^2+(y-64).^2+(z-64).^2)/3000);
V = struct('fname',filename,'dim',[128,128,128],'dt',[16,0],'mat',eye(4),'pinfo',[1;0;0],'descrip','Synthetic localization fixture');
V.mat(1:3,4) = [-64;-64;-32];
spm_write_vol(V,image);
options.subj.postopModality = 'MRI';
options.subj.coreg.anat.postop.ax_MRI = filename;
end

function pressKey(fig,character,key)
event = struct('Character',character,'Key',key,'Modifier',{{}});
callback = get(fig,'KeyPressFcn');
callback(fig,event);
end

function applySetup(qa)
fig = findall(0,'Tag','electrode_setup');
count = findobj(fig,'Tag','electrode_count');
count.String = '16';
callback = count.Callback; callback(count,[]);
list = findobj(fig,'Tag','electrode_models');
data = list.Data;
data(:,1) = {false}; data([1,3,16],1) = {true};
data(1:3,2) = {'A';'B';'C'};
data{2,3} = 'Abbott Directed 6172 (short)';
data{3,3} = 'DIXI D08-12AM';
list.Data = data;
frame = getframe(fig);
imwrite(frame.cdata,fullfile(qa,'setup.png'));
apply = findobj(fig,'Tag','electrode_apply');
callback = apply.Callback; callback(apply,[]);
end

function deleteIfGraphics(fig)
if isgraphics(fig), delete(fig); end
end

function options = saveFixture(test)
options = test.TestData.options;
ea_save_reconstruction(test.TestData.coords, test.TestData.trajectory, test.TestData.markers, ...
    options.elmodel, 0, options);
saved = load(options.subj.recon.recon);
reco = saved.reco;
for i = 1:3
    name = char('A'+i-1);
    reco.props(i).elname = name;
    reco.props(i).labels = arrayfun(@(j) sprintf('%s%d',name,j), 1:size(test.TestData.coords{i},1), 'UniformOutput',false)';
    reco.props(i).manually_corrected = mod(i,2);
end
save(options.subj.recon.recon, 'reco');
end

function filename = makeImport(test)
ElecXYZRaw = vertcat(test.TestData.coords{:});
ElecXYZRaw(4+8+5,1) = ElecXYZRaw(4+8+5,1)+0.2;
ElecMapRaw = cell(24,1);
first = 1;
for i = 1:3
    count = size(test.TestData.coords{i},1);
    for j = 1:count
        ElecMapRaw{first+j-1} = sprintf('%s%d',char('A'+i-1),j);
    end
    first = first+count;
end
order = 24:-1:1;
ElecXYZRaw = ElecXYZRaw(order,:);
ElecMapRaw = ElecMapRaw(order,:);
DepthElecRaw = true(24,1);
filename = fullfile(test.TestData.options.subj.subjDir,'electrodes.mat');
save(filename, 'ElecXYZRaw','ElecMapRaw','DepthElecRaw');
end

function [handles,bids] = makeHandles(test)
handles.leadfigure = figure('Visible','off');
handles.prod = 'dbs';
handles.datasetselect = uicontrol(handles.leadfigure, 'Style','pushbutton','String',test.TestData.options.subj.subjDir);
handles.patdir_choosebox = uicontrol(handles.leadfigure, 'Style','edit','String',test.TestData.options.subj.subjDir);
handles.electrode_model_popup = uicontrol(handles.leadfigure, 'Style','popupmenu','String',ea_resolve_elspec,'Value',1);
handles.reconmethod = uicontrol(handles.leadfigure, 'Style','popupmenu','String',{'Manual','PaCER (Husch 2017)'},'Value',1);
for i = 1:15
    handles.(['side',num2str(i)]) = uicontrol(handles.leadfigure,'Style','checkbox','Value',i<=2);
end
bids.getPrefs = @(varargin) fullfile(test.TestData.options.subj.subjDir,'prefs.mat');
bids.getRecon = @(varargin) struct('recon',test.TestData.options.subj.recon.recon);
setappdata(handles.leadfigure,'bids',bids);
setappdata(handles.leadfigure,'subjId',{'test'});
setappdata(handles.leadfigure,'uipatdir',{test.TestData.options.subj.subjDir});
end

function writeFile(filename, contents)
fid = fopen(filename,'w');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid,'%s',contents);
end
