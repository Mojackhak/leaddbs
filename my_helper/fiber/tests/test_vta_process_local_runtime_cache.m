function tests = test_vta_process_local_runtime_cache
% Solver-free tests for explicit per-subject VTA runtime caches.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.repoDir = repoDir;
end

function testExactKeysAndRuntimeLifetime(testCase)
first = mh_vta_create_subject_runtime('S001');
second = mh_vta_create_subject_runtime('S001');
key = mh_vta_runtime_cache_key('fixture', {'a', 1});
otherKey = mh_vta_runtime_cache_key('fixture', {'a', 2});

mh_vta_runtime_cache_store(first, 'subject_context', key, struct('value', 7));
[value, hit] = mh_vta_runtime_cache_lookup(first, 'subject_context', key);
[~, otherHit] = mh_vta_runtime_cache_lookup(first, ...
    'subject_context', otherKey);
[~, separateHit] = mh_vta_runtime_cache_lookup(second, ...
    'subject_context', key);

verifyTrue(testCase, hit);
verifyEqual(testCase, value.value, 7);
verifyFalse(testCase, otherHit);
verifyFalse(testCase, separateHit);
end

function testSubjectContextExcludesTaskStimulation(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
subjectDir = fullfile(testRoot, 'sub-S001');
mkdir(stubDir);
mkdir(subjectDir);
cleanup = onCleanup(@() cleanup_context_fixture(testRoot, stubDir));
write_context_stubs(stubDir);
addpath(stubDir, '-begin');
clear ea_getptopts ea_resolve_elspec ea_load_reconstruction ea_space;
rehash;
global MH_VTA_CONTEXT_CALLS; %#ok<GVMIS>
global MH_VTA_RECON_CALLS; %#ok<GVMIS>
MH_VTA_CONTEXT_CALLS = 0;
MH_VTA_RECON_CALLS = 0;

runtime = mh_vta_create_subject_runtime('S001');
first = fixture_task(subjectDir, 'R', 1, 2.0);
second = first;
second.sources.amplitude = 3.5;
[firstContext, firstStatus] = ...
    mh_vta_resolve_canonical_context(first, runtime);
[secondContext, secondStatus] = ...
    mh_vta_resolve_canonical_context(second, runtime);

verifyEqual(testCase, string(firstStatus), "miss");
verifyEqual(testCase, string(secondStatus), "hit");
verifyEqual(testCase, MH_VTA_CONTEXT_CALLS, 1);
verifyEqual(testCase, MH_VTA_RECON_CALLS, 1);
verifyFalse(testCase, isfield(firstContext, 'sources'));
verifyEqual(testCase, firstContext.trajectory, secondContext.trajectory);
end

function testTransformOnlyContextDoesNotLoadReconstruction(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
subjectDir = fullfile(testRoot, 'sub-S001');
mkdir(stubDir);
mkdir(subjectDir);
cleanup = onCleanup(@() cleanup_context_fixture(testRoot, stubDir));
write_context_stubs(stubDir);
addpath(stubDir, '-begin');
clear ea_getptopts ea_resolve_elspec ea_load_reconstruction ea_space;
rehash;
global MH_VTA_CONTEXT_CALLS; %#ok<GVMIS>
global MH_VTA_RECON_CALLS; %#ok<GVMIS>
MH_VTA_CONTEXT_CALLS = 0;
MH_VTA_RECON_CALLS = 0;
task = fixture_task(subjectDir, 'R', 1, 2.0);
runtime = mh_vta_create_subject_runtime('S001');

[first, firstStatus] = mh_vta_resolve_transform_context(task, runtime);
[second, secondStatus] = mh_vta_resolve_transform_context(task, runtime);

verifyEqual(testCase, string(firstStatus), "miss");
verifyEqual(testCase, string(secondStatus), "hit");
verifyEqual(testCase, MH_VTA_CONTEXT_CALLS, 1);
verifyEqual(testCase, MH_VTA_RECON_CALLS, 0);
verifyEqual(testCase, second.mni_reference, first.mni_reference);
end

function testExportGeometryCachePreservesPointValueAlignment(testCase)
runtime = mh_vta_create_subject_runtime('S001');
mesh = fixture_mesh();
trajectory = {[0, 0, 0; 0, 10, 0]};
elspec = struct('lead_diameter', 1.2);
task = struct('subject_id', 'S001', ...
    'reconstruction_path', '/tmp/reconstruction.mat', ...
    'reconstruction_lead_id', 1, 'electrode_model', 'Fixture');
headmodelKey = 'headmodel-key';

[geometry, firstStatus] = mh_vta_get_export_geometry( ...
    task, mesh, trajectory, 1, elspec, headmodelKey, runtime);
[cached, secondStatus] = mh_vta_get_export_geometry( ...
    task, mesh, trajectory, 1, elspec, headmodelKey, runtime);
fieldValues = (10:10:40)';
midpoints = mh_vta_tetrahedron_midpoints_mm(mesh);
[legacyPoints, legacyValues, legacyKeep] = ...
    mh_vta_remove_electrode_export_samples( ...
        mesh, midpoints, fieldValues, trajectory, 1, elspec);

verifyEqual(testCase, string(firstStatus), "miss");
verifyEqual(testCase, string(secondStatus), "hit");
verifyEqual(testCase, cached, geometry);
verifyEqual(testCase, geometry.electrode_adjusted_points_mm, ...
    legacyPoints, 'AbsTol', 1e-12);
verifyEqual(testCase, fieldValues(geometry.final_field_value_indices), ...
    legacyValues);
verifyEqual(testCase, find(legacyKeep), ...
    geometry.final_field_value_indices);

changedTrajectory = {[0, 0, 0; 0, 12, 0]};
[~, changedStatus] = mh_vta_get_export_geometry( ...
    task, mesh, changedTrajectory, 1, elspec, headmodelKey, runtime);
verifyEqual(testCase, string(changedStatus), "miss");
end

function testValidatedHeadmodelIsReusedOnlyForExactContext(testCase)
testRoot = tempname;
subjectDir = fullfile(testRoot, 'sub-S001');
headmodelDir = fullfile(subjectDir, 'headmodel', 'native');
mkdir(headmodelDir);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
path = mh_vta_canonical_headmodel_path(subjectDir, 'S001', 1);
write_valid_headmodel(path, false);
task = fixture_task(subjectDir, 'R', 1, 2.0);
context = struct( ...
    'subject_context_key', 'subject-key', ...
    'side_index', 1, ...
    'trajectory', {{[0, 0, 0; 0, 10, 0]}}, ...
    'patient_gm_mask_signature', {{'/tmp/gm.nii', 100, 1}}, ...
    'options', struct('subj', struct( ...
        'subjDir', subjectDir, 'subjId', 'S001')));
runtime = mh_vta_create_subject_runtime('S001');

[first, firstState, firstStatus, firstKey] = mh_vta_get_canonical_headmodel( ...
    task, context, struct(), runtime, 'fixture');
[second, secondState, secondStatus, secondKey] = ...
    mh_vta_get_canonical_headmodel( ...
    task, context, struct(), runtime, 'fixture');
write_valid_headmodel(path, true);
[third, ~, thirdStatus, thirdKey] = mh_vta_get_canonical_headmodel( ...
    task, context, struct(), runtime, 'fixture');
unrelated = true;
save(path, 'unrelated');

verifyEqual(testCase, string(firstState), "reused");
verifyEqual(testCase, string(firstStatus), "miss");
verifyEqual(testCase, string(secondState), "reused");
verifyEqual(testCase, string(secondStatus), "hit");
verifyEqual(testCase, second.mesh.pnt, first.mesh.pnt);
verifyEqual(testCase, secondKey, firstKey);
verifyEqual(testCase, string(thirdStatus), "miss");
verifyNotEqual(testCase, thirdKey, firstKey);
verifyNotEqual(testCase, third.mesh.pnt, first.mesh.pnt);
verifyError(testCase, @() mh_vta_get_canonical_headmodel( ...
    task, context, struct(), runtime, 'fixture'), ...
    'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel');

conflicting = task;
conflicting.model.gray_matter_s_per_m = 0.34;
verifyError(testCase, @() mh_vta_get_canonical_headmodel( ...
    conflicting, context, struct(), runtime, 'fixture'), ...
    'mh_vta:ConflictingCanonicalHeadmodelContext');
end

function testNativeAnchorCacheIsPathAndFileSpecific(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
firstPath = fullfile(testRoot, 'first.nii');
secondPath = fullfile(testRoot, 'second.nii');
write_fixture_nifti(firstPath, zeros(2, 2, 2, 'single'), eye(4));
write_fixture_nifti(secondPath, zeros(3, 2, 2, 'single'), eye(4));
runtime = mh_vta_create_subject_runtime('S001');

[first, firstStatus] = mh_vta_get_native_anchor(firstPath, runtime);
[cached, secondStatus] = mh_vta_get_native_anchor(firstPath, runtime);
[other, otherStatus] = mh_vta_get_native_anchor(secondPath, runtime);

verifyEqual(testCase, string(firstStatus), "miss");
verifyEqual(testCase, string(secondStatus), "hit");
verifyEqual(testCase, string(otherStatus), "miss");
verifyEqual(testCase, cached.dim, first.dim);
verifyNotEqual(testCase, other.dim, first.dim);
end

function testDirectExportWithoutHeadmodelIdentityDoesNotCache(testCase)
runtime = mh_vta_create_subject_runtime('S001');
firstMesh = fixture_mesh();
secondMesh = firstMesh;
secondMesh.pnt(:, 1) = secondMesh.pnt(:, 1) + 5;
trajectory = {[0, 0, 0; 0, 10, 0]};
elspec = struct('lead_diameter', 1.2);
task = struct('subject_id', 'S001', ...
    'reconstruction_path', '/tmp/reconstruction.mat', ...
    'reconstruction_lead_id', 1, 'electrode_model', 'Fixture');

[first, firstStatus, firstKey] = mh_vta_get_export_geometry( ...
    task, firstMesh, trajectory, 1, elspec, '', runtime);
[second, secondStatus, secondKey] = mh_vta_get_export_geometry( ...
    task, secondMesh, trajectory, 1, elspec, '', runtime);

verifyEqual(testCase, string(firstStatus), "miss");
verifyEqual(testCase, string(secondStatus), "miss");
verifyEmpty(testCase, firstKey);
verifyEmpty(testCase, secondKey);
verifyNotEqual(testCase, first.tetrahedron_midpoints_mm, ...
    second.tetrahedron_midpoints_mm);
verifyEqual(testCase, double(runtime.caches.export_geometry.Count), 0);
end

function task = fixture_task(subjectDir, hemisphere, leadId, amplitude)
source = struct('source_id', 'source-1', 'frequency_hz', 130, ...
    'control_mode', 'voltage', 'amplitude', amplitude, ...
    'pulse_width_us', 60, 'contacts', struct( ...
        'contact', 1, 'polarity', 'cathode', 'fraction', 1));
task = struct( ...
    'task_id', 'task-context-fixture', ...
    'subject_id', 'S001', ...
    'subject_dir', subjectDir, ...
    'reconstruction_path', fullfile(subjectDir, 'reconstruction.mat'), ...
    'hemisphere', hemisphere, ...
    'electrode_model', 'Fixture Electrode', ...
    'reconstruction_lead_id', leadId, ...
    'sources', source, ...
    'model', struct('atlas_set', 'FixtureAtlas', ...
        'gray_matter_s_per_m', 0.33, ...
        'white_matter_s_per_m', 0.14));
end

function mesh = fixture_mesh()
mesh = struct();
mesh.pnt = [ ...
    0, 0, 0; 4, 0, 0; 0, 4, 0; 0, 0, 4; ...
    8, 0, 0; 8, 4, 0; 8, 0, 4];
mesh.tet = [1, 2, 3, 4; 2, 5, 6, 7; 1, 3, 4, 2; 2, 6, 7, 5];
mesh.tissue = [1; 2; 3; 1];
mesh.unit = 'mm';
end

function write_context_stubs(stubDir)
write_text(fullfile(stubDir, 'ea_getptopts.m'), [ ...
    "function options = ea_getptopts(subjectDir, varargin)" newline ...
    "global MH_VTA_CONTEXT_CALLS;" newline ...
    "MH_VTA_CONTEXT_CALLS = MH_VTA_CONTEXT_CALLS + 1;" newline ...
    "[~, patient] = fileparts(subjectDir);" newline ...
    "options = struct();" newline ...
    "options.subj = struct('subjDir',subjectDir,'subjId',patient," + ...
    "'AnchorModality','T1','preopAnat',struct('T1'," + ...
    "struct('coreg',fullfile(subjectDir,'anchor.nii'))));" newline ...
    "options.prefs = struct('vat',struct(),'machine'," + ...
    "struct('vatsettings',struct()));" newline ...
    "end" newline]);
write_text(fullfile(stubDir, 'ea_resolve_elspec.m'), [ ...
    "function options = ea_resolve_elspec(options)" newline ...
    "options.elspec = struct('lead_diameter',1.2);" newline ...
    "end" newline]);
write_text(fullfile(stubDir, 'ea_load_reconstruction.m'), [ ...
    "function [coords, trajectory, markers, model] = ea_load_reconstruction(options)" newline ...
    "global MH_VTA_RECON_CALLS;" newline ...
    "MH_VTA_RECON_CALLS = MH_VTA_RECON_CALLS + 1;" newline ...
    "coords = []; markers = []; model = options.elmodel;" newline ...
    "trajectory = {[0,0,0;0,10,0],[0,0,0;0,10,0]};" newline ...
    "end" newline]);
write_text(fullfile(stubDir, 'ea_space.m'), [ ...
    "function path = ea_space(varargin)" newline ...
    "path = tempdir;" newline ...
    "end" newline]);
end

function cleanup_context_fixture(testRoot, stubDir)
rmpath(stubDir);
clear ea_getptopts ea_resolve_elspec ea_load_reconstruction ea_space;
clear global MH_VTA_CONTEXT_CALLS;
clear global MH_VTA_RECON_CALLS;
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end

function write_fixture_nifti(path, image, affine)
nii = struct('fname', path, 'dim', size(image), 'dt', [16, 0], ...
    'mat', affine, 'n', [1, 1], 'pinfo', [1; 0; 0], ...
    'descrip', 'VTA cache fixture', 'img', image);
if numel(nii.dim) < 3
    nii.dim(end + 1:3) = 1;
end
ea_write_nii(nii);
end

function write_valid_headmodel(path, changed)
points = [0, 0, 0; 10, -20, 30; -40, 50, -60];
if changed
    points(end + 1, :) = [80, 90, -100];
end
mesh = struct('pnt', points, ...
    'unit', 'mm');
vol = struct('pos', double(mesh.pnt) / 1000);
centroids = [];
wmboundary = [];
elfv = [];
meshregions = [];
save(path, 'vol', 'mesh', 'centroids', 'wmboundary', ...
    'elfv', 'meshregions');
end

function write_text(path, content)
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create VTA runtime-cache fixture.');
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, char(content), 'char');
end
