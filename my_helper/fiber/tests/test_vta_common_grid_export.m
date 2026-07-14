function tests = test_vta_common_grid_export
% Validate canonical head-model preparation and fixed-grid VTA exports.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.repoDir = repoDir;
end

function testThresholdUsesInclusiveIndicatorAndUint8(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));

inputPath = fullfile(testRoot, 'efield.nii');
outputPath = fullfile(testRoot, 'vta.nii');
write_fixture_nifti(inputPath, single(reshape([179, 180, 220, 221, NaN], [5, 1, 1])), eye(4));

mh_vta_threshold_efield(inputPath, 180, outputPath);

nii = ea_load_nii(outputPath);
verifyEqual(testCase, uint8(nii.img), uint8(reshape([0, 1, 1, 1, 0], [5, 1, 1])));
header = spm_vol(outputPath);
verifyEqual(testCase, header.dt(1), 2);
end

function testSharedExporterRepairsThresholdWithoutControlModeBranch(testCase)
testRoot = tempname;
nativeLeaf = fullfile(testRoot, 'native');
mniLeaf = fullfile(testRoot, 'mni');
mkdir(nativeLeaf);
mkdir(mniLeaf);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
write_fixture_nifti(nativeEfield, ...
    single(reshape([179, 180, 220], [3, 1, 1])), eye(4));
task = struct( ...
    'task_id', 'shared-export-test', ...
    'output_leaves', struct('native', nativeLeaf, ...
        'MNI152NLin2009bAsym', mniLeaf), ...
    'missing_artifacts', struct('native', ...
        {{'vta_threshold-0p20Vpermm.nii.gz'}}), ...
    'model', struct('thresholds_v_per_m', [180, 200, 220]));
events = {};

status = mh_vta_export_canonical_outputs(task, struct(), 1, ...
    struct(), [], [], '', 'not_required', ...
    'EventEmitter', @collect_event, 'TaskId', task.task_id);

output = fullfile(nativeLeaf, 'vta_threshold-0p20Vpermm.nii.gz');
verifyTrue(testCase, isfile(output));
verifyEqual(testCase, uint8(ea_load_nii(output).img), ...
    uint8(reshape([0, 0, 1], [3, 1, 1])));
verifyEqual(testCase, string(status.execution), "solve");
verifyEqual(testCase, string(cellfun( ...
    @(event) event.stage, events, 'UniformOutput', false)), ...
    ["threshold_generation", "artifact_publication"]);

    function collect_event(eventType, fields)
        verifyEqual(testCase, eventType, 'stage_timing');
        events{end + 1} = fields;
    end
end

function testExportMatchesAnchorGeometryAndPreservesOutsideNaN(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));

anchorPath = fullfile(testRoot, 'anchor.nii');
outputPath = fullfile(testRoot, 'efield.nii');
anchorAffine = [2, 0, 0, -2; 0, 3, 0, -3; 0, 0, 4, -4; 0, 0, 0, 1];
write_fixture_nifti(anchorPath, zeros(3, 3, 3, 'single'), anchorAffine);

[x, y, z] = ndgrid(1:2, 1:2, 1:2);
meshVoxels = [x(:), y(:), z(:)];
meshPoints = ea_vox2mm(meshVoxels, anchorAffine);
fieldValues = sum(meshVoxels, 2);

mh_vta_export_common_grid(meshPoints, fieldValues, anchorPath, outputPath);

anchor = ea_load_nii(anchorPath);
output = ea_load_nii(outputPath);
verifyEqual(testCase, size(output.img), size(anchor.img));
verifyEqual(testCase, output.mat, anchor.mat, 'AbsTol', 1e-12);
verifyEqual(testCase, output.img(1, 1, 1), 3, 'AbsTol', 1e-6);
verifyTrue(testCase, isnan(output.img(3, 3, 3)));
end

function testAcceptanceAnchorOverrideUsesExistingReferenceGrid(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
defaultAnchor = fullfile(testRoot, 'default.nii');
acceptanceAnchor = fullfile(testRoot, 'acceptance.nii');
write_fixture_nifti(defaultAnchor, zeros(2, 2, 2, 'single'), eye(4));
write_fixture_nifti(acceptanceAnchor, zeros(3, 3, 3, 'single'), eye(4));

verifyEqual(testCase, ...
    mh_vta_resolve_native_anchor(defaultAnchor, ''), defaultAnchor);
verifyEqual(testCase, ...
    mh_vta_resolve_native_anchor(defaultAnchor, acceptanceAnchor), ...
    acceptanceAnchor);
end

function testAcceptanceAnchorOverrideRejectsMissingPath(testCase)
verifyError(testCase, @() mh_vta_resolve_native_anchor( ...
    '/tmp/default-anchor.nii', '/tmp/missing-acceptance-anchor.nii'), ...
    'mh_vta:MissingNativeAnchorOverride');
end

function testElectrodeTissueSamplesAreExcludedBeforeExport(testCase)
mesh = struct('tissue', [1; 2; 3; 4]);
points = reshape(1:12, 4, 3);
values = [10; 20; 30; 40];

[filteredPoints, filteredValues, keep] = ...
    mh_vta_filter_export_samples(mesh, points, values);

verifyEqual(testCase, keep, [true; true; false; false]);
verifyEqual(testCase, filteredPoints, points(1:2, :));
verifyEqual(testCase, filteredValues, values(1:2));
end

function testCanonicalExporterDoesNotHighFieldFillElectrodeTetrahedra(testCase)
source = fileread(which('mh_vta_export_canonical_outputs'));

verifyFalse(testCase, contains(source, 'fill_electrode_tetrahedra'));
end

function testElectrodeTissueFilterRejectsMisalignedSamples(testCase)
mesh = struct('tissue', [1; 2; 3]);
verifyError(testCase, @() mh_vta_filter_export_samples( ...
    mesh, zeros(2, 3), zeros(2, 1)), ...
    'mh_vta:InvalidFemExportSamples');
end

function testElectrodeRemovalMatchesAxialRadialDisplacement(testCase)
mesh = struct('tissue', [1; 2; 3]);
points = [2, 5, 0; 2, -1, 0; 3, 5, 0];
values = [10; 20; 30];
trajectory = cell(1, 2);
trajectory{1} = [0, 0, 0; 0, 10, 0];
elspec = struct('lead_diameter', 1.2);

[adjustedPoints, adjustedValues] = ...
    mh_vta_remove_electrode_export_samples( ...
        mesh, points, values, trajectory, 1, elspec);

verifyEqual(testCase, adjustedPoints, [1.4, 5, 0; 2, -1, 0], ...
    'AbsTol', 1e-12);
verifyEqual(testCase, adjustedValues, [10; 20]);
end

function testElectrodeRemovalDropsSamplesInsideLeadRadius(testCase)
mesh = struct('tissue', [1; 1]);
points = [0.1, 5, 0; 2, 5, 0];
values = [10; 20];
trajectory = {[0, 0, 0; 0, 10, 0]};
elspec = struct('lead_diameter', 1.2);

[adjustedPoints, adjustedValues] = ...
    mh_vta_remove_electrode_export_samples( ...
        mesh, points, values, trajectory, 1, elspec);

verifyEqual(testCase, adjustedPoints, [1.4, 5, 0], 'AbsTol', 1e-12);
verifyEqual(testCase, adjustedValues, 20);
end

function testTransformUsesForwardNormalization(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
mkdir(stubDir);
cleanup = onCleanup(@() cleanup_transform_fixture(testRoot, stubDir));

inputPath = fullfile(testRoot, 'native.nii');
outputPath = fullfile(testRoot, 'mni.nii');
referencePath = fullfile(testRoot, 'mni_reference.nii');
logPath = fullfile(testRoot, 'normalization_call.mat');
write_fixture_nifti(inputPath, single(reshape(1:8, [2, 2, 2])), eye(4));
write_fixture_nifti(referencePath, zeros(2, 2, 2, 'single'), diag([2, 2, 2, 1]));
write_normalization_stub(stubDir);
setenv('MH_VTA_NORMALIZATION_LOG', logPath);
addpath(stubDir, '-begin');
clear ea_apply_normalization_tofile;
rehash;

options = struct('subj', struct('subjDir', testRoot));
mh_vta_transform_efield_to_mni(inputPath, options, referencePath, outputPath);

call = load(logPath);
verifyEqual(testCase, call.useinverse, 0);
verifyEqual(testCase, call.interp, 1);
verifyEqual(testCase, call.ref, referencePath);
verifyTrue(testCase, isfile(outputPath));
end

function testAtomicPublisherPreservesExistingFinalFile(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
outputPath = fullfile(testRoot, 'efield.nii.gz');
write_text(outputPath, 'existing');
producerCalled = false;

published = mh_vta_publish_atomic(outputPath, @producer);

verifyFalse(testCase, published);
verifyFalse(testCase, producerCalled);
verifyEqual(testCase, fileread(outputPath), 'existing');

    function producer(path)
        producerCalled = true;
        write_text(path, 'replacement');
    end
end

function testAtomicPublisherCreatesMissingFinalFile(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
outputPath = fullfile(testRoot, 'efield.nii.gz');

published = mh_vta_publish_atomic(outputPath, ...
    @(path) write_text(path, 'generated'));

verifyTrue(testCase, published);
verifyEqual(testCase, fileread(outputPath), 'generated');
end

function testAtomicPublisherEmitsPublicationAfterFinalFileExists(testCase)
testRoot = tempname;
mkdir(testRoot);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
outputPath = fullfile(testRoot, 'efield.nii.gz');
observed = struct();

published = mh_vta_publish_atomic(outputPath, ...
    @(path) write_text(path, 'generated'), ...
    'EventEmitter', @collect_event, 'TaskId', 'task-001');

verifyTrue(testCase, published);
verifyTrue(testCase, isfile(outputPath));
verifyEqual(testCase, string(observed.stage), "artifact_publication");
verifyEqual(testCase, string(observed.task_id), "task-001");
verifyGreaterThanOrEqual(testCase, observed.duration_seconds, 0);

    function collect_event(eventType, fields)
        verifyEqual(testCase, eventType, 'stage_timing');
        verifyTrue(testCase, isfile(outputPath));
        observed = fields;
    end
end

function testAllRequestedThresholdsEmitGenerationThenPublication(testCase)
testRoot = tempname;
nativeLeaf = fullfile(testRoot, 'native');
mniLeaf = fullfile(testRoot, 'mni');
mkdir(nativeLeaf);
mkdir(mniLeaf);
cleanup = onCleanup(@() rmdir(testRoot, 's'));
write_fixture_nifti(fullfile(nativeLeaf, 'efield.nii.gz'), ...
    single(reshape([179, 180, 200, 220], [4, 1, 1])), eye(4));
task = struct( ...
    'task_id', 'all-thresholds-test', ...
    'output_leaves', struct('native', nativeLeaf, ...
        'MNI152NLin2009bAsym', mniLeaf), ...
    'missing_artifacts', struct('native', {{ ...
        'vta_threshold-0p18Vpermm.nii.gz', ...
        'vta_threshold-0p20Vpermm.nii.gz', ...
        'vta_threshold-0p22Vpermm.nii.gz'}}), ...
    'model', struct('thresholds_v_per_m', [180, 200, 220]));
stages = strings(0, 1);

mh_vta_export_canonical_outputs(task, struct(), 1, ...
    struct(), [], [], '', 'not_required', ...
    'EventEmitter', @collect_event, 'TaskId', task.task_id);

verifyEqual(testCase, stages, repmat( ...
    ["threshold_generation"; "artifact_publication"], 3, 1));

    function collect_event(~, fields)
        stages(end + 1, 1) = string(fields.stage);
    end
end

function testFemSolveEmitsMatrixPreconditionerAndPcgOrder(testCase)
vol = struct( ...
    'pos', [0, 0, 0; 1, 0, 0; 0, 1, 0; 0, 0, 1], ...
    'stiff', speye(4));
stages = strings(0, 1);

potential = mh_vta_fem_apply_dbs( ...
    vol, 1, [1, 1], false, true, [], ...
    'EventEmitter', @collect_event, 'TaskId', 'fem-order-test');

verifyEqual(testCase, potential, [1; 0; 0; 0], 'AbsTol', 1e-12);
verifyEqual(testCase, stages, [ ...
    "fem_matrix_preparation"; ...
    "fem_preconditioner"; ...
    "fem_pcg_solve"]);

    function collect_event(~, fields)
        stages(end + 1, 1) = string(fields.stage);
    end
end

function testHeadmodelBuildAndExistingStructurallyValidModelIsReused(testCase)
testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
subjectDir = fullfile(testRoot, 'sub-SNr003');
mkdir(stubDir);
mkdir(subjectDir);
cleanup = onCleanup(@() cleanup_headmodel_fixture(testRoot, stubDir));

write_headmodel_builder_stub(stubDir);
addpath(stubDir, '-begin');
clear mh_vta_run_horn_with_retry;
rehash;

options = fixture_options(subjectDir);
[headmodelPath, state] = mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation');

verifyEqual(testCase, state, 'built');
verifyTrue(testCase, isfile(headmodelPath));

[reusedPath, reusedState] = mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation');
verifyEqual(testCase, reusedPath, headmodelPath);
verifyEqual(testCase, reusedState, 'reused');
end

function testUnreadableOrIncompleteHeadmodelIsRejectedWithoutOverwrite(testCase)
testRoot = tempname;
subjectDir = fullfile(testRoot, 'sub-SNr003');
headmodelDir = fullfile(subjectDir, 'headmodel', 'native');
mkdir(headmodelDir);
cleanup = onCleanup(@() rmdir(testRoot, 's'));

options = fixture_options(subjectDir);
headmodelPath = fullfile(headmodelDir, 'sub-SNr003_desc-headmodel1.mat');
unrelated = true;
save(headmodelPath, 'unrelated');
originalHash = mh_fiber_file_sha256(headmodelPath);

verifyError(testCase, @() mh_vta_prepare_canonical_headmodel( ...
    struct(), 1, options, 'fixture-stimulation'), ...
    'mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel');
verifyEqual(testCase, mh_fiber_file_sha256(headmodelPath), originalHash);
end

function options = fixture_options(subjectDir)
options = struct();
options.native = 1;
options.subj = struct('subjDir', subjectDir, 'subjId', 'SNr003');
end

function write_fixture_nifti(path, image, affine)
nii = struct();
nii.fname = path;
nii.dim = size(image);
if numel(nii.dim) < 3
    nii.dim(end+1:3) = 1;
end
nii.dt = [16, 0];
nii.mat = affine;
nii.n = [1, 1];
nii.pinfo = [1; 0; 0];
nii.descrip = 'VTA test fixture';
nii.img = image;
ea_write_nii(nii);
end

function write_normalization_stub(stubDir)
path = fullfile(stubDir, 'ea_apply_normalization_tofile.m');
text = ...
    "function ea_apply_normalization_tofile(options, from, to, useinverse, interp, ref)" + newline + ...
    "logPath = getenv('MH_VTA_NORMALIZATION_LOG');" + newline + ...
    "save(logPath, 'options', 'from', 'to', 'useinverse', 'interp', 'ref');" + newline + ...
    "copyfile(from, to);" + newline + ...
    "end" + newline;
write_text(path, text);
end

function write_headmodel_builder_stub(stubDir)
path = fullfile(stubDir, 'mh_vta_run_horn_with_retry.m');
text = ...
    "function diagnostics = mh_vta_run_horn_with_retry(varargin)" + newline + ...
    "expectedPath = varargin{5};" + newline + ...
    "mesh = struct('pnt',[0,0,0;10,-20,30;-40,50,-60],'unit','mm');" + newline + ...
    "vol = struct('pos',double(mesh.pnt)/1000);" + newline + ...
    "centroids = []; wmboundary = [];" + newline + ...
    "elfv = []; meshregions = [];" + newline + ...
    "save(expectedPath, 'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions', '-v7.3');" + newline + ...
    "diagnostics = struct('attempt_count', 1);" + newline + ...
    "end" + newline;
write_text(path, text);
end

function write_text(path, contents)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not write test stub: %s', path);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', char(contents));
end

function cleanup_transform_fixture(testRoot, stubDir)
if isfolder(stubDir)
    rmpath(stubDir);
end
clear ea_apply_normalization_tofile;
setenv('MH_VTA_NORMALIZATION_LOG', '');
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end

function cleanup_headmodel_fixture(testRoot, stubDir)
if isfolder(stubDir)
    rmpath(stubDir);
end
clear mh_vta_run_horn_with_retry;
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
