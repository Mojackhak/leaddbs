function task = mh_vta_validate_canonical_task_runtime(task)
% Validate canonical output leaves and a nonempty runtime missing set.

if ~isstruct(task) || ~isscalar(task)
    invalid_task('Canonical task must be a scalar struct.');
end
required = {'run_id', 'output_leaves', 'missing_artifacts', 'model'};
missing = required(~isfield(task, required));
if ~isempty(missing)
    invalid_task('Runtime task is missing required field %s.', missing{1});
end
require_nonempty_text(task.run_id, 'run_id');
validate_output_leaves(task);
validate_missing_artifacts(task);
end

function validate_output_leaves(task)
if ~isstruct(task.output_leaves) || ~isscalar(task.output_leaves)
    invalid_task('output_leaves must be a scalar struct.');
end
spaces = cellstr(string(task.model.spaces));
for spaceIndex = 1:numel(spaces)
    space = spaces{spaceIndex};
    if ~isfield(task.output_leaves, space)
        invalid_task('output_leaves is missing space %s.', space);
    end
    require_nonempty_text(task.output_leaves.(space), ...
        sprintf('output_leaves.%s', space));
    expected = canonical_path(mh_vta_canonical_leaf_path(task, space));
    actual = canonical_path(task.output_leaves.(space));
    if actual ~= expected
        invalid_task('output_leaves.%s does not match canonical path.', space);
    end
    task.output_leaves.(space) = char(actual);
end

function path = canonical_path(value)
require_nonempty_text(value, 'path');
file = javaObject('java.io.File', char(string(value)));
path = string(char(file.getCanonicalPath()));
end
unknown = setdiff(fieldnames(task.output_leaves), spaces);
if ~isempty(unknown)
    invalid_task('output_leaves contains unsupported space %s.', unknown{1});
end
end

function validate_missing_artifacts(task)
if ~isstruct(task.missing_artifacts) || ~isscalar(task.missing_artifacts)
    invalid_task('missing_artifacts must be a scalar struct.');
end
spaces = cellstr(string(task.model.spaces));
allowed = mh_vta_expected_artifact_names(task.model.thresholds_v_per_m);
requestedCount = 0;
for spaceIndex = 1:numel(spaces)
    space = spaces{spaceIndex};
    if ~isfield(task.missing_artifacts, space)
        continue;
    end
    names = string(task.missing_artifacts.(space));
    names = names(:);
    if isempty(names) || any(ismissing(names)) || any(strlength(names) == 0)
        invalid_task('missing_artifacts.%s must contain file names.', space);
    end
    if any(~ismember(names, allowed)) || numel(unique(names)) ~= numel(names)
        invalid_task('missing_artifacts.%s contains an invalid file name.', space);
    end
    requestedCount = requestedCount + numel(names);
end
unknown = setdiff(fieldnames(task.missing_artifacts), spaces);
if ~isempty(unknown)
    invalid_task('missing_artifacts contains unsupported space %s.', unknown{1});
end
if requestedCount == 0
    invalid_task('missing_artifacts must request at least one artifact.');
end
end

function require_nonempty_text(value, label)
if ~(ischar(value) || isstring(value) && isscalar(value))
    invalid_task('%s must be text.', label);
end
text = string(value);
if ~isscalar(text) || ismissing(text) || strlength(text) == 0
    invalid_task('%s must be nonempty text.', label);
end
end

function invalid_task(message, varargin)
error('mh_vta:InvalidCanonicalTask', message, varargin{:});
end
