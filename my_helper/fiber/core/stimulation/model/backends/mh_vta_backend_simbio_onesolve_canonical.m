function status = mh_vta_backend_simbio_onesolve_canonical(task, varargin)
% Execute one canonical voltage- or current-controlled SimBio solve.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('NativeAnchorPath', '', ...
    @(value) ischar(value) || isstring(value));
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('TaskId', char(string(task.task_id)), ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.addParameter('SubjectRuntime', [], ...
    @(value) isempty(value) || isstruct(value) && isscalar(value));
parser.parse(varargin{:});

emit = parser.Results.EventEmitter;
taskId = char(string(parser.Results.TaskId));
runtime = parser.Results.SubjectRuntime;
if isempty(runtime)
    runtime = mh_vta_create_subject_runtime(task.subject_id);
end
stageTimer = tic;
actions = mh_vta_resolve_output_actions(task);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'task_runtime_resolution', 'executed', toc(stageTimer), '');
headmodelState = 'not_required';
headmodelKey = '';
options = struct();
sideIndex = NaN;
mesh = struct();
gradient = [];
anchorPath = '';
trajectory = [];
mniReference = '';

if actions.solve_native_efield
    stageTimer = tic;
    [context, cacheStatus] = mh_vta_resolve_canonical_context(task, runtime);
    options = context.options;
    sideIndex = context.side_index;
    trajectory = context.trajectory;
    mniReference = context.mni_reference;
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'subject_reconstruction_context', 'executed', ...
        toc(stageTimer), cacheStatus);
elseif actions.transform_mni_efield
    stageTimer = tic;
    [transformContext, cacheStatus] = ...
        mh_vta_resolve_transform_context(task, runtime);
    options = transformContext.options;
    mniReference = transformContext.mni_reference;
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'subject_reconstruction_context', 'executed', ...
        toc(stageTimer), cacheStatus);
end

if actions.solve_native_efield
    anchorPath = mh_vta_resolve_native_anchor( ...
        context.native_anchor_path, parser.Results.NativeAnchorPath);
    S = mh_vta_build_geometry_stimulation(task, options, sideIndex);
    labelId = char(string(task.task_id));
    stimLabel = ['canonical-', labelId(1:min(12, numel(labelId)))];
    stageTimer = tic;
    [hm, headmodelState, cacheStatus, headmodelKey] = ...
        mh_vta_get_canonical_headmodel( ...
            task, context, S, runtime, stimLabel);
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'headmodel_build_or_load', 'executed', toc(stageTimer), cacheStatus);

    stageTimer = tic;
    activeidx = ea_getactiveidx(S, sideIndex, hm.centroids, hm.mesh, ...
        hm.elfv, options.elspec, hm.meshregions);
    controlMode = lower(char(string(task.sources(1).control_mode)));
    boundary = mh_vta_assemble_boundary( ...
        task.sources, activeidx, controlMode);
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'active_contact_boundary', 'executed', toc(stageTimer), '');
    potential = mh_vta_fem_apply_dbs( ...
        hm.vol, boundary.node_indices, boundary.values_and_groups, ...
        boundary.unipolar, boundary.constvol, hm.wmboundary, ...
        'EventEmitter', emit, 'TaskId', taskId, ...
        'SubjectRuntime', runtime, 'HeadmodelKey', headmodelKey, ...
        'ControlMode', controlMode);
    stageTimer = tic;
    gradient = mh_vta_fem_calc_gradient(hm.vol, potential);
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'gradient_calculation', 'executed', toc(stageTimer), '');
    mesh = hm.mesh;
end

status = mh_vta_export_canonical_outputs(task, options, sideIndex, ...
    mesh, gradient, trajectory, anchorPath, headmodelState, ...
    'EventEmitter', emit, 'TaskId', taskId, ...
    'SubjectRuntime', runtime, 'HeadmodelKey', headmodelKey, ...
    'MniReference', mniReference);
end
