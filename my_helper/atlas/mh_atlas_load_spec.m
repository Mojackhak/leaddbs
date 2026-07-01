function spec = mh_atlas_load_spec(specPath)
% Load and normalize a seed-target binary atlas JSON spec.

if nargin < 1 || strlength(string(specPath)) == 0
    error('mh_atlas_load_spec:MissingSpecPath', 'specPath is required.');
end

repoDir = resolve_repo_dir(mfilename('fullpath'));
specPath = resolve_path(specPath, repoDir);
if ~isfile(specPath)
    error('mh_atlas_load_spec:MissingSpec', 'Spec file does not exist: %s', specPath);
end

spec = jsondecode(fileread(specPath));
spec.spec_path = specPath;
spec.repo_dir = repoDir;

required = {'atlas_name', 'space', 'reference_image', 'output_dir', 'rois'};
for i = 1:numel(required)
    if ~isfield(spec, required{i})
        error('mh_atlas_load_spec:InvalidSpec', 'Missing top-level field: %s', required{i});
    end
end

spec.atlas_name = char(string(spec.atlas_name));
spec.space = char(string(spec.space));
spec.reference_image = resolve_path(spec.reference_image, repoDir);
spec.output_dir = resolve_path(spec.output_dir, repoDir);

if ~isfile(spec.reference_image)
    error('mh_atlas_load_spec:MissingReference', ...
        'Reference image does not exist: %s', spec.reference_image);
end

spec.rois = normalize_roi_array(spec.rois);

if ~isstruct(spec.rois) || isempty(spec.rois)
    error('mh_atlas_load_spec:InvalidRois', 'Spec must contain at least one ROI.');
end

for i = 1:numel(spec.rois)
    roi = spec.rois(i);
    roiRequired = {'name', 'role', 'operation', 'sides'};
    for j = 1:numel(roiRequired)
        if ~isfield(roi, roiRequired{j})
            error('mh_atlas_load_spec:InvalidRoi', ...
                'ROI %d is missing field: %s', i, roiRequired{j});
        end
    end
    if ~isfield(roi.sides, 'L') || ~isfield(roi.sides, 'R')
        error('mh_atlas_load_spec:InvalidSides', ...
            'ROI %s must define both L and R sides.', char(string(roi.name)));
    end
end
end

function rois = normalize_roi_array(rois)
if iscell(rois)
    if isempty(rois)
        rois = struct([]);
        return;
    end
    allFields = strings(0, 1);
    for i = 1:numel(rois)
        allFields = unique([allFields; string(fieldnames(rois{i}))]); %#ok<AGROW>
    end
    template = struct();
    for j = 1:numel(allFields)
        template.(char(allFields(j))) = [];
    end
    out = repmat(template, numel(rois), 1);
    for i = 1:numel(rois)
        names = fieldnames(rois{i});
        for j = 1:numel(names)
            out(i).(names{j}) = rois{i}.(names{j});
        end
    end
    rois = out;
elseif isstruct(rois)
    rois = rois(:);
end
end

function path = resolve_path(path, repoDir)
path = char(string(path));
if startsWith(path, filesep)
    return;
end
path = fullfile(repoDir, path);
end

function repoDir = resolve_repo_dir(startPath)
repoDir = fileparts(startPath);
while strlength(string(repoDir)) > 0
    if isfolder(fullfile(repoDir, 'templates')) && isfolder(fullfile(repoDir, 'my_helper'))
        return;
    end
    parentDir = fileparts(repoDir);
    if strcmp(parentDir, repoDir)
        break;
    end
    repoDir = parentDir;
end
error('mh_atlas_load_spec:RepoRootNotFound', ...
    'Cannot resolve Lead-DBS repo root from: %s', startPath);
end
