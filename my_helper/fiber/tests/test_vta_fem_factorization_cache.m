function tests = test_vta_fem_factorization_cache
% Verify exact, bounded process-local FEM factorization reuse.

tests = functiontests(localfunctions);
end

function setupOnce(testCase)
repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));
testCase.TestData.repoDir = repoDir;
end

function testVoltageAmplitudeChangeReusesExactFactorization(testCase)
runtime = mh_vta_create_subject_runtime('S001');
events = repmat(empty_event(), 0, 1);
vol = fixture_volume();
headmodelKey = register_headmodel(runtime, vol, 'A');

first = solve_cached(vol, 1, [-2, 1], true, true, 5, ...
    runtime, headmodelKey, 'voltage', @collect_event);
second = solve_cached(vol, 1, [-3, 1], true, true, 5, ...
    runtime, headmodelKey, 'voltage', @collect_event);
uncached = mh_vta_fem_apply_dbs(vol, 1, [-3, 1], true, true, 5);

verifyEqual(testCase, second, uncached, 'AbsTol', 1e-12);
verifyEqual(testCase, second, 1.5 * first, 'AbsTol', 1e-12);
verifyEqual(testCase, [events.stage]', repmat([ ...
    "fem_matrix_preparation"; ...
    "fem_preconditioner"; ...
    "fem_pcg_solve"], 2, 1));
verifyEqual(testCase, stage_cache_statuses(events), [ ...
    "fem_matrix_preparation", "miss"; ...
    "fem_preconditioner", "miss"; ...
    "fem_matrix_preparation", "hit"; ...
    "fem_preconditioner", "hit"]);
verifyEqual(testCase, double(runtime.caches.fem_factorization.Count), 1);

    function collect_event(~, fields)
        cacheStatus = "";
        if isfield(fields, 'cache_status')
            cacheStatus = string(fields.cache_status);
        end
        events(end + 1) = struct( ... %#ok<AGROW>
            'stage', string(fields.stage), ...
            'cache_status', cacheStatus);
    end
end

function testChangedVoltageNodesMissAndReplaceSoleEntry(testCase)
runtime = mh_vta_create_subject_runtime('S001');
events = repmat(empty_event(), 0, 1);
vol = fixture_volume();
headmodelKey = register_headmodel(runtime, vol, 'A');

solve_cached(vol, 1, [-2, 1], true, true, 5, ...
    runtime, headmodelKey, 'voltage', @collect_event);
solve_cached(vol, 2, [-2, 1], true, true, 5, ...
    runtime, headmodelKey, 'voltage', @collect_event);

statuses = stage_cache_statuses(events);
verifyEqual(testCase, statuses(:, 2), repmat("miss", 4, 1));
verifyEqual(testCase, double(runtime.caches.fem_factorization.Count), 1);

    function collect_event(~, fields)
        if isfield(fields, 'cache_status')
            events(end + 1) = struct( ... %#ok<AGROW>
                'stage', string(fields.stage), ...
                'cache_status', string(fields.cache_status));
        end
    end
end

function testCurrentInjectionChangeReusesStableReturnSystem(testCase)
runtime = mh_vta_create_subject_runtime('S001');
events = repmat(empty_event(), 0, 1);
vol = fixture_volume();
headmodelKey = register_headmodel(runtime, vol, 'A');

first = solve_cached(vol, 1, [1e-3, 1], true, false, 5, ...
    runtime, headmodelKey, 'current', @collect_event);
second = solve_cached(vol, 2, [2e-3, 1], true, false, 5, ...
    runtime, headmodelKey, 'current', @collect_event);
uncached = mh_vta_fem_apply_dbs(vol, 2, [2e-3, 1], true, false, 5);

verifyEqual(testCase, second, uncached, 'AbsTol', 1e-12);
verifyNotEqual(testCase, first, second);
verifyEqual(testCase, stage_cache_statuses(events), [ ...
    "fem_matrix_preparation", "miss"; ...
    "fem_preconditioner", "miss"; ...
    "fem_matrix_preparation", "hit"; ...
    "fem_preconditioner", "hit"]);

    function collect_event(~, fields)
        if isfield(fields, 'cache_status')
            events(end + 1) = struct( ... %#ok<AGROW>
                'stage', string(fields.stage), ...
                'cache_status', string(fields.cache_status));
        end
    end
end

function testCurrentBipolarInjectionChangeReusesReferenceSystem(testCase)
runtime = mh_vta_create_subject_runtime('S001');
events = repmat(empty_event(), 0, 1);
vol = fixture_volume();
headmodelKey = register_headmodel(runtime, vol, 'A');

solve_cached(vol, [2; 3], [1e-3, 1; -1e-3, 2], false, false, [], ...
    runtime, headmodelKey, 'current', @collect_event);
cached = solve_cached(vol, [3; 4], [2e-3, 1; -2e-3, 2], ...
    false, false, [], runtime, headmodelKey, 'current', @collect_event);
uncached = mh_vta_fem_apply_dbs( ...
    vol, [3; 4], [2e-3, 1; -2e-3, 2], false, false, []);

verifyEqual(testCase, cached, uncached, 'AbsTol', 1e-12);
verifyEqual(testCase, stage_cache_statuses(events), [ ...
    "fem_matrix_preparation", "miss"; ...
    "fem_preconditioner", "miss"; ...
    "fem_matrix_preparation", "hit"; ...
    "fem_preconditioner", "hit"]);

    function collect_event(~, fields)
        if isfield(fields, 'cache_status')
            events(end + 1) = struct( ... %#ok<AGROW>
                'stage', string(fields.stage), ...
                'cache_status', string(fields.cache_status));
        end
    end
end

function testControlReturnAndHeadmodelIdentityChangesMiss(testCase)
runtime = mh_vta_create_subject_runtime('S001');
events = repmat(empty_event(), 0, 1);
vol = fixture_volume();
headmodelA = register_headmodel(runtime, vol, 'A');
headmodelB = register_headmodel(runtime, vol, 'B');

solve_cached(vol, 1, [-2, 1], false, true, [], ...
    runtime, headmodelA, 'voltage', @collect_event);
solve_cached(vol, 2, [1e-3, 1], false, false, [], ...
    runtime, headmodelA, 'current', @collect_event);
solve_cached(vol, [1; 5], [-2, 1; 1, 2], false, true, [], ...
    runtime, headmodelA, 'voltage', @collect_event);
solve_cached(vol, 1, [-2, 1], true, true, 5, ...
    runtime, headmodelA, 'voltage', @collect_event);
solve_cached(vol, 1, [-2, 1], true, true, 5, ...
    runtime, headmodelB, 'voltage', @collect_event);

statuses = stage_cache_statuses(events);
verifyEqual(testCase, statuses(:, 2), repmat("miss", 10, 1));
verifyEqual(testCase, double(runtime.caches.fem_factorization.Count), 1);

    function collect_event(~, fields)
        if isfield(fields, 'cache_status')
            events(end + 1) = struct( ... %#ok<AGROW>
                'stage', string(fields.stage), ...
                'cache_status', string(fields.cache_status));
        end
    end
end

function testOrderingIsCanonicalAndRuntimeIdentityIsIsolated(testCase)
firstRuntime = mh_vta_create_subject_runtime('S001');
secondRuntime = mh_vta_create_subject_runtime('S001');
vol = fixture_volume();
firstHeadmodel = register_headmodel(firstRuntime, vol, 'A');
secondHeadmodel = register_headmodel(secondRuntime, vol, 'A');

solve_cached(vol, [2; 1], [-2, 1; 1, 2], false, true, [], ...
    firstRuntime, firstHeadmodel, 'voltage', []);
solve_cached(vol, [1; 2], [1, 2; -2, 1], false, true, [], ...
    firstRuntime, firstHeadmodel, 'voltage', []);
solve_cached(vol, [1; 2], [1, 2; -2, 1], false, true, [], ...
    secondRuntime, secondHeadmodel, 'voltage', []);

verifyEqual(testCase, double(firstRuntime.caches.fem_factorization.Count), 1);
verifyEqual(testCase, double(secondRuntime.caches.fem_factorization.Count), 1);
firstKeys = keys(firstRuntime.caches.fem_factorization);
secondKeys = keys(secondRuntime.caches.fem_factorization);
verifyEqual(testCase, firstKeys, secondKeys);
end

function testMissingHeadmodelIdentityDisablesCaching(testCase)
runtime = mh_vta_create_subject_runtime('S001');
events = repmat(empty_event(), 0, 1);
vol = fixture_volume();

solve_cached(vol, 1, [-2, 1], true, true, 5, ...
    runtime, '', 'voltage', @collect_event);
solve_cached(vol, 1, [-2, 1], true, true, 5, ...
    runtime, '', 'voltage', @collect_event);

verifyEqual(testCase, double(runtime.caches.fem_factorization.Count), 0);
verifyEmpty(testCase, events);

    function collect_event(~, fields)
        if isfield(fields, 'cache_status')
            events(end + 1) = struct( ... %#ok<AGROW>
                'stage', string(fields.stage), ...
                'cache_status', string(fields.cache_status));
        end
    end
end

function testControlModeMismatchFails(testCase)
runtime = mh_vta_create_subject_runtime('S001');
vol = fixture_volume();
headmodelKey = register_headmodel(runtime, vol, 'A');
verifyError(testCase, @() mh_vta_fem_apply_dbs( ...
    vol, 1, [-2, 1], true, true, 5, ...
    'SubjectRuntime', runtime, 'HeadmodelKey', headmodelKey, ...
    'ControlMode', 'current', 'TaskId', 'factorization-test'), ...
    'mh_vta_fem_apply_dbs:ControlModeMismatch');
end

function testArbitraryHeadmodelTokenIsRejected(testCase)
runtime = mh_vta_create_subject_runtime('S001');
verifyError(testCase, @() mh_vta_fem_apply_dbs( ...
    fixture_volume(), 1, [-2, 1], true, true, 5, ...
    'SubjectRuntime', runtime, 'HeadmodelKey', 'headmodel-A', ...
    'ControlMode', 'voltage'), ...
    'mh_vta:InvalidHeadmodelCacheIdentity');

vol = fixture_volume();
headmodelKey = register_headmodel(runtime, vol, 'A');
changed = vol;
changed.stiff(2, 2) = changed.stiff(2, 2) + 1;
verifyError(testCase, @() mh_vta_fem_apply_dbs( ...
    changed, 1, [-2, 1], true, true, 5, ...
    'SubjectRuntime', runtime, 'HeadmodelKey', headmodelKey, ...
    'ControlMode', 'voltage'), ...
    'mh_vta:InvalidHeadmodelCacheIdentity');
end

function potential = solve_cached(vol, elec, val, unipolar, constvol, ...
        boundarynodes, runtime, headmodelKey, mode, emitter)
callArgs = cache_arguments(runtime, headmodelKey, mode, emitter);
potential = mh_vta_fem_apply_dbs( ...
    vol, elec, val, unipolar, constvol, boundarynodes, callArgs{:});
end

function callArgs = cache_arguments(runtime, headmodelKey, mode, emitter)
callArgs = {'SubjectRuntime', runtime, 'HeadmodelKey', headmodelKey, ...
    'ControlMode', mode, 'TaskId', 'factorization-test'};
if ~isempty(emitter)
    callArgs = [callArgs, {'EventEmitter', emitter}];
end
end

function vol = fixture_volume()
fullMatrix = sparse([ ...
    4, -1,  0,  0, -1; ...
   -1,  4, -1,  0,  0; ...
    0, -1,  4, -1,  0; ...
    0,  0, -1,  4, -1; ...
   -1,  0,  0, -1,  4]);
halfDiagonal = spdiags(diag(fullMatrix) / 2, 0, 5, 5);
vol = struct( ...
    'pos', [0, 0, 0; 1, 0, 0; 0, 1, 0; 0, 0, 1; 1, 1, 1], ...
    'stiff', triu(fullMatrix, 1) + halfDiagonal);
end

function key = register_headmodel(runtime, vol, identity)
baseKey = mh_vta_runtime_cache_key('headmodel', {identity});
signature = {['/tmp/headmodel-', identity, '.mat'], 100, 1};
entry = struct( ...
    'headmodel', struct('vol', vol), ...
    'file_signature', {signature});
mh_vta_runtime_cache_store(runtime, 'headmodel', baseKey, entry);
key = mh_vta_runtime_cache_key( ...
    'validated_headmodel_instance', {baseKey, signature});
end

function event = empty_event()
event = struct('stage', "", 'cache_status', "");
end

function statuses = stage_cache_statuses(events)
keep = ismember([events.stage], [ ...
    "fem_matrix_preparation", "fem_preconditioner"]);
statuses = [[events(keep).stage]', [events(keep).cache_status]'];
end
