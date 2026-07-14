function status = mh_vta_export_canonical_outputs(task, options, sideIndex, ...
        mesh, gradient, trajectory, nativeAnchorPath, headmodelState, ...
        varargin)
% Publish canonical native/MNI E-fields and thresholded VTAs.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('TaskId', char(string(task.task_id)), ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.addParameter('SubjectRuntime', [], ...
    @(value) isempty(value) || isstruct(value) && isscalar(value));
parser.addParameter('HeadmodelKey', '', ...
    @(value) ischar(value) || isstring(value));
parser.addParameter('MniReference', '', ...
    @(value) ischar(value) || isstring(value));
parser.parse(varargin{:});
emit = parser.Results.EventEmitter;
taskId = char(string(parser.Results.TaskId));
runtime = parser.Results.SubjectRuntime;
if isempty(runtime)
    subjectId = '';
    if isfield(task, 'subject_id')
        subjectId = task.subject_id;
    end
    runtime = mh_vta_create_subject_runtime(subjectId);
end

nativeLeaf = char(string(task.output_leaves.native));
mniLeaf = char(string(task.output_leaves.MNI152NLin2009bAsym));
nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
mniEfield = fullfile(mniLeaf, 'efield.nii.gz');
actions = mh_vta_resolve_output_actions(task);

if actions.solve_native_efield
    fieldValues = sqrt(sum(double(gradient).^2, 2));
    stageTimer = tic;
    [geometry, cacheStatus] = mh_vta_get_export_geometry( ...
        task, mesh, trajectory, sideIndex, options.elspec, ...
        char(string(parser.Results.HeadmodelKey)), runtime);
    meshPointsMm = geometry.electrode_adjusted_points_mm;
    if numel(fieldValues) ~= numel(mesh.tissue)
        error('mh_vta:InvalidFemExportSamples', ...
            'Gradient values must align with FEM tetrahedra.');
    end
    fieldValues = fieldValues(geometry.final_field_value_indices);
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'electrode_removal_geometry', 'executed', ...
        toc(stageTimer), cacheStatus);
    stageTimer = tic;
    [nativeAnchor, cacheStatus] = mh_vta_get_native_anchor( ...
        nativeAnchorPath, runtime);
    mh_vta_emit_stage_timing(emit, 'task', taskId, ...
        'native_anchor_load', 'executed', toc(stageTimer), cacheStatus);
    mh_vta_publish_atomic(nativeEfield, @(temporaryPath) ...
        export_native_grid(meshPointsMm, fieldValues, nativeAnchorPath, ...
            nativeAnchor, temporaryPath, emit, taskId), ...
        'EventEmitter', emit, 'TaskId', taskId);
end

write_requested_thresholds(nativeEfield, nativeLeaf, ...
    task.model.thresholds_v_per_m, actions.native_threshold_names, ...
    emit, taskId);

if actions.transform_mni_efield
    require_file(nativeEfield, 'native E-field');
    [transformOptions, mniReference] = transform_context( ...
        task, options, parser.Results.MniReference);
    mh_vta_publish_atomic(mniEfield, @(temporaryPath) ...
        transform_to_mni(nativeEfield, transformOptions, mniReference, ...
            temporaryPath, emit, taskId), ...
        'EventEmitter', emit, 'TaskId', taskId);
end

write_requested_thresholds(mniEfield, mniLeaf, ...
    task.model.thresholds_v_per_m, actions.mni_threshold_names, ...
    emit, taskId);

status = struct( ...
    'task_id', task.task_id, ...
    'execution', 'solve', ...
    'headmodel_state', headmodelState, ...
    'native_efield', nativeEfield, ...
    'mni_efield', mniEfield);
end

function [options, mniReference] = transform_context( ...
        task, options, resolvedReference)
if ~isstruct(options) || ~isfield(options, 'subj') || ...
        ~isfield(options.subj, 'subjDir')
    error('mh_vta:MissingCanonicalTransformContext', ...
        'Canonical MNI export requires resolved subject context.');
end
options.subj.recon.recon = char(string(task.reconstruction_path));
if strlength(string(resolvedReference)) == 0
    mniReference = fullfile(ea_space(options), 't1.nii');
else
    mniReference = char(string(resolvedReference));
end
end

function write_requested_thresholds(efieldPath, leaf, thresholds, ...
        requestedNames, emit, taskId)
if isempty(requestedNames)
    return;
end
thresholds = double(thresholds(:));
requestedThresholds = zeros(numel(thresholds), 1);
outputPaths = strings(numel(thresholds), 1);
requestedCount = 0;
for thresholdIndex = 1:numel(thresholds)
    threshold = thresholds(thresholdIndex);
    token = strrep(sprintf('%.2f', threshold / 1000), '.', 'p');
    name = "vta_threshold-" + token + "Vpermm.nii.gz";
    if ~any(requestedNames == name)
        continue;
    end
    requestedCount = requestedCount + 1;
    requestedThresholds(requestedCount) = threshold;
    outputPaths(requestedCount) = string(fullfile(leaf, char(name)));
end
requestedThresholds = requestedThresholds(1:requestedCount);
outputPaths = outputPaths(1:requestedCount);
mh_vta_threshold_efields(efieldPath, requestedThresholds, outputPaths, ...
    'EventEmitter', emit, 'TaskId', taskId);
end

function export_native_grid(points, values, anchorPath, anchor, ...
        outputPath, emit, taskId)
stageTimer = tic;
mh_vta_export_common_grid(points, values, anchorPath, outputPath, ...
    'Anchor', anchor);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'native_grid_interpolation', 'executed', toc(stageTimer), '');
end

function transform_to_mni(efieldPath, options, reference, outputPath, emit, taskId)
stageTimer = tic;
mh_vta_transform_efield_to_mni(efieldPath, options, reference, outputPath);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'native_to_mni_transform', 'executed', toc(stageTimer), '');
end

function require_file(path, label)
if ~isfile(path)
    error('mh_vta:MissingCanonicalDependency', ...
        'Missing %s: %s', label, path);
end
end
