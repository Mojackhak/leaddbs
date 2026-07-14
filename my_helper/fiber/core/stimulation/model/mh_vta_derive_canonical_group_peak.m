function status = mh_vta_derive_canonical_group_peak(task, varargin)
% Derive an alternating group peak from completed source-level E-fields.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.addParameter('TaskId', char(string(task.task_id)), ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
parser.parse(varargin{:});
emit = parser.Results.EventEmitter;
taskId = char(string(parser.Results.TaskId));

nativeLeaf = char(string(task.output_leaves.native));
mniLeaf = char(string(task.output_leaves.MNI152NLin2009bAsym));
nativeEfield = fullfile(nativeLeaf, 'efield.nii.gz');
mniEfield = fullfile(mniLeaf, 'efield.nii.gz');
stageTimer = tic;
actions = mh_vta_resolve_output_actions(task);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'task_runtime_resolution', 'executed', toc(stageTimer), '');

if actions.solve_native_efield
    alternatingRoot = fileparts(fileparts(nativeLeaf));
    sourcePaths = cell(1, numel(task.sources));
    for sourceIndex = 1:numel(task.sources)
        sourcePaths{sourceIndex} = fullfile(alternatingRoot, 'sources', ...
            ['source-', char(string(task.sources(sourceIndex).source_id))], ...
            'efield.nii.gz');
        if ~isfile(sourcePaths{sourceIndex})
            error('mh_vta:MissingGroupPeakDependency', ...
                'Alternating source E-field is missing: %s', ...
                sourcePaths{sourceIndex});
        end
    end
    mh_vta_publish_atomic(nativeEfield, @(temporaryPath) ...
        compose_group_peak(sourcePaths, temporaryPath, emit, taskId), ...
        'EventEmitter', emit, 'TaskId', taskId);
end

write_requested_thresholds(nativeEfield, nativeLeaf, ...
    task.model.thresholds_v_per_m, actions.native_threshold_names, ...
    emit, taskId);

if actions.transform_mni_efield
    require_file(nativeEfield, 'native group-peak E-field');
    options = ea_getptopts(char(string(task.subject_dir)), struct());
    options.subj.recon.recon = char(string(task.reconstruction_path));
    mniReference = fullfile(ea_space(options), 't1.nii');
    mh_vta_publish_atomic(mniEfield, @(temporaryPath) ...
        transform_to_mni(nativeEfield, options, mniReference, ...
            temporaryPath, emit, taskId), ...
        'EventEmitter', emit, 'TaskId', taskId);
end

write_requested_thresholds(mniEfield, mniLeaf, ...
    task.model.thresholds_v_per_m, actions.mni_threshold_names, ...
    emit, taskId);

status = struct( ...
    'task_id', task.task_id, ...
    'execution', 'derived', ...
    'native_efield', nativeEfield, ...
    'mni_efield', mniEfield);
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

function compose_group_peak(sourcePaths, outputPath, emit, taskId)
stageTimer = tic;
mh_vta_compose_group_peak(sourcePaths, outputPath);
mh_vta_emit_stage_timing(emit, 'task', taskId, ...
    'group_peak_composition', 'executed', toc(stageTimer), '');
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
