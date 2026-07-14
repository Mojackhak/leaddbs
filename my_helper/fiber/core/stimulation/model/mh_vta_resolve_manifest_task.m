function resolution = mh_vta_resolve_manifest_task(manifest, taskIndex)
% Resolve one validated manifest task to skip, copy, dependency skip, or ready.

validateattributes(taskIndex, {'numeric'}, ...
    {'scalar', 'integer', 'positive', '<=', numel(manifest.tasks)}, ...
    mfilename, 'taskIndex');
entry = manifest.tasks(taskIndex);
task = entry.task;
[missingArtifacts, initialMissingCount] = ...
    mh_vta_missing_task_artifacts(task);
if initialMissingCount == 0
    resolution = make_resolution('skipped_existing', task, 0, 0, strings(0, 1));
    return;
end

copiedCount = copy_from_donors( ...
    task, missingArtifacts, entry.reuse_candidate_ids, manifest.reuse_donors);
[missingArtifacts, missingCount] = mh_vta_missing_task_artifacts(task);
if missingCount == 0
    resolution = make_resolution('copied', task, copiedCount, 0, strings(0, 1));
    return;
end

task.missing_artifacts = missingArtifacts;
task = mh_vta_validate_canonical_task_runtime(task);
blockedDependencies = missing_required_dependencies(task, manifest.tasks);
if ~isempty(blockedDependencies)
    resolution = make_resolution('skipped_dependency', task, copiedCount, ...
        missingCount, blockedDependencies);
    return;
end
resolution = make_resolution('ready', task, copiedCount, ...
    missingCount, strings(0, 1));
end

function copiedCount = copy_from_donors(task, missingArtifacts, ...
        candidateIds, donors)
copiedCount = 0;
candidateIds = string(candidateIds);
candidateIds = candidateIds(:);
spaces = fieldnames(missingArtifacts);
donorIds = string({donors.donor_id});
for spaceIndex = 1:numel(spaces)
    space = spaces{spaceIndex};
    names = string(missingArtifacts.(space));
    for nameIndex = 1:numel(names)
        destination = fullfile(char(string(task.output_leaves.(space))), ...
            char(names(nameIndex)));
        for candidateIndex = 1:numel(candidateIds)
            donorIndex = find(donorIds == candidateIds(candidateIndex), 1);
            source = fullfile(char(string( ...
                donors(donorIndex).output_leaves.(space))), ...
                char(names(nameIndex)));
            if mh_vta_copy_artifact_atomic(source, destination)
                copiedCount = copiedCount + 1;
                break;
            end
        end
    end
end
end

function blocked = missing_required_dependencies(task, entries)
blocked = strings(0, 1);
if ~strcmp(task.kind, 'alternating_group_peak') || ...
        ~isfield(task.missing_artifacts, 'native') || ...
        ~any(string(task.missing_artifacts.native) == "efield.nii.gz")
    return;
end
entryTaskIds = string(arrayfun( ...
    @(entry) string(entry.task.task_id), entries, 'UniformOutput', false));
dependencies = string(task.dependencies);
dependencies = dependencies(:);
for dependencyIndex = 1:numel(dependencies)
    entryIndex = find(entryTaskIds == dependencies(dependencyIndex), 1);
    dependencyEfield = fullfile(char(string( ...
        entries(entryIndex).task.output_leaves.native)), 'efield.nii.gz');
    if ~isfile(dependencyEfield)
        blocked(end + 1, 1) = dependencies(dependencyIndex); %#ok<AGROW>
    end
end
end

function resolution = make_resolution(status, task, copiedCount, ...
        missingCount, blockedDependencies)
resolution = struct( ...
    'status', status, ...
    'task', task, ...
    'copied_artifact_count', copiedCount, ...
    'missing_artifact_count', missingCount, ...
    'blocked_dependency_ids', {cellstr(blockedDependencies)});
end
