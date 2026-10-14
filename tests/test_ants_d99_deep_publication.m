function tests = test_ants_d99_deep_publication
% Publisher orchestration tests; registration/application run only as fixtures.
tests = functiontests(localfunctions);
end

function setupOnce(test)
test.TestData.path = path;
test.TestData.cwd = pwd;
test.TestData.copy = @copyfile;
test.TestData.warning = warning('query', 'MATLAB:dispatcher:nameConflict');
warning('off', 'MATLAB:dispatcher:nameConflict');
root = fileparts(fileparts(mfilename('fullpath')));
addpath(root, fullfile(root, 'helpers'), fullfile(root, 'helpers', 'gui'), fullfile(root, 'ext_libs', 'ANTs'));
folder = tempname;
mkdir(folder);
mocks = fullfile(folder, 'mocks');
mkdir(mocks);
writeMock(mocks, 'ea_getspace', [
    "function value=ea_getspace"
    "global D99_PUBLISH_TEST; value=D99_PUBLISH_TEST.space;"
    "end"]);
writeMock(mocks, 'ea_space', [
    "function value=ea_space(varargin)"
    "global D99_PUBLISH_TEST; value=[D99_PUBLISH_TEST.template,filesep];"
    "end"]);
writeMock(mocks, 'ea_load_nii', [
    "function value=ea_load_nii(p)"
    "value=load(p,'-mat');"
    "end"]);
writeMock(mocks, 'savejson', [
    "function savejson(~,value,p)"
    "ea_mkdir(fileparts(p)); f=fopen(p,'w'); fprintf(f,'%s',jsonencode(value)); fclose(f);"
    "end"]);
writeMock(mocks, 'loadjson', [
    "function value=loadjson(p)"
    "value=jsondecode(fileread(p));"
    "end"]);
writeMock(mocks, 'ea_ants_d99_deep_run', [
    "function value=ea_ants_d99_deep_run(template,moving,work)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='engine';"
    "D99_PUBLISH_TEST.engine={template,moving,work};"
    "if strcmp(D99_PUBLISH_TEST.failure,'engine'), error('D99Test:Engine','engine failed'); end"
    "ea_mkdir(fullfile(work,'engine'));"
    "value.forward=fullfile(work,'engine','forward.nii.gz');"
    "value.inverse=fullfile(work,'engine','inverse.nii.gz');"
    "for p={value.forward,value.inverse}, f=fopen(p{1},'w'); fprintf(f,'new-field'); fclose(f); end"
    "value.warped=moving; value.masks=struct('fixed','fixed-mask','moving','native-mask','deep','deep-mask');"
    "value.provenance=struct('moving',moving,'mask_origin','independent bootstrap');"
    "for name={'bootstrap','linear','wholebrain','deep'}, command=fullfile(work,'engine',[name{1},'.txt']); f=fopen(command,'w'); fprintf(f,'command-%s',name{1}); fclose(f); value.provenance.(name{1})=struct('command',command); end"
    "value.preset=struct('interpolation','Linear','float',0,'randomseed',1);"
    "end"]);
writeMock(mocks, 'ea_apply_normalization', [
    "function ea_apply_normalization(o)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='apply'; D99_PUBLISH_TEST.staged=o;"
    "if strcmp(D99_PUBLISH_TEST.failure,'apply'), error('D99Test:Apply','application failed'); end"
    "names=fieldnames(o.subj.coreg.anat.preop);"
    "for i=1:numel(names), name=names{i}; if isfile(o.subj.coreg.anat.preop.(name)), ea_mkdir(fileparts(o.subj.norm.anat.preop.(name))); copyfile(o.subj.coreg.anat.preop.(name),o.subj.norm.anat.preop.(name)); end; end"
    "if strcmp(o.subj.postopModality,'CT'), ea_mkdir(fileparts(o.subj.norm.anat.postop.CT)); copyfile(o.subj.coreg.anat.postop.CT,o.subj.norm.anat.postop.CT); end"
    "end"]);
writeMock(mocks, 'ea_tonemapct', [
    "function ea_tonemapct(o,kind)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='tonemap'; assert(strcmp(kind,'norm'));"
    "v=load(o.subj.postopAnat.CT.norm,'-mat'); v.img=v.img+100; save(o.subj.postopAnat.CT.normTonemap,'-struct','v','-mat');"
    "end"]);
writeMock(mocks, 'ea_gencheckregfigs', [
    "function ea_gencheckregfigs(o,kind)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='qc'; assert(strcmp(kind,'norm'));"
    "if strcmp(D99_PUBLISH_TEST.failure,'qc'), return; end"
    "files=struct2cell(o.subj.norm.checkreg.preop); if strcmp(o.subj.postopModality,'CT'), files=[files;struct2cell(o.subj.norm.checkreg.postop)]; end"
    "for i=1:numel(files), ea_mkdir(fileparts(files{i})); imwrite(uint8(ones(5,5)*80),files{i}); end"
    "end"]);
writeMock(mocks, 'ea_methods', [
    "function ea_methods(o,text,varargin)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='methods';"
    "f=fopen(o.subj.methodLog,'a'); fprintf(f,'\n%s',text); fclose(f);"
    "end"]);
writeMock(mocks, 'ea_cprintf', [
    "function ea_cprintf(varargin)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='warning';"
    "end"]);
writeMock(mocks, 'ea_delete', [
    "function ea_delete(p,varargin)"
    "global D99_PUBLISH_TEST; assert(isequal(varargin,{'recycle','on'}));"
    "D99_PUBLISH_TEST.deleteCount=D99_PUBLISH_TEST.deleteCount+1;"
    "if strcmp(D99_PUBLISH_TEST.failure,'trash') && D99_PUBLISH_TEST.deleteCount==2, error('D99Test:Trash','Trash failed'); end"
    "if isfile(p), destination=fullfile(D99_PUBLISH_TEST.trash,ea_generate_uuid); movefile(p,destination); end"
    "end"]);
writeMock(mocks, 'copyfile', [
    "function varargout=copyfile(varargin)"
    "global D99_PUBLISH_TEST; destination=varargin{2};"
    "if strcmp(D99_PUBLISH_TEST.failure,'publish') && ~D99_PUBLISH_TEST.copyFailed && strcmp(destination,D99_PUBLISH_TEST.failTarget)"
    "D99_PUBLISH_TEST.copyFailed=true; f=fopen(destination,'w'); fprintf(f,'partial'); fclose(f); error('D99Test:Copy','publication failed'); end"
    "if nargout, [varargout{1:nargout}]=D99_PUBLISH_TEST.copy(varargin{:}); else, D99_PUBLISH_TEST.copy(varargin{:}); end"
    "end"]);
writeMock(mocks, 'ea_norm_refine_prepare', [
    "function [o,context]=ea_norm_refine_prepare(o)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='generic-prepare'; context=struct('cancelled',true);"
    "end"]);
writeMock(mocks, 'ea_normalize_apply_normalization', [
    "function ea_normalize_apply_normalization(varargin)"
    "global D99_PUBLISH_TEST; D99_PUBLISH_TEST.events{end+1}='reapply';"
    "end"]);
addpath(mocks, '-begin');
cd(mocks);
test.TestData.folder = folder;
fprintf('D99_PUBLICATION_FIXTURES=%s\n', folder);
end

function teardownOnce(test)
cd(test.TestData.cwd);
path(test.TestData.path);
warning(test.TestData.warning);
clear ea_getspace ea_space ea_load_nii savejson loadjson ea_ants_d99_deep_run ...
    ea_apply_normalization ea_tonemapct ea_gencheckregfigs ea_methods ea_cprintf ...
    ea_delete copyfile ea_norm_refine_prepare ea_normalize_apply_normalization;
clear global D99_PUBLISH_TEST;
end

function setup(test)
global D99_PUBLISH_TEST;
subject = tempname(test.TestData.folder);
mkdir(subject);
template = fullfile(subject, 'template');
mkdir(template);
writeImage(fullfile(template, 't1.nii'), 1);
D99_PUBLISH_TEST = struct('space','D99v2','template',template,'events',{{}}, ...
    'failure','','deleteCount',0,'copy',test.TestData.copy,'copyFailed',false, ...
    'failTarget','','trash',fullfile(subject,'trash'));
mkdir(D99_PUBLISH_TEST.trash);
o.subj.subjDir = subject;
o.subj.subjId = 'test';
o.subj.AnchorModality = 'ax_T1w';
o.subj.normDir = fullfile(subject,'normalization');
o.subj.brainshiftDir = fullfile(subject,'brainshift');
o.subj.warpdriveDir = fullfile(subject,'warpdrive');
o.subj.postopModality = 'CT';
o.subj.methodLog = fullfile(subject,'log','methods.txt');
o.subj.norm.transform.forwardBaseName = fullfile(o.subj.normDir,'transformations','forward_');
o.subj.norm.transform.inverseBaseName = fullfile(o.subj.normDir,'transformations','inverse_');
o.subj.norm.log.method = fullfile(o.subj.normDir,'log','method.json');
o.subj.norm.log.logBaseName = fullfile(o.subj.normDir,'log','normalization_');
for name={'ax_T1w','ax_T2w'}
    key=name{1};
    o.subj.coreg.anat.preop.(key)=fullfile(subject,'coregistration','anat',[key,'.nii']);
    o.subj.norm.anat.preop.(key)=fullfile(o.subj.normDir,'anat',[key,'.nii']);
    o.subj.norm.checkreg.preop.(key)=fullfile(o.subj.normDir,'checkreg',[key,'.png']);
    writeImage(o.subj.coreg.anat.preop.(key),1);
end
o.subj.preopAnat.ax_T1w.norm = o.subj.norm.anat.preop.ax_T1w;
o.subj.coreg.anat.postop.CT=fullfile(subject,'coregistration','anat','CT.nii');
o.subj.coreg.anat.postop.tonemapCT=fullfile(subject,'coregistration','anat','tonemapCT.nii');
writeImage(o.subj.coreg.anat.postop.CT,7);
writeImage(o.subj.coreg.anat.postop.tonemapCT,8);
o.subj.norm.anat.postop.CT=fullfile(o.subj.normDir,'anat','CT.nii');
o.subj.norm.anat.postop.tonemapCT=fullfile(o.subj.normDir,'anat','tonemapCT.nii');
o.subj.norm.checkreg.postop.tonemapCT=fullfile(o.subj.normDir,'checkreg','tonemapCT.png');
o.subj.postopAnat.CT.norm=o.subj.norm.anat.postop.CT;
o.subj.postopAnat.CT.normTonemap=o.subj.norm.anat.postop.tonemapCT;
o.subj.brainshift.transform.scrf=fullfile(o.subj.brainshiftDir,'scrf.mat');
o.subj.brainshift.log.method=fullfile(o.subj.brainshiftDir,'method.json');
o.prefs.diary=false;
o.prefs.machine.normsettings.ants_preset='ea_antspreset_macaque_d99_deep';
o.bids.spacedef.name='D99v2';
o.normalize.method='ANTs (Avants 2008)';
o.normalize.deferApply=true;
o.overwriteapproved=true;
writeFile([o.subj.norm.transform.forwardBaseName,'ants.nii.gz'],'old-forward');
writeFile([o.subj.norm.transform.inverseBaseName,'ants.nii.gz'],'old-inverse');
writeFile(o.subj.norm.log.method,'{"method":"ANTs (Avants 2008)","approval":1}');
writeFile(fullfile(o.subj.normDir,'log','sub-test_desc-antscmd.txt'),'old-command-history');
writeFile(o.subj.methodLog,'old-method-history');
writeFile(fullfile(subject,'unrelated.txt'),'keep');
for name={'source.json','target.json','info.json'}
    writeFile(fullfile(o.subj.warpdriveDir,name{1}),'old-session');
end
test.TestData.options=o;
end

function testDispatchPublishesCompleteT1OnlyResult(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
ea_normalize(o);
verifyEqual(test,D99_PUBLISH_TEST.engine{2},o.subj.coreg.anat.preop.ax_T1w);
verifyEqual(test,D99_PUBLISH_TEST.events,{'engine','apply','tonemap','qc','methods'});
verifyFalse(test,D99_PUBLISH_TEST.staged.normalize.deferApply);
method=loadjson(o.subj.norm.log.method);
verifyEqual(test,method.approval,0);
verifyEqual(test,method.settings.preset_id,'ea_antspreset_macaque_d99_deep');
verifyEqual(test,method.settings.interpolation,'Linear');
verifyEqual(test,method.settings.precision,'double');
verifyEqual(test,method.transform.forward,[o.subj.norm.transform.forwardBaseName,'ants.nii.gz']);
tonemap=ea_load_nii(o.subj.norm.anat.postop.tonemapCT);
verifyEqual(test,tonemap.img,ones(3,3,3)*107);
verifyTrue(test,startsWith(fileread(o.subj.methodLog),'old-method-history'));
commandLog=fileread(fullfile(o.subj.normDir,'log','sub-test_desc-antscmd.txt'));
verifyTrue(test,startsWith(commandLog,'old-command-history'));
verifyTrue(test,all(contains(commandLog,{'command-bootstrap','command-linear','command-wholebrain','command-deep'})));
verifyEqual(test,fileread(fullfile(o.subj.subjDir,'unrelated.txt')),'keep');
verifyFalse(test,isfile(fullfile(o.subj.warpdriveDir,'source.json')));
records=dir(fullfile(o.subj.subjDir,'masks','ants_d99_deep','publication','*','publication.json'));
receipt=loadjson(fullfile(records(1).folder,records(1).name));
verifyEqual(test,receipt.status,'published');
verifyTrue(test,all(cellfun(@isfile,receipt.backup_paths)));
end

function testT1FilenameDoesNotRequireUnderscoredAlias(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
o.subj.AnchorModality='axT1w';
o.subj.coreg.anat.preop.axT1w=o.subj.coreg.anat.preop.ax_T1w;
o.subj.coreg.anat.preop=rmfield(o.subj.coreg.anat.preop,'ax_T1w');
o.subj.norm.anat.preop.axT1w=o.subj.norm.anat.preop.ax_T1w;
o.subj.norm.anat.preop=rmfield(o.subj.norm.anat.preop,'ax_T1w');
o.subj.norm.checkreg.preop.axT1w=o.subj.norm.checkreg.preop.ax_T1w;
o.subj.norm.checkreg.preop=rmfield(o.subj.norm.checkreg.preop,'ax_T1w');
o.subj.preopAnat.axT1w=o.subj.preopAnat.ax_T1w;
o.subj.preopAnat=rmfield(o.subj.preopAnat,'ax_T1w');
ea_normalize(o);
verifyEqual(test,D99_PUBLISH_TEST.engine{2},o.subj.coreg.anat.preop.axT1w);
end

function testDirectAntsDispatchAndStaleBrainshift(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
writeFile(o.subj.brainshift.transform.scrf,'old-scrf');
writeFile(o.subj.brainshift.log.method,'{"method":"Fine","approval":1,"extra":"keep"}');
ea_normalize_ants(o);
verifyEmpty(test,D99_PUBLISH_TEST.staged.subj.brainshift.transform.scrf);
verifyEqual(test,fileread(o.subj.brainshift.transform.scrf),'old-scrf');
verifyEqual(test,o.subj.brainshift.transform.scrf,fullfile(o.subj.brainshiftDir,'scrf.mat'));
state=loadjson(o.subj.brainshift.log.method);
verifyEqual(test,state.approval,0);
verifyEqual(test,state.extra,'keep');
verifyFalse(test,isfield(state,'requires_rerun'));
normalization=loadjson(o.subj.norm.log.method);
verifyTrue(test,normalization.downstream.brainshift.requires_rerun);
verifyEqual(test,D99_PUBLISH_TEST.events{end},'warning');
end

function testEnabledDiaryIsStagedAndPublished(test)
o=test.TestData.options;
o.prefs.diary=true;
ea_normalize(o);
logs=dir([o.subj.norm.log.logBaseName,'*.log']);
verifyEqual(test,numel(logs),1);
end

function testInvalidSpaceAndAnchorDoNotTouchExistingResult(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
o.bids.spacedef.name='MNI152NLin2009bAsym';
verifyError(test,@()ea_normalize(o),'ea_normalize_ants_d99_deep:Space');
o.bids.spacedef.name='D99v2';
o.subj.AnchorModality='ax_T2w';
o.subj.preopAnat.ax_T2w.norm=o.subj.norm.anat.preop.ax_T2w;
verifyError(test,@()ea_normalize(o),'ea_normalize_ants_d99_deep:Anchor');
verifyEmpty(test,D99_PUBLISH_TEST.events);
verifyEqual(test,fileread([o.subj.norm.transform.forwardBaseName,'ants.nii.gz']),'old-forward');
verifyFalse(test,isfolder(fullfile(o.subj.subjDir,'masks')));
end

function testApplicationFailurePreservesPriorResult(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
D99_PUBLISH_TEST.failure='apply';
verifyError(test,@()ea_normalize(o),'D99Test:Apply');
verifyPrior(test,o);
verifyEqual(test,D99_PUBLISH_TEST.deleteCount,0);
end

function testMissingQaPreservesPriorAndBrainshiftApproval(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
writeFile(o.subj.brainshift.transform.scrf,'old-scrf');
writeFile(o.subj.brainshift.log.method,'{"method":"Fine","approval":1}');
D99_PUBLISH_TEST.failure='qc';
verifyError(test,@()ea_normalize(o),'ea_normalize_ants_d99_deep:IncompleteStage');
verifyPrior(test,o);
state=loadjson(o.subj.brainshift.log.method);
verifyEqual(test,state.approval,1);
verifyEqual(test,D99_PUBLISH_TEST.deleteCount,0);
end

function testTrashFailureRestoresPriorResult(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
D99_PUBLISH_TEST.failure='trash';
verifyError(test,@()ea_normalize(o),'D99Test:Trash');
verifyPrior(test,o);
verifyFalse(test,isfile(o.subj.norm.anat.preop.ax_T1w));
end

function testPartialPublicationRestoresOldAndRemovesNewFiles(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
D99_PUBLISH_TEST.failure='publish';
D99_PUBLISH_TEST.failTarget=o.subj.norm.anat.preop.ax_T1w;
verifyError(test,@()ea_normalize(o),'D99Test:Copy');
verifyPrior(test,o);
verifyFalse(test,isfile(o.subj.norm.anat.preop.ax_T1w));
end

function testLegacyAndReapplyDispatchRemainSeparate(test)
global D99_PUBLISH_TEST;
o=test.TestData.options;
o.prefs.machine.normsettings.ants_preset='ea_antspreset_default';
ea_normalize(o);
verifyEqual(test,D99_PUBLISH_TEST.events,{'generic-prepare'});
D99_PUBLISH_TEST.events={};
o.prefs.machine.normsettings.ants_preset='ea_antspreset_macaque_d99_deep';
o.normalize.method='Apply';
o.subj.postopModality='None';
ea_normalize(o);
verifyEqual(test,D99_PUBLISH_TEST.events,{'reapply'});
end

function verifyPrior(test,o)
verifyEqual(test,fileread([o.subj.norm.transform.forwardBaseName,'ants.nii.gz']),'old-forward');
verifyEqual(test,fileread([o.subj.norm.transform.inverseBaseName,'ants.nii.gz']),'old-inverse');
verifyEqual(test,fileread(o.subj.methodLog),'old-method-history');
verifyEqual(test,fileread(fullfile(o.subj.normDir,'log','sub-test_desc-antscmd.txt')),'old-command-history');
verifyEqual(test,loadjson(o.subj.norm.log.method).approval,1);
verifyTrue(test,isfile(fullfile(o.subj.warpdriveDir,'source.json')));
end

function writeImage(filename,value)
ea_mkdir(fileparts(filename));
img=ones(3,3,3)*value;
mat=eye(4);
save(filename,'img','mat','-mat');
end

function writeFile(filename,text)
ea_mkdir(fileparts(filename));
file=fopen(filename,'w');
fprintf(file,'%s',char(text));
fclose(file);
end

function writeMock(folder,name,lines)
file=fopen(fullfile(folder,[name,'.m']),'w');
fprintf(file,'%s\n',char(strjoin(lines,newline)));
fclose(file);
end
