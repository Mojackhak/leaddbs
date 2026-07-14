function [missingArtifacts, count] = mh_vta_missing_task_artifacts(task)
% Recompute one task's missing canonical artifacts from path existence.

names = mh_vta_expected_artifact_names(task.model.thresholds_v_per_m);
spaces = cellstr(string(task.model.spaces));
missingArtifacts = struct();
count = 0;
for spaceIndex = 1:numel(spaces)
    space = spaces{spaceIndex};
    leaf = char(string(task.output_leaves.(space)));
    missing = strings(0, 1);
    for nameIndex = 1:numel(names)
        if ~isfile(fullfile(leaf, char(names(nameIndex))))
            missing(end + 1, 1) = names(nameIndex); %#ok<AGROW>
        end
    end
    if ~isempty(missing)
        missingArtifacts.(space) = cellstr(missing);
        count = count + numel(missing);
    end
end
end
