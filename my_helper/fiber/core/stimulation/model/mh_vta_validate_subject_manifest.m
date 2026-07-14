function manifest = mh_vta_validate_subject_manifest(manifest)
% Validate and normalize one vta_subject_manifest_v1 execution envelope.

if ~isstruct(manifest) || ~isscalar(manifest)
    invalid_manifest('Subject manifest must be a scalar struct.');
end
require_fields(manifest, ...
    {'schema_version', 'run_id', 'subject_id', 'tasks', 'reuse_donors'}, ...
    'manifest');
require_nonempty_text(manifest.schema_version, 'schema_version');
if string(manifest.schema_version) ~= "vta_subject_manifest_v1"
    invalid_manifest('Unsupported subject manifest schema_version.');
end
require_nonempty_text(manifest.run_id, 'run_id');
require_nonempty_text(manifest.subject_id, 'subject_id');
if ~isstruct(manifest.tasks) || isempty(manifest.tasks)
    invalid_manifest('tasks must be a nonempty struct array.');
end
if ~isstruct(manifest.reuse_donors) || isempty(manifest.reuse_donors)
    invalid_manifest('reuse_donors must be a nonempty struct array.');
end

taskIds = strings(numel(manifest.tasks), 1);
selectedLeaves = strings(0, 1);
headmodelPaths = strings(0, 1);
headmodelContexts = cell(0, 1);
for taskIndex = 1:numel(manifest.tasks)
    entry = manifest.tasks(taskIndex);
    require_fields(entry, {'task', 'output_leaves', 'reuse_candidate_ids'}, ...
        sprintf('tasks(%d)', taskIndex));
    if ~isstruct(entry.task) || ~isscalar(entry.task)
        invalid_manifest('tasks(%d).task must be a scalar struct.', taskIndex);
    end
    if any(isfield(entry.task, ...
            {'run_id', 'output_leaves', 'missing_artifacts'}))
        invalid_manifest('Manifest task definitions must not embed runtime fields.');
    end
    try
        task = mh_vta_validate_canonical_task_definition(entry.task);
    catch validationError
        invalid_manifest('Task definition at index %d is invalid: %s', ...
            taskIndex, validationError.message);
    end
    if string(task.subject_id) ~= string(manifest.subject_id)
        invalid_manifest('Task %s belongs to a different subject.', task.task_id);
    end
    taskIds(taskIndex) = string(task.task_id);
    if nnz(taskIds(1:taskIndex) == taskIds(taskIndex)) ~= 1
        invalid_manifest('Duplicate selected task_id %s.', task.task_id);
    end
    dependencies = text_array(task.dependencies, 'dependencies');
    if any(~ismember(dependencies, taskIds(1:taskIndex - 1)))
        invalid_manifest('Task %s has an unknown or forward dependency.', ...
            task.task_id);
    end
    task.run_id = char(string(manifest.run_id));
    task.output_leaves = entry.output_leaves;
    task = validate_entry_output_leaves(task);
    manifest.tasks(taskIndex).task = task;
    manifest.tasks(taskIndex).reuse_candidate_ids = cellstr(text_array( ...
        entry.reuse_candidate_ids, 'reuse_candidate_ids'));
    spaces = cellstr(string(task.model.spaces));
    for spaceIndex = 1:numel(spaces)
        selectedLeaves(end + 1, 1) = canonical_path( ...
            task.output_leaves.(spaces{spaceIndex})); %#ok<AGROW>
    end
    [headmodelPath, context] = headmodel_identity(task);
    existing = find(headmodelPaths == headmodelPath, 1);
    if isempty(existing)
        headmodelPaths(end + 1, 1) = headmodelPath; %#ok<AGROW>
        headmodelContexts{end + 1, 1} = context; %#ok<AGROW>
    elseif ~isequal(headmodelContexts{existing}, context)
        invalid_manifest('Tasks sharing headmodel %s have conflicting inputs.', ...
            headmodelPath);
    end
end
validate_nonoverlapping_paths(selectedLeaves, 'selected writable leaves');

[donorIds, donorLeaves, manifest.reuse_donors] = validate_donors(manifest);
if any(~ismember(taskIds, donorIds))
    invalid_manifest('Every selected task must own one donor catalog entry.');
end
for taskIndex = 1:numel(manifest.tasks)
    taskId = taskIds(taskIndex);
    ownerIndex = find(donorIds == taskId, 1);
    spaces = cellstr(string(manifest.tasks(taskIndex).task.model.spaces));
    for spaceIndex = 1:numel(spaces)
        space = spaces{spaceIndex};
        expected = canonical_path( ...
            manifest.tasks(taskIndex).task.output_leaves.(space));
        if donorLeaves(ownerIndex).(space) ~= expected
            invalid_manifest('Selected donor %s does not match its owned leaf.', ...
                taskId);
        end
    end
    candidates = string(manifest.tasks(taskIndex).reuse_candidate_ids);
    candidates = candidates(:);
    if any(candidates == taskId) || ...
            numel(unique(candidates)) ~= numel(candidates) || ...
            any(~ismember(candidates, donorIds))
        invalid_manifest('Task %s has invalid reuse candidates.', taskId);
    end
end
end

function task = validate_entry_output_leaves(task)
if ~isstruct(task.output_leaves) || ~isscalar(task.output_leaves)
    invalid_manifest('output_leaves must be a scalar struct.');
end
spaces = cellstr(string(task.model.spaces));
for spaceIndex = 1:numel(spaces)
    space = spaces{spaceIndex};
    if ~isfield(task.output_leaves, space)
        invalid_manifest('output_leaves is missing space %s.', space);
    end
    expected = canonical_path(mh_vta_canonical_leaf_path(task, space));
    actual = canonical_path(task.output_leaves.(space));
    if actual ~= expected
        invalid_manifest('output_leaves.%s does not match canonical path.', space);
    end
    task.output_leaves.(space) = char(actual);
end
unknown = setdiff(fieldnames(task.output_leaves), spaces);
if ~isempty(unknown)
    invalid_manifest('output_leaves contains unsupported space %s.', unknown{1});
end
end

function [donorIds, donorLeaves, donors] = validate_donors(manifest)
donors = manifest.reuse_donors;
donorIds = strings(numel(manifest.reuse_donors), 1);
donorLeaves = repmat(struct(), numel(manifest.reuse_donors), 1);
subjectRoot = canonical_path(fullfile(char(string( ...
    manifest.tasks(1).task.subject_dir)), 'stimulations'));
spaces = cellstr(string(manifest.tasks(1).task.model.spaces));
for donorIndex = 1:numel(manifest.reuse_donors)
    donor = manifest.reuse_donors(donorIndex);
    require_fields(donor, {'donor_id', 'output_leaves'}, ...
        sprintf('reuse_donors(%d)', donorIndex));
    require_nonempty_text(donor.donor_id, 'donor_id');
    donorIds(donorIndex) = string(donor.donor_id);
    if nnz(donorIds(1:donorIndex) == donorIds(donorIndex)) ~= 1
        invalid_manifest('Duplicate donor_id %s.', donor.donor_id);
    end
    if ~isstruct(donor.output_leaves) || ~isscalar(donor.output_leaves)
        invalid_manifest('Donor output_leaves must be a scalar struct.');
    end
    for spaceIndex = 1:numel(spaces)
        space = spaces{spaceIndex};
        if ~isfield(donor.output_leaves, space)
            invalid_manifest('Donor %s is missing output space %s.', ...
                donor.donor_id, space);
        end
        path = canonical_path(donor.output_leaves.(space));
        if ~is_path_within(path, subjectRoot)
            invalid_manifest('Donor %s is outside the subject stimulation tree.', ...
                donor.donor_id);
        end
        donorLeaves(donorIndex).(space) = path;
        donors(donorIndex).output_leaves.(space) = char(path);
    end
    unknown = setdiff(fieldnames(donor.output_leaves), spaces);
    if ~isempty(unknown)
        invalid_manifest('Donor %s contains unsupported space %s.', ...
            donor.donor_id, unknown{1});
    end
end
end

function [path, context] = headmodel_identity(task)
sideIndex = 1 + double(strcmpi(char(string(task.hemisphere)), 'L'));
path = canonical_path(fullfile(char(string(task.subject_dir)), ...
    'headmodel', 'native', sprintf('sub-%s_desc-headmodel%d.mat', ...
    char(string(task.subject_id)), sideIndex)));
context = { ...
    canonical_path(task.subject_dir), ...
    canonical_path(task.reconstruction_path), ...
    upper(char(string(task.hemisphere))), ...
    double(task.reconstruction_lead_id), ...
    char(string(task.electrode_model)), ...
    char(string(task.model.atlas_set)), ...
    double(task.model.gray_matter_s_per_m), ...
    double(task.model.white_matter_s_per_m)};
end

function validate_nonoverlapping_paths(paths, label)
if numel(unique(paths)) ~= numel(paths)
    invalid_manifest('%s contain duplicate paths.', label);
end
for firstIndex = 1:numel(paths)
    for secondIndex = firstIndex + 1:numel(paths)
        if is_path_within(paths(firstIndex), paths(secondIndex)) || ...
                is_path_within(paths(secondIndex), paths(firstIndex))
            invalid_manifest('%s contain ancestor/descendant paths.', label);
        end
    end
end
end

function tf = is_path_within(path, root)
path = string(path);
root = string(root);
tf = path ~= root && startsWith(path, root + string(filesep));
end

function path = canonical_path(value)
require_nonempty_text(value, 'path');
file = javaObject('java.io.File', char(string(value)));
path = string(char(file.getCanonicalPath()));
end

function values = text_array(value, label)
if isempty(value)
    values = strings(0, 1);
    return;
end
if ~(ischar(value) || isstring(value) || iscellstr(value))
    invalid_manifest('%s must contain text values.', label);
end
values = string(value);
values = values(:);
if any(ismissing(values)) || any(strlength(values) == 0) || ...
        numel(unique(values)) ~= numel(values)
    invalid_manifest('%s must contain unique nonempty values.', label);
end
end

function require_fields(value, fields, label)
if ~isstruct(value)
    invalid_manifest('%s must be a struct.', label);
end
missing = fields(~isfield(value, fields));
if ~isempty(missing)
    invalid_manifest('%s is missing field %s.', label, missing{1});
end
end

function require_nonempty_text(value, label)
if ~(ischar(value) || isstring(value) && isscalar(value))
    invalid_manifest('%s must be text.', label);
end
text = string(value);
if ~isscalar(text) || ismissing(text) || strlength(text) == 0
    invalid_manifest('%s must be nonempty text.', label);
end
end

function invalid_manifest(message, varargin)
error('mh_vta:InvalidSubjectManifest', message, varargin{:});
end
