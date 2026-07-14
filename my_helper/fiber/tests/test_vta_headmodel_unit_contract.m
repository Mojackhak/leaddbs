function tests = test_vta_headmodel_unit_contract
% Validate canonical mesh/volume coordinate units before FEM execution.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(fullfile(repoDir, 'my_helper', 'fiber')));
testCase.TestData.repoDir = repoDir;
end

function testAcceptsDoubleCoordinatesWithoutUnitField(testCase)
[vol, mesh] = valid_fixture('double', false);
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testAcceptsSingleCoordinatesWithMillimeterUnit(testCase)
[vol, mesh] = valid_fixture('single', true);
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsVolumeCoordinatesStoredInMillimeters(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos = double(mesh.pnt);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsPresentNonMillimeterUnit(testCase)
[vol, mesh] = valid_fixture('double', true);
mesh.unit = 'm';
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsJointlyMisScaledCoordinatesOutsideRange(testCase)
mesh = struct('pnt', [0, 0, 0; 3000, 0, 0], 'unit', 'mm');
vol = struct('pos', double(mesh.pnt) / 1000);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonfiniteCoordinates(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = Inf;
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsCoordinateShapeAndNodeCountMismatch(testCase)
[vol, mesh] = valid_fixture('double', true);
invalidShape = mesh;
invalidShape.pnt = zeros(2, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, invalidShape), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
fewerNodes = mesh;
fewerNodes.pnt = fewerNodes.pnt(1:2, :);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, fewerNodes), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonscalarVolumeStruct(testCase)
[vol, mesh] = valid_fixture('double', true);
vol = repmat(vol, 1, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testRejectsNonscalarMeshStruct(testCase)
[vol, mesh] = valid_fixture('double', true);
mesh = repmat(mesh, 1, 2);
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testAcceptsMismatchExactlyAtTolerance(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = vol.pos(1, 1) + 1e-6;
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsMismatchAboveTolerance(testCase)
[vol, mesh] = valid_fixture('double', true);
vol.pos(1, 1) = vol.pos(1, 1) + 1.0001e-6;
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testAcceptsPositionSlightlyBelowAbsoluteBound(testCase)
vol = struct('pos', [2 - 1e-6, 0, 0]);
mesh = struct('pnt', vol.pos * 1000, 'unit', 'mm');
mh_vta_validate_canonical_headmodel_units(vol, mesh);
verifyTrue(testCase, true);
end

function testRejectsPositionExactlyAtAbsoluteBound(testCase)
vol = struct('pos', [2, 0, 0]);
mesh = struct('pnt', vol.pos * 1000, 'unit', 'mm');
verifyError(testCase, @() mh_vta_validate_canonical_headmodel_units(vol, mesh), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
end

function testPrepareRejectsUnitMismatchWithoutOverwrite(testCase)
testRoot = tempname;
subjectDir = fullfile(testRoot, 'sub-SNr003');
headmodelDir = fullfile(subjectDir, 'headmodel', 'native');
mkdir(headmodelDir);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
[vol, mesh] = valid_fixture('double', true);
vol.pos = double(mesh.pnt);
centroids = [];
wmboundary = [];
elfv = [];
meshregions = [];
headmodelPath = fullfile(headmodelDir, 'sub-SNr003_desc-headmodel1.mat');
save(headmodelPath, 'vol', 'mesh', 'centroids', 'wmboundary', ...
    'elfv', 'meshregions', '-v7.3');
originalHash = mh_fiber_file_sha256(headmodelPath);
options = struct('native', 1, 'subj', struct( ...
    'subjDir', subjectDir, 'subjId', 'SNr003'));
verifyError(testCase, @() mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation'), ...
    'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel');
verifyEqual(testCase, mh_fiber_file_sha256(headmodelPath), originalHash);
end

function testCanonicalBackendGuardsUnitsImmediatelyAfterLoad(testCase)
loaderSource = fileread(which('mh_vta_load_canonical_headmodel'));
loadPosition = strfind(loaderSource, 'headmodel = load(headmodelPath');
guardPosition = strfind(loaderSource, ...
    'mh_vta_validate_canonical_headmodel_units(');
backendSource = fileread(which('mh_vta_backend_simbio_onesolve_canonical'));
cachePosition = strfind(backendSource, ...
    'mh_vta_get_canonical_headmodel(');
cacheSource = fileread(which('mh_vta_get_canonical_headmodel'));
preparePosition = strfind(cacheSource, ...
    'mh_vta_prepare_canonical_headmodel(');
activeIndexPosition = strfind(backendSource, 'activeidx = ea_getactiveidx');
verifyEqual(testCase, numel(loadPosition), 1);
verifyEqual(testCase, numel(guardPosition), 1);
verifyEqual(testCase, numel(preparePosition), 1);
verifyEqual(testCase, numel(cachePosition), 1);
verifyEqual(testCase, numel(activeIndexPosition), 1);
verifyGreaterThan(testCase, guardPosition, loadPosition);
verifyLessThan(testCase, cachePosition, activeIndexPosition);
verifyEmpty(testCase, strfind(backendSource, 'load(headmodelPath'));
end

function testCanonicalContextLoadSitesAreConsolidated(testCase)
backendSource = fileread(which('mh_vta_backend_simbio_onesolve_canonical'));
exportSource = fileread(which('mh_vta_export_canonical_outputs'));
contextSource = fileread(which('mh_vta_resolve_canonical_context'));
transformSource = fileread(which('mh_vta_resolve_transform_context'));

verifyEqual(testCase, numel(strfind( ...
    transformSource, 'options = ea_getptopts(')), 1);
verifyEqual(testCase, numel(strfind( ...
    contextSource, 'ea_load_reconstruction(options)')), 1);
verifyNotEmpty(testCase, strfind(contextSource, ...
    'mh_vta_resolve_transform_context('));
verifyEmpty(testCase, strfind(backendSource, 'ea_getptopts('));
verifyEmpty(testCase, strfind(backendSource, 'ea_load_reconstruction('));
verifyEmpty(testCase, strfind(exportSource, 'ea_load_reconstruction('));
verifyEmpty(testCase, strfind(exportSource, 'ea_getptopts('));
verifyNotEmpty(testCase, strfind(contextSource, ...
    'options.elside = sideIndex;'));
end

function testNewlyBuiltInvalidHeadmodelStopsBeforeActiveIndex(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
subjectDir = fullfile(testRoot, 'sub-SNr003');
mkdir(stubDir);
mkdir(subjectDir);
markerPath = fullfile(testRoot, 'active-index-called.txt');
originalMarker = getenv('MH_VTA_ACTIVE_INDEX_MARKER');
environmentCleanup = onCleanup(@() setenv( ...
    'MH_VTA_ACTIVE_INDEX_MARKER', originalMarker));
preexistingMarker = 'preexisting-marker-sentinel';
setenv('MH_VTA_ACTIVE_INDEX_MARKER', preexistingMarker);
cleanup = onCleanup(@() cleanup_backend_fixture( ...
    testRoot, stubDir, preexistingMarker));
write_backend_stubs(stubDir);
setenv('MH_VTA_ACTIVE_INDEX_MARKER', markerPath);
addpath(stubDir, '-begin');
clear_backend_fixture_functions();
rehash;

reco = struct('props', struct('elmodel', 'Fixture Electrode'));
reconstructionPath = fullfile(testRoot, 'reconstruction.mat');
save(reconstructionPath, 'reco');
task = backend_fixture_task(subjectDir, reconstructionPath);

verifyError(testCase, ...
    @() mh_vta_backend_simbio_onesolve_canonical(task), ...
    'mh_vta:InvalidCanonicalHeadmodelUnits');
verifyFalse(testCase, isfile(markerPath), ...
    'ea_getactiveidx must not run for a unit-invalid newly built head model.');
clear cleanup;
verifyEqual(testCase, getenv('MH_VTA_ACTIVE_INDEX_MARKER'), preexistingMarker);
end

function [vol, mesh] = valid_fixture(precision, includeUnit)
pointsMm = cast([0, 0, 0; 10, -20, 30; -40, 50, -60], precision);
mesh = struct('pnt', pointsMm);
if includeUnit
    mesh.unit = 'mm';
end
vol = struct('pos', cast(double(pointsMm) / 1000, precision));
end

function task = backend_fixture_task(subjectDir, reconstructionPath)
contact = struct('contact', 1, 'polarity', 'cathode');
source = struct('amplitude', 1, 'control_mode', 'voltage', ...
    'contacts', contact);
task = struct( ...
    'task_id', 'newly-built-invalid-headmodel', ...
    'subject_id', 'SNr003', ...
    'subject_dir', subjectDir, ...
    'reconstruction_path', reconstructionPath, ...
    'electrode_model', 'Fixture Electrode', ...
    'hemisphere', 'R', ...
    'reconstruction_lead_id', 1, ...
    'sources', source, ...
    'model', struct('atlas_set', 'FixtureAtlas', ...
        'gray_matter_s_per_m', 0.33, ...
        'white_matter_s_per_m', 0.14), ...
    'missing_artifacts', struct('native', {{'efield.nii.gz'}}));
end

function write_backend_stubs(stubDir)
write_stub(stubDir, 'ea_getptopts.m', ...
    "function options = ea_getptopts(subjectDir, varargin)" + newline + ...
    "[~, subjectLabel] = fileparts(subjectDir);" + newline + ...
    "subjectId = regexprep(subjectLabel, '^sub-', '');" + newline + ...
    "options = struct('subj', struct('subjDir', subjectDir, 'subjId', subjectId," + ...
    "'AnchorModality','fixture','preopAnat',struct('fixture'," + ...
    "struct('coreg','fixture-anchor.nii')))," + ...
    "'prefs',struct('vat',struct(),'machine',struct('vatsettings',struct())));" + newline + ...
    "end" + newline);
write_stub(stubDir, 'ea_resolve_elspec.m', ...
    "function options = ea_resolve_elspec(options)" + newline + ...
    "options.elspec = struct('lead_diameter',1.2);" + newline + ...
    "end" + newline);
write_stub(stubDir, 'mh_vta_configure_canonical_options.m', ...
    "function options = mh_vta_configure_canonical_options(options, varargin)" + newline + ...
    "options.subj.AnchorModality = 'fixture';" + newline + ...
    "options.subj.preopAnat.fixture.coreg = 'fixture-anchor.nii';" + newline + ...
    "end" + newline);
write_stub(stubDir, 'ea_initializeS.m', ...
    "function S = ea_initializeS(varargin)" + newline + ...
    "S = struct('numContacts', 1, 'Rs1', struct());" + newline + ...
    "end" + newline);
write_stub(stubDir, 'ea_activecontacts.m', ...
    "function S = ea_activecontacts(S)" + newline + ...
    "end" + newline);
write_stub(stubDir, 'ea_load_reconstruction.m', ...
    "function [coords, trajectory, markers, elmodel] = ea_load_reconstruction(varargin)" + newline + ...
    "coords = []; trajectory = {[0,0,0;0,10,0],[0,0,0;0,10,0]}; markers = [];" + newline + ...
    "elmodel = 'Fixture Electrode';" + newline + ...
    "end" + newline);
write_stub(stubDir, 'ea_space.m', ...
    "function path = ea_space(varargin)" + newline + ...
    "path = tempdir;" + newline + ...
    "end" + newline);
write_stub(stubDir, 'mh_vta_run_horn_with_retry.m', ...
    "function diagnostics = mh_vta_run_horn_with_retry(varargin)" + newline + ...
    "expectedPath = varargin{5};" + newline + ...
    "mesh = struct('pnt', [0,0,0;10,-20,30;-40,50,-60], 'unit', 'mm');" + newline + ...
    "vol = struct('pos', double(mesh.pnt));" + newline + ...
    "centroids = []; wmboundary = []; elfv = []; meshregions = [];" + newline + ...
    "save(expectedPath, 'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions', '-v7.3');" + newline + ...
    "diagnostics = struct('attempt_count', 1);" + newline + ...
    "end" + newline);
write_stub(stubDir, 'ea_getactiveidx.m', ...
    "function activeidx = ea_getactiveidx(varargin)" + newline + ...
    "markerPath = getenv('MH_VTA_ACTIVE_INDEX_MARKER');" + newline + ...
    "fid = fopen(markerPath, 'w');" + newline + ...
    "assert(fid > 0, 'Could not create active-index marker.');" + newline + ...
    "fprintf(fid, 'called'); fclose(fid);" + newline + ...
    "activeidx = [];" + newline + ...
    "error('test:ActiveIndexCalled', 'ea_getactiveidx was called.');" + newline + ...
    "end" + newline);
end

function write_stub(stubDir, name, contents)
path = fullfile(stubDir, name);
fid = fopen(path, 'w');
assert(fid > 0, 'Could not write backend test stub: %s', path);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', char(contents));
end

function cleanup_backend_fixture(testRoot, stubDir, previousMarker)
if isfolder(stubDir)
    rmpath(stubDir);
end
clear_backend_fixture_functions();
setenv('MH_VTA_ACTIVE_INDEX_MARKER', previousMarker);
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end

function clear_backend_fixture_functions()
clear ea_getptopts ea_resolve_elspec mh_vta_configure_canonical_options ea_space;
clear ea_initializeS ea_activecontacts ea_load_reconstruction;
clear mh_vta_run_horn_with_retry;
clear ea_getactiveidx mh_vta_backend_simbio_onesolve_canonical;
clear mh_vta_resolve_canonical_context mh_vta_get_canonical_headmodel;
clear mh_vta_build_geometry_stimulation;
end
