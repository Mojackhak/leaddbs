function logTable = run_stnsnr_apply_dwi_orientation_correction(varargin)
% Apply the confirmed STNSNr DWI image-content orientation correction.

p = inputParser;
p.FunctionName = 'run_stnsnr_apply_dwi_orientation_correction';
p.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('SourceRoot', '/Volumes/VAL/STNSNrdwi', @(x) ischar(x) || isstring(x));
p.addParameter('StudyRoot', '/Volumes/VAL/STNSNr', @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('Transform', 'rotX180', @(x) ischar(x) || isstring(x));
p.addParameter('AllowIncrementalCorrection', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('LogRoot', '', @(x) ischar(x) || isstring(x));
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = normalize_options(p.Results);

repoDir = resolve_repo_dir(opts.RepoDir);
addpath(genpath(repoDir));

timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
if isempty(opts.LogRoot)
    opts.LogRoot = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs', ...
        'import_logs', ['dwi_orientation_correction_', timestamp]);
end
trashRoot = fullfile(getenv('HOME'), '.Trash', ['stnsnr_dwi_orientation_', timestamp]);
stagingRoot = fullfile(opts.LogRoot, 'staging');
mh_util_make_dir(opts.LogRoot);
mh_util_make_dir(stagingRoot);
mh_util_make_dir(trashRoot);

items = build_target_items(opts);
rows = repmat(empty_log_row(), 0, 1);

fprintf('Staging %d orientation-correction targets.\n', numel(items));
for i = 1:numel(items)
    [items(i), newRows] = stage_item(items(i), stagingRoot, opts.Transform, ...
        opts.AllowIncrementalCorrection, opts.Force);
    rows = [rows, newRows]; %#ok<AGROW>
end

fprintf('Replacing staged targets and invalidating stale derivatives.\n');
for i = 1:numel(items)
    newRows = replace_item(items(i), trashRoot, opts.Transform);
    rows = [rows, newRows]; %#ok<AGROW>
end

staleTargets = build_stale_targets(opts);
for i = 1:numel(staleTargets)
    newRows = move_stale_target(staleTargets(i), trashRoot, opts.Transform);
    rows = [rows, newRows]; %#ok<AGROW>
end

logTable = struct2table(rows, 'AsArray', true);
logPath = fullfile(opts.LogRoot, 'dwi_orientation_correction_log.csv');
writetable(logTable, logPath);
write_run_manifest(opts, logPath, trashRoot, stagingRoot);
fprintf('Wrote orientation-correction log: %s\n', logPath);
end

function opts = normalize_options(opts)
opts.RepoDir = char(string(opts.RepoDir));
opts.SourceRoot = char(string(opts.SourceRoot));
opts.StudyRoot = char(string(opts.StudyRoot));
opts.LogRoot = char(string(opts.LogRoot));
opts.SubjectIds = to_cellstr(opts.SubjectIds);
if isempty(opts.SubjectIds)
    error('run_stnsnr_apply_dwi_orientation_correction:MissingSubjectIds', ...
        'SubjectIds must be provided by the project caller.');
end
opts.Transform = validatestring(char(string(opts.Transform)), ...
    {'identity', 'flipY', 'flipZ', 'rotX180'}, ...
    'run_stnsnr_apply_dwi_orientation_correction', 'Transform');
opts.AllowIncrementalCorrection = logical(opts.AllowIncrementalCorrection);
opts.Force = logical(opts.Force);
if strcmp(opts.Transform, 'identity')
    error('run_stnsnr_apply_dwi_orientation_correction:IdentityTransform', ...
        'Formal correction with identity would only rewrite files. Choose a non-identity transform.');
end
end

function values = to_cellstr(value)
if iscell(value)
    values = cellfun(@(x) char(string(x)), value, 'UniformOutput', false);
elseif isstring(value)
    values = cellstr(value(:));
else
    values = {char(string(value))};
end
values = values(~cellfun(@isempty, values));
end

function repoDir = resolve_repo_dir(repoDir)
repoDir = char(string(repoDir));
if ~isempty(repoDir)
    return;
end
current = fileparts(mfilename('fullpath'));
while ~isempty(current)
    if isfile(fullfile(current, 'ea_normalize.m'))
        repoDir = current;
        return;
    end
    parent = fileparts(current);
    if strcmp(parent, current)
        break;
    end
    current = parent;
end
error('run_stnsnr_apply_dwi_orientation_correction:RepoRootNotFound', ...
    'Could not resolve Lead-DBS repository root. Provide RepoDir explicitly.');
end

function items = build_target_items(opts)
items = repmat(empty_item(), 0, 1);
for subjectIndex = 1:numel(opts.SubjectIds)
    subjectId = opts.SubjectIds{subjectIndex};
    source = locate_source_dwi(opts.SourceRoot, subjectId);
    items(end + 1) = dwi_item(subjectId, 'stnsnrdwi', 'source_dwi', ...
        source.Nifti, source.Json, source.Bval, source.Bvec, ...
        opts.AllowIncrementalCorrection); %#ok<AGROW>

    rawDir = fullfile(opts.StudyRoot, 'rawdata', ['sub-', subjectId], 'ses-preop', 'dwi');
    rawBase = ['sub-', subjectId, '_ses-preop_dwi'];
    items(end + 1) = dwi_item(subjectId, 'rawdata', 'bids_dwi', ...
        fullfile(rawDir, [rawBase, '.nii.gz']), ...
        fullfile(rawDir, [rawBase, '.json']), ...
        fullfile(rawDir, [rawBase, '.bval']), ...
        fullfile(rawDir, [rawBase, '.bvec']), ...
        opts.AllowIncrementalCorrection); %#ok<AGROW>

    preprocDir = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs', ...
        ['sub-', subjectId], 'preprocessing', 'dwi');
    preBase = ['sub-', subjectId, '_ses-preop_dwi'];
    items(end + 1) = dwi_item(subjectId, 'preprocessing', 'staged_dwi', ...
        fullfile(preprocDir, [preBase, '.nii']), ...
        fullfile(preprocDir, [preBase, '.json']), ...
        fullfile(preprocDir, [preBase, '.bval']), ...
        fullfile(preprocDir, [preBase, '.bvec']), ...
        opts.AllowIncrementalCorrection); %#ok<AGROW>

    correctedBase = ['sub-', subjectId, '_ses-preop_desc-preproc_dwi'];
    items(end + 1) = dwi_item(subjectId, 'preprocessing', 'corrected_dwi', ...
        fullfile(preprocDir, [correctedBase, '.nii']), '', ...
        fullfile(preprocDir, [correctedBase, '.bval']), ...
        fullfile(preprocDir, [correctedBase, '.bvec']), ...
        opts.AllowIncrementalCorrection); %#ok<AGROW>

    scalarItems = scalar_preproc_items(subjectId, preprocDir);
    items = [items, scalarItems]; %#ok<AGROW>
end
end

function source = locate_source_dwi(sourceRoot, subjectId)
subjectDir = fullfile(sourceRoot, ['sub-', subjectId]);
files = [dir(fullfile(subjectDir, '*.nii.gz')); dir(fullfile(subjectDir, '*.nii'))];
files = files(~startsWith({files.name}, '._'));
if numel(files) ~= 1
    error('run_stnsnr_apply_dwi_orientation_correction:AmbiguousSourceDwi', ...
        'Expected exactly one source DWI NIfTI in %s, found %d.', subjectDir, numel(files));
end
source = struct();
source.Nifti = fullfile(files(1).folder, files(1).name);
source.Base = mh_fiber_nii_basename(source.Nifti);
source.Json = fullfile(subjectDir, [source.Base, '.json']);
source.Bval = fullfile(subjectDir, [source.Base, '.bval']);
source.Bvec = fullfile(subjectDir, [source.Base, '.bvec']);
end

function item = dwi_item(subjectId, layer, role, niftiPath, jsonPath, bvalPath, bvecPath, allowIncrementalCorrection)
item = empty_item();
item.subject = subjectId;
item.layer = layer;
item.role = role;
item.kind = 'dwi';
item.nifti = niftiPath;
item.json = jsonPath;
item.bval = bvalPath;
item.bvec = bvecPath;
item.outputBase = mh_fiber_nii_basename(niftiPath);
required = {niftiPath, bvalPath, bvecPath};
if ~isempty(jsonPath)
    required{end + 1} = jsonPath;
end
for i = 1:numel(required)
    mh_util_must_be_file(required{i}, ['DWI ', role], ...
        'run_stnsnr_apply_dwi_orientation_correction:MissingDwiFile');
end
assert_json_not_already_corrected(jsonPath, [subjectId, ' ', layer, ' ', role], ...
    allowIncrementalCorrection);
end

function items = scalar_preproc_items(subjectId, preprocDir)
items = repmat(empty_item(), 0, 1);
patterns = {
    'brainmask.nii', 'brainmask'
    'trackingmask.nii', 'trackingmask'
    ['sub-', subjectId, '_ses-preop_dwi_b0.nii'], 'distorted_b0'
    ['sub-', subjectId, '_ses-preop_dwi_fa.nii'], 'fa'
    ['sub-', subjectId, '_ses-preop_desc-preproc_b0.nii'], 'corrected_b0'
    ['sub-', subjectId, '_ses-preop_desc-preproc_dwi_b0.nii'], 'corrected_dwi_b0'
    };
for i = 1:size(patterns, 1)
    niftiPath = fullfile(preprocDir, patterns{i, 1});
    if ~isfile(niftiPath)
        continue;
    end
    item = empty_item();
    item.subject = subjectId;
    item.layer = 'preprocessing';
    item.role = patterns{i, 2};
    item.kind = 'scalar';
    item.nifti = niftiPath;
    item.json = matching_json_path(niftiPath);
    item.outputBase = mh_fiber_nii_basename(niftiPath);
    items(end + 1) = item; %#ok<AGROW>
end
end

function [item, rows] = stage_item(item, stagingRoot, transformName, allowIncrementalCorrection, force)
rows = repmat(empty_log_row(), 0, 1);
stageDir = fullfile(stagingRoot, ['sub-', item.subject], item.layer, item.role);
mh_util_make_dir(stageDir);
item.stageDir = stageDir;
try
    switch item.kind
        case 'dwi'
            result = mh_fiber_reorient_dwi_image_content( ...
                'SourceNifti', item.nifti, ...
                'SourceJson', item.json, ...
                'SourceBval', item.bval, ...
                'SourceBvec', item.bvec, ...
                'OutputDir', stageDir, ...
                'OutputBase', item.outputBase, ...
                'Transform', transformName, ...
                'AllowIncrementalCorrection', allowIncrementalCorrection, ...
                'Force', force);
            item.stageNifti = result.Nifti;
            item.stageJson = result.Json;
            item.stageBval = result.Bval;
            item.stageBvec = result.Bvec;
        case 'scalar'
            item.stageNifti = fullfile(stageDir, file_name(item.nifti));
            mh_fiber_reorient_nifti_content( ...
                'SourceNifti', item.nifti, ...
                'OutputNifti', item.stageNifti, ...
                'Transform', transformName, ...
                'Force', force);
            if ~isempty(item.json) && isfile(item.json)
                item.stageJson = fullfile(stageDir, file_name(item.json));
                copyfile(item.json, item.stageJson, 'f');
                augment_scalar_json(item.stageJson, item, transformName, allowIncrementalCorrection);
            end
        otherwise
            error('run_stnsnr_apply_dwi_orientation_correction:UnknownItemKind', ...
                'Unsupported item kind: %s', item.kind);
    end
    rows(end + 1) = make_log_row(item, 'stage', '', transformName, 'ok', 'ok');
catch ME
    error('run_stnsnr_apply_dwi_orientation_correction:StageFailed', ...
        'Staging failed for %s %s %s: %s', item.subject, item.layer, item.role, ME.message);
end
end

function rows = replace_item(item, trashRoot, transformName)
rows = repmat(empty_log_row(), 0, 1);
switch item.kind
    case 'dwi'
        rows = [rows, replace_file(item, 'nifti', item.nifti, item.stageNifti, trashRoot, transformName)];
        rows = [rows, replace_file(item, 'json', item.json, item.stageJson, trashRoot, transformName)];
        rows = [rows, replace_file(item, 'bval', item.bval, item.stageBval, trashRoot, transformName)];
        rows = [rows, replace_file(item, 'bvec', item.bvec, item.stageBvec, trashRoot, transformName)];
    case 'scalar'
        rows = [rows, replace_file(item, 'nifti', item.nifti, item.stageNifti, trashRoot, transformName)];
        if ~isempty(item.json) && ~isempty(item.stageJson)
            rows = [rows, replace_file(item, 'json', item.json, item.stageJson, trashRoot, transformName)];
        end
end
end

function row = replace_file(item, fileRole, targetPath, stagePath, trashRoot, transformName)
row = make_log_row(item, ['replace_', fileRole], targetPath, transformName, 'started', '');
if isempty(targetPath) || isempty(stagePath)
    row.status = 'skipped_empty_path';
    return;
end
if ~isfile(stagePath)
    error('run_stnsnr_apply_dwi_orientation_correction:MissingStagedFile', ...
        'Staged file is missing: %s', stagePath);
end
row.old_sha256 = file_hash_or_empty(targetPath);
row.staging_path = stagePath;
row.staging_sha256 = mh_fiber_file_sha256(stagePath);
row.trash_path = move_existing_to_trash(targetPath, trashRoot);
move_appledouble_to_trash(targetPath, trashRoot);
mh_util_make_dir(fileparts(targetPath));
copyfile(stagePath, targetPath, 'f');
row.final_sha256 = mh_fiber_file_sha256(targetPath);
if ~strcmp(row.staging_sha256, row.final_sha256)
    error('run_stnsnr_apply_dwi_orientation_correction:CopyHashMismatch', ...
        'Staged and final SHA differ for %s.', targetPath);
end
row.status = 'ok';
row.message = 'ok';
end

function rows = build_stale_targets(opts)
rows = repmat(empty_stale_target(), 0, 1);
for subjectIndex = 1:numel(opts.SubjectIds)
    subjectId = opts.SubjectIds{subjectIndex};
    preprocDir = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs', ...
        ['sub-', subjectId], 'preprocessing', 'dwi');
    mifFiles = dir(fullfile(preprocDir, '*.mif'));
    for i = 1:numel(mifFiles)
        if startsWith(mifFiles(i).name, '._')
            continue;
        end
        rows(end + 1) = stale_target(subjectId, 'preprocessing', 'stale_tensor_mif', ...
            fullfile(mifFiles(i).folder, mifFiles(i).name)); %#ok<AGROW>
    end

    coregDir = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs', ...
        ['sub-', subjectId], 'coregistration', 'anat');
    coregFiles = dir(fullfile(coregDir, '*B0*'));
    for i = 1:numel(coregFiles)
        if coregFiles(i).isdir || startsWith(coregFiles(i).name, '._')
            continue;
        end
        rows(end + 1) = stale_target(subjectId, 'coregistration', 'invalidated_coreg_b0', ...
            fullfile(coregFiles(i).folder, coregFiles(i).name)); %#ok<AGROW>
    end
end
end

function rows = move_stale_target(target, trashRoot, transformName)
rows = repmat(empty_log_row(), 0, 1);
item = empty_item();
item.subject = target.subject;
item.layer = target.layer;
item.role = target.role;
item.kind = 'stale';
item.nifti = target.path;
if ~isfile(target.path)
    return;
end
row = make_log_row(item, 'move_to_trash', target.path, transformName, 'started', '');
row.old_sha256 = mh_fiber_file_sha256(target.path);
row.trash_path = move_existing_to_trash(target.path, trashRoot);
move_appledouble_to_trash(target.path, trashRoot);
row.status = 'ok';
row.message = 'moved stale derivative to Trash';
rows(end + 1) = row;
end

function trashPath = move_existing_to_trash(path, trashRoot)
trashPath = '';
if isempty(path) || ~isfile(path)
    return;
end
trashPath = unique_trash_path(path, trashRoot);
mh_util_make_dir(fileparts(trashPath));
movefile(path, trashPath, 'f');
end

function move_appledouble_to_trash(path, trashRoot)
[folder, name, ext] = fileparts(path);
appleDouble = fullfile(folder, ['._', name, ext]);
if isfile(appleDouble)
    move_existing_to_trash(appleDouble, trashRoot);
end
end

function trashPath = unique_trash_path(path, trashRoot)
relative = regexprep(path, '^/', '');
trashPath = fullfile(trashRoot, relative);
[folder, name, ext] = fileparts(trashPath);
counter = 1;
candidate = trashPath;
while isfile(candidate)
    candidate = fullfile(folder, sprintf('%s_%03d%s', name, counter, ext));
    counter = counter + 1;
end
trashPath = candidate;
end

function augment_scalar_json(jsonPath, item, transformName, allowIncrementalCorrection)
metadata = jsondecode(fileread(jsonPath));
if is_already_corrected(metadata) && ~allowIncrementalCorrection
    error('run_stnsnr_apply_dwi_orientation_correction:AlreadyCorrected', ...
        'Source JSON already records an image-content orientation correction: %s', jsonPath);
end
correctionContext = mh_fiber_orientation_correction_context(metadata, transformName);
metadata.ImageContentOrientationCorrection = true;
metadata.OrientationCorrectionTransform = correctionContext.NetTransform;
metadata.OrientationCorrectionBvecMatrix = correctionContext.NetMatrix;
metadata.OrientationCorrectionLatestTransform = correctionContext.IncrementalTransform;
metadata.OrientationCorrectionLatestBvecMatrix = correctionContext.IncrementalMatrix;
metadata.OrientationCorrectionChainText = chain_text(correctionContext);
if correctionContext.HasPrevious
    metadata.OrientationCorrectionPreviousTransform = correctionContext.PreviousTransform;
    metadata.OrientationCorrectionPreviousBvecMatrix = correctionContext.PreviousMatrix;
    metadata.OrientationCorrectionIncrementalTransform = correctionContext.IncrementalTransform;
    metadata.OrientationCorrectionIncrementalBvecMatrix = correctionContext.IncrementalMatrix;
end
metadata.OrientationCorrectionNetTransform = correctionContext.NetTransform;
metadata.OrientationCorrectionNetBvecMatrix = correctionContext.NetMatrix;
metadata.OrientationCorrectionSourceNifti = item.nifti;
metadata.OrientationCorrectionSourceJson = item.json;
metadata.OrientationCorrectionSourceSha256 = struct( ...
    'Nifti', mh_fiber_file_sha256(item.nifti), ...
    'Json', mh_fiber_file_sha256(item.json));
metadata.OrientationCorrectionDateTime = char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss'));
fid = fopen(jsonPath, 'w');
if fid < 0
    error('run_stnsnr_apply_dwi_orientation_correction:JsonWriteFailed', ...
        'Could not write JSON: %s', jsonPath);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(metadata, 'PrettyPrint', true));
clear cleanupObj;
end

function text = chain_text(correctionContext)
if correctionContext.HasPrevious
    text = sprintf('%s -> %s => %s', correctionContext.PreviousTransform, ...
        correctionContext.IncrementalTransform, correctionContext.NetTransform);
else
    text = correctionContext.NetTransform;
end
end

function corrected = is_already_corrected(metadata)
corrected = isfield(metadata, 'ImageContentOrientationCorrection') && ...
    logical(metadata.ImageContentOrientationCorrection);
end

function jsonPath = matching_json_path(niftiPath)
jsonPath = [regexprep(niftiPath, '\.nii(\.gz)?$', ''), '.json'];
if ~isfile(jsonPath)
    jsonPath = '';
end
end

function assert_json_not_already_corrected(jsonPath, label, allowIncrementalCorrection)
if isempty(jsonPath) || ~isfile(jsonPath)
    return;
end
try
    metadata = jsondecode(fileread(jsonPath));
catch
    return;
end
if is_already_corrected(metadata) && ~allowIncrementalCorrection
    error('run_stnsnr_apply_dwi_orientation_correction:AlreadyCorrected', ...
        'Refusing to apply a second orientation correction to %s: %s', label, jsonPath);
end
end

function write_run_manifest(opts, logPath, trashRoot, stagingRoot)
manifest = struct();
manifest.SubjectIds = opts.SubjectIds;
manifest.Transform = opts.Transform;
manifest.AllowIncrementalCorrection = opts.AllowIncrementalCorrection;
manifest.SourceRoot = opts.SourceRoot;
manifest.StudyRoot = opts.StudyRoot;
manifest.LogPath = logPath;
manifest.TrashRoot = trashRoot;
manifest.StagingRoot = stagingRoot;
manifest.ReranSynb0TopupEddy = false;
manifest.DateTime = char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss'));
manifestPath = fullfile(opts.LogRoot, 'dwi_orientation_correction_manifest.json');
fid = fopen(manifestPath, 'w');
if fid < 0
    error('run_stnsnr_apply_dwi_orientation_correction:ManifestWriteFailed', ...
        'Could not write manifest: %s', manifestPath);
end
cleanupObj = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(manifest, 'PrettyPrint', true));
clear cleanupObj;
end

function hash = file_hash_or_empty(path)
if isempty(path) || ~isfile(path)
    hash = '';
else
    hash = mh_fiber_file_sha256(path);
end
end

function name = file_name(path)
[~, base, ext] = fileparts(path);
if strcmp(ext, '.gz')
    [~, innerBase, innerExt] = fileparts(base);
    name = [innerBase, innerExt, ext];
else
    name = [base, ext];
end
end

function row = make_log_row(item, action, targetPath, transformName, status, message)
row = empty_log_row();
row.subject = item.subject;
row.layer = item.layer;
row.role = item.role;
row.kind = item.kind;
row.action = action;
row.transform = transformName;
row.target_path = targetPath;
row.staging_path = '';
row.trash_path = '';
row.status = status;
row.message = mh_fiber_compact_message(message);
end

function item = empty_item()
item = struct();
item.subject = '';
item.layer = '';
item.role = '';
item.kind = '';
item.nifti = '';
item.json = '';
item.bval = '';
item.bvec = '';
item.outputBase = '';
item.stageDir = '';
item.stageNifti = '';
item.stageJson = '';
item.stageBval = '';
item.stageBvec = '';
end

function target = stale_target(subjectId, layer, role, path)
target = empty_stale_target();
target.subject = subjectId;
target.layer = layer;
target.role = role;
target.path = path;
end

function target = empty_stale_target()
target = struct();
target.subject = '';
target.layer = '';
target.role = '';
target.path = '';
end

function row = empty_log_row()
row = struct();
row.subject = '';
row.layer = '';
row.role = '';
row.kind = '';
row.action = '';
row.transform = '';
row.target_path = '';
row.staging_path = '';
row.trash_path = '';
row.old_sha256 = '';
row.staging_sha256 = '';
row.final_sha256 = '';
row.status = '';
row.message = '';
end
