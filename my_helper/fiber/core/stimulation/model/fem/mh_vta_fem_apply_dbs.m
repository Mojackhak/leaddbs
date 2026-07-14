function potential = mh_vta_fem_apply_dbs(vol, elec, val, unipolar, ...
        constvol, boundarynodes, varargin)
% Apply DBS boundary conditions and solve the FEM system.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('TaskId', '', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.addParameter('SubjectRuntime', [], ...
    @(value) isempty(value) || isstruct(value) && isscalar(value));
parser.addParameter('HeadmodelKey', '', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.addParameter('ControlMode', '', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.parse(varargin{:});
emit = parser.Results.EventEmitter;
taskId = char(string(parser.Results.TaskId));
runtime = parser.Results.SubjectRuntime;
headmodelKey = char(string(parser.Results.HeadmodelKey));
controlMode = resolve_control_mode(parser.Results.ControlMode, constvol);

if constvol
    if unipolar
        dirinodes = [boundarynodes, elec'];
    else
        dirinodes = elec;
    end
    rhs = zeros(length(vol.pos), 1);
    dirival = zeros(size(vol.pos, 1), 1);
    dirival(elec) = val(:, 1);
else
    if unipolar
        dirinodes = boundarynodes;
    else
        dirinodes = 1;
    end
    dirival = zeros(size(vol.pos, 1), 1);
    rhs = zeros(size(vol.pos, 1), 1);
    uvals = unique(val(:, 2));
    if unipolar && isscalar(uvals)
        elecCenterId = find_elec_center(elec, vol.pos);
        rhs(elecCenterId) = val(1, 1);
    else
        for v = 1:numel(uvals)
            elecCenterId = find_elec_center(elec(val(:, 2) == uvals(v)), vol.pos);
            thesevals = val(val(:, 2) == uvals(v), 1);
            rhs(elecCenterId) = thesevals(1);
        end
    end
end

dirinodes = unique(dirinodes(:), 'sorted');
cacheKey = '';
cacheStatus = '';
cacheEntry = [];
stageTimer = tic;
if ~isempty(runtime) && ~isempty(headmodelKey)
    validate_headmodel_identity(runtime, headmodelKey, vol.stiff);
    cacheKey = factorization_cache_key( ...
        headmodelKey, controlMode, unipolar, dirinodes, vol.stiff);
    [cacheEntry, cacheHit] = mh_vta_runtime_cache_lookup( ...
        runtime, 'fem_factorization', cacheKey);
    if cacheHit
        cacheStatus = 'hit';
    else
        cacheStatus = 'miss';
        clear_factorization_cache(runtime);
    end
else
    cacheHit = false;
end

if cacheHit
    stiff = cacheEntry.conditioned_stiffness;
    symmetricStiffness = cacheEntry.symmetric_stiffness;
    rhs = condition_rhs(symmetricStiffness, rhs, dirinodes, dirival);
else
    [stiff, rhs, symmetricStiffness] = ...
        dbs_matrix(vol.stiff, rhs, dirinodes, dirival);
end
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'fem_matrix_preparation', 'executed', toc(stageTimer), cacheStatus);

stageTimer = tic;
if cacheHit
    preconditioner = cacheEntry.preconditioner;
else
    preconditioner = build_preconditioner(stiff);
    if ~isempty(cacheKey)
        cacheEntry = struct( ...
            'cache_key', cacheKey, ...
            'symmetric_stiffness', symmetricStiffness, ...
            'conditioned_stiffness', stiff, ...
            'preconditioner', preconditioner);
        mh_vta_runtime_cache_store( ...
            runtime, 'fem_factorization', cacheKey, cacheEntry);
    end
end
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'fem_preconditioner', 'executed', toc(stageTimer), cacheStatus);
potential = solve_system(stiff, rhs, preconditioner, emit, taskId);
end

function centerId = find_elec_center(elec, pos)
center = mean(pos(elec, :));
distCenter = sqrt(sum((pos(elec, :) - repmat(center, numel(elec), 1)).^2, 2));
[~, elecId] = min(distCenter);
centerId = elec(elecId);
end

function [stiff, rhs, symmetricStiffness] = ...
        dbs_matrix(stiff, rhs, dirinodes, dirival)
diagonal = diag(stiff);
symmetricStiffness = stiff + stiff';
rhs = condition_rhs(symmetricStiffness, rhs, dirinodes, dirival);
stiff = symmetricStiffness;
stiff(dirinodes, :) = 0.0;
stiff(:, dirinodes) = 0.0;
diagonal = -diagonal;
diagonal(dirinodes) = 1.0;
stiff = stiff + spdiags(diagonal(:), 0, length(diagonal), length(diagonal));
end

function rhs = condition_rhs(symmetricStiffness, rhs, dirinodes, dirival)
rhs = rhs - symmetricStiffness * dirival;
rhs(dirinodes) = dirival(dirinodes);
end

function preconditioner = build_preconditioner(sysmat)
try
    preconditioner = ichol(sysmat);
catch
    alpha = max(sum(abs(sysmat), 2) ./ diag(sysmat)) - 2;
    preconditioner = ichol(sysmat, struct( ...
        'type', 'ict', 'droptol', 1e-3, 'diagcomp', alpha));
end
end

function x = solve_system(sysmat, vecb, preconditioner, emit, taskId) %#ok<INUSD>
stageTimer = tic;
[~, x] = evalc(['pcg(sysmat, vecb, 10e-10, 5000, ' ...
    'preconditioner, preconditioner'', vecb)']);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'fem_pcg_solve', 'executed', toc(stageTimer), '');
end

function mode = resolve_control_mode(value, constvol)
expected = 'current';
if constvol
    expected = 'voltage';
end
if strlength(string(value)) == 0
    mode = expected;
    return;
end
mode = lower(strtrim(char(string(value))));
if ~strcmp(mode, expected)
    error('mh_vta_fem_apply_dbs:ControlModeMismatch', ...
        'ControlMode does not match the constvol boundary mode.');
end
end

function key = factorization_cache_key( ...
        headmodelKey, controlMode, unipolar, dirinodes, stiffness)
returnDesign = 'bipolar';
if unipolar
    returnDesign = 'unipolar';
end
key = mh_vta_runtime_cache_key('fem_factorization_v1', { ...
    headmodelKey, controlMode, returnDesign, ...
    double(dirinodes(:))', double(size(stiffness)), ...
    'dbs_matrix_v1', 'pcg_tol_1e-9_maxit_5000', ...
    'initial_guess_rhs', ...
    'ichol_default_then_ict_droptol_1e-3_diagcomp'});
end

function clear_factorization_cache(runtime)
cache = runtime.caches.fem_factorization;
if cache.Count > 0
    remove(cache, keys(cache));
end
end

function validate_headmodel_identity(runtime, headmodelKey, stiffness)
try
    identity = jsondecode(headmodelKey);
catch
    invalid_headmodel_identity();
end
if ~isstruct(identity) || ~isscalar(identity) || ...
        ~isfield(identity, 'kind') || ...
        ~strcmp(char(string(identity.kind)), 'validated_headmodel_instance') || ...
        ~isfield(identity, 'parts') || ~iscell(identity.parts) || ...
        numel(identity.parts) ~= 2
    invalid_headmodel_identity();
end
baseKey = identity.parts{1};
signature = identity.parts{2};
if ~(ischar(baseKey) || isstring(baseKey) && isscalar(baseKey)) || ...
        ~iscell(signature)
    invalid_headmodel_identity();
end
signature = signature(:)';
[entry, hit] = mh_vta_runtime_cache_lookup( ...
    runtime, 'headmodel', char(string(baseKey)));
if ~hit || ~isstruct(entry) || ~isscalar(entry) || ...
        ~isfield(entry, 'file_signature') || ...
        ~isequal(entry.file_signature, signature) || ...
        ~isfield(entry, 'headmodel') || ~isstruct(entry.headmodel) || ...
        ~isfield(entry.headmodel, 'vol') || ...
        ~isfield(entry.headmodel.vol, 'stiff') || ...
        ~isequaln(entry.headmodel.vol.stiff, stiffness)
    invalid_headmodel_identity();
end
end

function invalid_headmodel_identity()
error('mh_vta:InvalidHeadmodelCacheIdentity', ...
    ['FEM factorization caching requires a validated head-model instance ' ...
    'registered in the same subject runtime.']);
end
