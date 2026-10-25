function tests = test_group_multielectrode_display
tests = functiontests(localfunctions);
end

function setupOnce(test)
root = fileparts(fileparts(mfilename('fullpath')));
test.TestData.path = path;
test.TestData.root = root;
addpath(root, fullfile(root,'helpers'), fullfile(root,'helpers','group'), ...
    fullfile(root,'helpers','gui'), fullfile(root,'common'), ...
    fullfile(root,'classes','ea_trajectory'), fullfile(root,'templates','electrode_models'));
test.TestData.folder = tempname;
mkdir(test.TestData.folder);
end

function teardownOnce(test)
path(test.TestData.path);
end

function setup(test)
subject = fullfile(tempname(test.TestData.folder), 'sub-eight');
mkdir(fullfile(subject,'reconstruction'));
models = {'Medtronic 3389','Abbott Directed 6172 (short)','DIXI D08-12AM'};
o = struct('elmodels', {models(mod(0:7,3)+1)}, 'elmodel', models{1}, ...
    'sides', 1:8, 'native', 0, 'leadprod', 'group', 'patientname', 'sub-eight');
o.root = [fileparts(subject),filesep];
o.subj.recon.recon = fullfile(subject,'reconstruction','sub-eight_desc-reconstruction.mat');
o.patient_list = {subject};
o.prefs = ea_prefs_default;
o.prefs.d3.showdirarrows = 0;
o.d3 = struct('elrendering',1,'hlactivecontacts',true,'mirrorsides',false, ...
    'verbose','off','isomatrix',{{}},'showactivecontacts',true,'showpassivecontacts',true);
o.colorMacroContacts = [];
o = ea_resolve_elspec(o);
for i = 1:8
    current = ea_resolve_elspec(o,i);
    template = load(fullfile(test.TestData.root,'templates','electrode_models',current.elspec.matfname));
    for field = {'head','tail','x','y'}
        markers(i).(field{1}) = template.electrode.([field{1},'_position']) + [i*10,0,0];
    end
    reco.props(i).elmodel = o.elmodels{i};
    reco.props(i).manually_corrected = 1;
    reco.props(i).labels = arrayfun(@(j) sprintf('E%d_%d',i,j), ...
        1:current.elspec.numContacts, 'UniformOutput',false);
end
[coords,trajectory,markers] = ea_resolvecoords(markers,o);
reco.mni = struct('coords_mm',{coords},'trajectory',{trajectory},'markers',markers);
reco.native = reco.mni;
save(o.subj.recon.recon,'reco');
test.TestData.options = o;
test.TestData.reco = reco;
end

function testEightElectrodesSurviveGroupReload(test)
o = test.TestData.options;
o.sides = 1:2; % Legacy group caller: must not truncate the saved reconstruction.
stale = struct('name','sub-eight','coords_mm',{{zeros(4,3),zeros(4,3),[]}}, ...
    'group',2,'groupcolors',[1 0 0;0 1 0]);
loaded = ea_load_group_reconstruction(o,stale,[]);
verifyEqual(test,loaded.coords_mm,test.TestData.reco.mni.coords_mm);
verifyEqual(test,cellfun(@(x)size(x,1),loaded.trajectory),repmat(50,1,8));
verifyEqual(test,loaded.elmodels,o.elmodels);
verifyEqual(test,loaded.labels,{test.TestData.reco.props.labels});
verifyEqual(test,loaded.group,2);
end

function testPatientSpecifiedPreservesImportedContactPositions(test)
o = test.TestData.options;
reco = test.TestData.reco;
reco.mni.coords_mm{8}(3,:) = reco.mni.coords_mm{8}(3,:) + [0.13,0.21,0.08];
save(o.subj.recon.recon,'reco');
loaded = ea_load_group_reconstruction(o,struct,[]);
verifyEqual(test,loaded.coords_mm{8},reco.mni.coords_mm{8});
end

function testModelOverrideIsDisplayOnlyAndCoversEightElectrodes(test)
o = test.TestData.options;
loaded = ea_load_group_reconstruction(o,struct,'Medtronic 3389');
verifyEqual(test,cellfun(@(x)size(x,1),loaded.coords_mm),repmat(4,1,8));
verifyEqual(test,loaded.elmodels,repmat({'Medtronic 3389'},1,8));
verifyEmpty(test,loaded.labels{2});
saved = load(o.subj.recon.recon,'reco');
verifyEqual(test,saved.reco,test.TestData.reco);
end

function testEightMixedModelsRenderWithoutDroppingElectrodes(test)
o = test.TestData.options;
loaded = ea_load_group_reconstruction(o,struct,[]);
loaded.activecontacts = {zeros(4,1),zeros(8,1)}; % Group stimulation metadata is bilateral.
fig = figure('Visible','off');
cleanup = onCleanup(@() delete(fig));
axes(fig); hold on;
[rendered,~,sides] = ea_renderelstruct(o,fig,loaded,1);
verifyEqual(test,sides,1:8);
verifyEqual(test,numel(rendered),8);
verifyEqual(test,{rendered.elmodel},o.elmodels);
for i = 1:8
    current = ea_resolve_elspec(o,i);
    template = load(fullfile(test.TestData.root,'templates','electrode_models',current.elspec.matfname));
    contacts = findobj(fig,'-regexp','Tag',sprintf('^sub-eight_Contact\\d+_Side%d$',i));
    verifyEqual(test,numel(contacts),numel(template.electrode.contacts));
end
saved = load(o.subj.recon.recon,'reco');
verifyEqual(test,saved.reco,test.TestData.reco);
end

function testSparseDisplayUsesTemplateSpaceElectrodes(test)
o = test.TestData.options;
reco = test.TestData.reco;
for i = [2,4,5,6,7]
    reco.mni.coords_mm{i} = [];
    reco.mni.trajectory{i} = [];
    for field = {'head','tail','x','y'}
        reco.mni.markers(i).(field{1}) = [];
    end
end
save(o.subj.recon.recon,'reco'); % Native still contains all eight electrodes.
loaded = ea_load_group_reconstruction(o,struct,[]);
fig = figure('Visible','off');
cleanup = onCleanup(@() delete(fig));
axes(fig); hold on;
[rendered,~,sides] = ea_renderelstruct(o,fig,loaded,1);
verifyEqual(test,sides,[1,3,8]);
verifyEqual(test,[rendered.side],[1,3,8]);
end

function testMissingTrajectoryRaisesContextualError(test)
o = test.TestData.options;
loaded = ea_load_group_reconstruction(o,struct,[]);
loaded.trajectory{3} = [];
loaded.elmodel = loaded.elmodels{3};
fig = figure('Visible','off');
cleanup = onCleanup(@() delete(fig));
obj = struct('plotFigureH',fig,'elstruct',loaded,'pt',1);
o.sides = 3;
verifyError(test,@() ea_showelectrode(obj,'dbs',o),'LeadDBS:MissingElectrodeGeometry');
end

function testUnsupportedMirroringFailsBeforeWarping(test)
loaded = ea_load_group_reconstruction(test.TestData.options,struct,[]);
verifyError(test,@() ea_mirrorsides(loaded),'LeadDBS:UnsupportedGroupMirroring');
end

function testSelectedSubjectPathsMatchCoordinates(test)
global GROUP_DISPLAY_CAPTURE;
GROUP_DISPLAY_CAPTURE = [];
o = test.TestData.options;
o.patient_list = {'/unused/sub-one';'/unused/sub-two';'/unused/sub-three'};
loaded = ea_load_group_reconstruction(o,struct,[]);
records = repmat(loaded,1,3);
for i=1:3
    records(i).name = sprintf('subject-%d',i);
end
mocks = tempname(test.TestData.folder);
mkdir(mocks);
fid = fopen(fullfile(mocks,'ea_renderelstruct.m'),'w');
fprintf(fid,['function varargout=ea_renderelstruct(options,fig,records,varargin)\n' ...
    'global GROUP_DISPLAY_CAPTURE;\n' ...
    'GROUP_DISPLAY_CAPTURE=struct(''options'',options,''records'',records,''figure'',fig);\n' ...
    'error(''GroupTest:Captured'',''Captured rendering inputs'');\nend\n']);
fclose(fid);
original = pwd;
addpath(mocks,'-begin');
cd(mocks); % Override the repository-root renderer only for this capture.
cleanup = onCleanup(@() restoreCapture(original,mocks));
verifyError(test,@() ea_elvis(o,records,[3,2]),'GroupTest:Captured');
verifyEqual(test,GROUP_DISPLAY_CAPTURE.options.patient_list,o.patient_list([3,2]));
verifyEqual(test,{GROUP_DISPLAY_CAPTURE.records.name},{'subject-3','subject-2'});
end

function restoreCapture(original,mocks)
global GROUP_DISPLAY_CAPTURE;
cd(original);
rmpath(mocks);
clear ea_renderelstruct;
if ~isempty(GROUP_DISPLAY_CAPTURE)
    delete(GROUP_DISPLAY_CAPTURE.figure);
end
end
