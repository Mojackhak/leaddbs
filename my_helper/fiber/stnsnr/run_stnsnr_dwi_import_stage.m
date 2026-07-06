% Re-import STN/SNr DWI four-file sets and stage Lead-DBS DWI derivatives.

repoDir = '/Users/mojackhu/Github/leaddbs';
studyRoot = '/Volumes/VAL/STNSNr';
sourceRoot = '/Volumes/VAL/STNSNrdwi';
timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));

cd(repoDir);
addpath(genpath(repoDir));

subjects = { ...
    'ChenLingHua', ...
    'ChenMeiJu', ...
    'FanDongDong', ...
    'GengHui', ...
    'HuFengXian', ...
    'HuangDan', ...
    'LiPing', ...
    'LinJia', ...
    'MaoXiaoMing', ...
    'ShengGuoLiang', ...
    'WuYueFen', ...
    'YuDongJian', ...
    'ZhangMing', ...
    'ZhangXiaoHong', ...
    'ZhaoPeiGen', ...
    'ZhengXiangQuan'};

importLogDir = fullfile(studyRoot, 'derivatives', 'leaddbs', 'import_logs');
mh_util_make_dir(importLogDir);
importLog = fullfile(importLogDir, ['dwi_import_', timestamp, '.csv']);

rows = {};
sourceInfo = struct();

for i = 1:numel(subjects)
    subjectId = subjects{i};
    patientName = ['sub-', subjectId];
    sourceDir = fullfile(sourceRoot, patientName);
    targetDir = fullfile(studyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
    targetBase = [patientName, '_ses-preop_dwi'];

    [sourceBase, sourcePaths] = resolve_source_set(sourceDir);
    validate_dwi_set(sourcePaths.nii, sourcePaths.bval, sourcePaths.bvec, sourcePaths.json);
    rows = append_log(rows, 'source_validation', subjectId, patientName, 'valid', ...
        sourceBase, '', sourceDir, '', '', '', 'Source DWI set passed validation');

    mh_util_make_dir(targetDir);
    targetPaths = target_dwi_paths(targetDir, targetBase);
    [rows, sourceInfo.(subjectId)] = copy_source_set(rows, subjectId, patientName, sourceBase, sourcePaths, targetPaths);

    validate_dwi_set(targetPaths.nii, targetPaths.bval, targetPaths.bvec, targetPaths.json);
    rows = append_log(rows, 'raw_validation', subjectId, patientName, 'valid', ...
        sourceBase, '', targetDir, '', '', '', 'Raw BIDS DWI set passed validation');

    clear_existing_staged_dwi(studyRoot, patientName, targetBase);
end

write_import_log(importLog, rows);

result = mh_fiber_register_imported_dwi_batch( ...
    'StudyRoot', studyRoot, ...
    'RepoDir', repoDir, ...
    'ImportLog', importLog, ...
    'SubjectIds', subjects, ...
    'AnchorModality', 'T2w', ...
    'CoregistrationTag', 'dwi_stage', ...
    'AllowT1Fallback', false, ...
    'RunCoregistration', false, ...
    'GenerateOptionalDwiQc', false, ...
    'Force', true);

summary = result.summary;
if height(summary) ~= numel(subjects)
    error('Expected %d staged subjects, but status table contains %d rows.', numel(subjects), height(summary));
end
if ~all(strcmp(string(summary.status), "staged"))
    disp(summary(:, {'subject', 'status', 'message'}));
    error('Not all subjects reached staged status.');
end

for i = 1:numel(subjects)
    subjectId = subjects{i};
    patientName = ['sub-', subjectId];
    targetBase = [patientName, '_ses-preop_dwi'];
    stagedDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, 'preprocessing', 'dwi');
    stagedPaths = staged_dwi_paths(stagedDir, targetBase);
    validate_dwi_set(stagedPaths.nii, stagedPaths.bval, stagedPaths.bvec, stagedPaths.json);
    validate_b0_geometry(stagedPaths.nii, stagedPaths.b0);
end

fprintf('\nFinished STN/SNr DWI re-import and staging.\n');
fprintf('Import log: %s\n', importLog);
fprintf('Stage status CSV: %s\n', result.statusCsv);

function [sourceBase, paths] = resolve_source_set(sourceDir)
if ~isfolder(sourceDir)
    error('Source DWI directory does not exist: %s', sourceDir);
end

niiFiles = dir(fullfile(sourceDir, '*.nii.gz'));
niiFiles = niiFiles(~startsWith({niiFiles.name}, '._'));
niiFiles = niiFiles(~endsWith({niiFiles.name}, '_ADC.nii.gz'));
if numel(niiFiles) ~= 1
    error('Expected exactly one DWI NIfTI in %s, found %d.', sourceDir, numel(niiFiles));
end

sourceBase = erase(niiFiles(1).name, '.nii.gz');
paths = struct();
paths.nii = fullfile(sourceDir, [sourceBase, '.nii.gz']);
paths.json = fullfile(sourceDir, [sourceBase, '.json']);
paths.bval = fullfile(sourceDir, [sourceBase, '.bval']);
paths.bvec = fullfile(sourceDir, [sourceBase, '.bvec']);
end

function paths = target_dwi_paths(targetDir, targetBase)
paths = struct();
paths.nii = fullfile(targetDir, [targetBase, '.nii.gz']);
paths.json = fullfile(targetDir, [targetBase, '.json']);
paths.bval = fullfile(targetDir, [targetBase, '.bval']);
paths.bvec = fullfile(targetDir, [targetBase, '.bvec']);
end

function paths = staged_dwi_paths(stagedDir, targetBase)
paths = struct();
paths.nii = fullfile(stagedDir, [targetBase, '.nii']);
paths.json = fullfile(stagedDir, [targetBase, '.json']);
paths.bval = fullfile(stagedDir, [targetBase, '.bval']);
paths.bvec = fullfile(stagedDir, [targetBase, '.bvec']);
paths.b0 = fullfile(stagedDir, [targetBase, '_b0.nii']);
end

function validate_dwi_set(niiPath, bvalPath, bvecPath, jsonPath)
mh_util_must_be_file(niiPath, 'DWI NIfTI');
mh_util_must_be_file(jsonPath, 'DWI JSON');
mh_util_must_be_file(bvalPath, 'DWI bval');
mh_util_must_be_file(bvecPath, 'DWI bvec');

info = niftiinfo(niiPath);
imageSize = double(info.ImageSize);
if numel(imageSize) ~= 4
    error('DWI NIfTI is not 4D: %s', niiPath);
end

bvals = mh_fiber_load_bval(bvalPath);
bvecCount = mh_fiber_bvec_count(bvecPath);
if numel(bvals) ~= imageSize(4)
    error('bval count (%d) does not match DWI volume count (%d): %s', ...
        numel(bvals), imageSize(4), bvalPath);
end
if bvecCount ~= imageSize(4)
    error('bvec count (%d) does not match DWI volume count (%d): %s', ...
        bvecCount, imageSize(4), bvecPath);
end
if ~any(bvals < 10)
    error('No b0 volume found with bval < 10: %s', bvalPath);
end
end

function [rows, copied] = copy_source_set(rows, subjectId, patientName, sourceBase, sourcePaths, targetPaths)
extensions = {'.nii.gz', '.json', '.bval', '.bvec'};
sourceFiles = {sourcePaths.nii, sourcePaths.json, sourcePaths.bval, sourcePaths.bvec};
targetFiles = {targetPaths.nii, targetPaths.json, targetPaths.bval, targetPaths.bvec};
copied = struct();

for i = 1:numel(extensions)
    source = sourceFiles{i};
    target = targetFiles{i};
    copyfile(source, target, 'f');
    sourceHash = file_sha256(source);
    targetHash = file_sha256(target);
    if ~strcmp(sourceHash, targetHash)
        error('Checksum mismatch after copy: %s -> %s', source, target);
    end
    rows = append_log(rows, 'copy_result', subjectId, patientName, 'copied', ...
        sourceBase, extensions{i}, source, target, sourceHash, targetHash, 'Copied and checksum-verified');
    copied.(extension_field(extensions{i})) = target;
end
end

function clear_existing_staged_dwi(studyRoot, patientName, targetBase)
stagedDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, 'preprocessing', 'dwi');
if ~isfolder(stagedDir)
    return;
end

patterns = { ...
    [targetBase, '.nii'], ...
    [targetBase, '.json'], ...
    [targetBase, '.bval'], ...
    [targetBase, '.bvec'], ...
    [targetBase, '_b0.nii'], ...
    [targetBase, '_fa.nii'], ...
    [targetBase, '_tensor.mif'], ...
    'brainmask.nii', ...
    'trackingmask.nii'};

for i = 1:numel(patterns)
    path = fullfile(stagedDir, patterns{i});
    if isfile(path)
        delete(path);
    end
end
end

function validate_b0_geometry(dwiPath, b0Path)
mh_util_must_be_file(b0Path, 'staged DWI b0');
Vd = spm_vol(dwiPath);
Vb = spm_vol(b0Path);
if ~isequal(Vd(1).dim, Vb.dim)
    error('b0 dimensions do not match staged DWI spatial dimensions: %s', b0Path);
end
if max(abs(Vd(1).mat(:) - Vb.mat(:))) > 1e-5
    error('b0 affine/header does not match the staged DWI first frame: %s', b0Path);
end
end

function rows = append_log(rows, phase, subjectId, patientName, status, sourceBase, extension, sourcePath, targetPath, sourceHash, targetHash, message)
rows(end + 1, :) = {phase, subjectId, patientName, status, sourceBase, extension, sourcePath, targetPath, sourceHash, targetHash, message};
end

function write_import_log(path, rows)
T = cell2table(rows, 'VariableNames', { ...
    'phase', ...
    'subject', ...
    'patient', ...
    'status', ...
    'source_base', ...
    'extension', ...
    'source_path', ...
    'target_path', ...
    'source_sha256', ...
    'target_sha256', ...
    'message'});
writetable(T, path);
end

function hash = file_sha256(path)
cmd = sprintf('shasum -a 256 %s', mh_fiber_shell_quote(path));
[status, out] = system(cmd);
if status ~= 0
    error('Failed to compute SHA-256 for %s: %s', path, out);
end
tokens = regexp(strtrim(out), '^([0-9a-fA-F]+)', 'tokens', 'once');
if isempty(tokens)
    error('Could not parse SHA-256 output for %s: %s', path, out);
end
hash = lower(tokens{1});
end

function field = extension_field(extension)
field = matlab.lang.makeValidName(strrep(extension, '.', '_'));
end
