% Re-import STNSNr DWI rawdata and run Synb0/eddy fake-B0 preprocessing.

scriptPath = mfilename('fullpath');
repoDir = fileparts(fileparts(fileparts(fileparts(scriptPath))));
documentedRepoDir = '/Users/mojackhu/Github/leaddbs';
studyRoot = '/Volumes/VAL/STNSNr';
sourceRoot = '/Volumes/VAL/STNSNrdwi';
freeSurferLicense = '/Applications/freesurfer/8.2.0/license.txt';
synb0WorkRoot = fullfile(getenv('HOME'), 'Library', 'Caches', 'leaddbs', 'stnsnr_synb0_work');
timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));

cd(repoDir);
addpath(genpath(repoDir));

subjects = { ...
    'LinJia', ...
    'HuFengXian', ...
    'YuDongJian', ...
    'WuYueFen', ...
    'LiPing', ...
    'MaoXiaoMing', ...
    'ShengGuoLiang', ...
    'ZhangXiaoHong', ...
    'ZhengXiangQuan', ...
    'ZhaoPeiGen', ...
    'ChenLingHua', ...
    'FanDongDong', ...
    'HuangDan', ...
    'ZhangMing', ...
    'GengHui', ...
    'ChenMeiJu'};

importLogDir = fullfile(studyRoot, 'derivatives', 'leaddbs', 'import_logs');
mh_util_make_dir(importLogDir);
importLog = fullfile(importLogDir, ['dwi_import_', timestamp, '.csv']);
cleanupLog = fullfile(importLogDir, ['dwi_reimport_cleanup_', timestamp, '.csv']);
trashRoot = fullfile(getenv('HOME'), '.Trash', ['stnsnr_dwi_reimport_', timestamp]);

importRows = {};
cleanupRows = {};
sourceSets = struct();

preflight_environment(studyRoot, sourceRoot, freeSurferLicense);

for i = 1:numel(subjects)
    subjectId = subjects{i};
    patientName = ['sub-', subjectId];
    [sourceBase, sourcePaths] = resolve_source_set(fullfile(sourceRoot, patientName));
    validate_dwi_set(sourcePaths.nii, sourcePaths.bval, sourcePaths.bvec, sourcePaths.json);
    validate_subject_anchors(studyRoot, patientName);
    sourceSets.(subjectId).base = sourceBase;
    sourceSets.(subjectId).paths = sourcePaths;
    importRows = append_import_log(importRows, 'source_validation', subjectId, patientName, ...
        'valid', sourceBase, '', fullfile(sourceRoot, patientName), '', '', '', ...
        'Source DWI set passed validation');
end
write_import_log(importLog, importRows);
write_cleanup_log(cleanupLog, cleanupRows);

for i = 1:numel(subjects)
    subjectId = subjects{i};
    patientName = ['sub-', subjectId];
    targetDir = fullfile(studyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
    targetBase = [patientName, '_ses-preop_dwi'];
    targetPaths = target_dwi_paths(targetDir, targetBase);
    sourceBase = sourceSets.(subjectId).base;
    sourcePaths = sourceSets.(subjectId).paths;

    [cleanupRows, movedCount] = move_existing_subject_dwi_outputs(cleanupRows, ...
        studyRoot, patientName, targetBase, trashRoot);
    if movedCount == 0
        cleanupRows = append_cleanup_log(cleanupRows, subjectId, patientName, ...
            'nothing_to_move', '', '', '', 'No existing target DWI outputs were present');
    end
    write_cleanup_log(cleanupLog, cleanupRows);

    mh_util_make_dir(targetDir);
    [importRows, ~] = copy_source_set(importRows, subjectId, patientName, ...
        sourceBase, sourcePaths, targetPaths);
    validate_dwi_set(targetPaths.nii, targetPaths.bval, targetPaths.bvec, targetPaths.json);
    importRows = append_import_log(importRows, 'raw_validation', subjectId, patientName, ...
        'valid', sourceBase, '', targetDir, '', '', '', ...
        'Raw BIDS DWI set passed validation');
    write_import_log(importLog, importRows);
end

validate_rawdata_import(studyRoot, subjects);

% run_project_dwi_fake_b0_coreg fixes 'CoregistrationTag', 'dwi_synb0_fakeb0'
% and 'RunCoregistration', false for this fake-B0 UI-coreg workflow.
result = run_project_dwi_fake_b0_coreg( ...
    'StudyRoot', studyRoot, ...
    'RepoDir', repoDir, ...
    'ImportLog', importLog, ...
    'SubjectIds', subjects, ...
    'FreeSurferLicense', freeSurferLicense, ...
    'PhaseEncodingVector', [0 1 0], ...
    'DefaultTotalReadoutTime', 0.05, ...
    'Synb0MinDockerMemoryGB', 12, ...
    'Synb0WorkRoot', synb0WorkRoot, ...
    'Parallel', false, ...
    'ParallelWorkers', 1, ...
    'MaxConcurrentSynb0', 1, ...
    'Force', true);

validate_preprocess_result(studyRoot, subjects, result);

fprintf('\nFinished STNSNr DWI re-import and Synb0/eddy fake-B0 preprocessing.\n');
fprintf('Import log: %s\n', importLog);
fprintf('Cleanup log: %s\n', cleanupLog);
fprintf('Status CSV: %s\n', result.statusCsv);
fprintf('Trash root: %s\n', trashRoot);

function preflight_environment(studyRoot, sourceRoot, freeSurferLicense)
if ~isfolder(studyRoot)
    error('Study root does not exist: %s', studyRoot);
end
if ~isfolder(sourceRoot)
    error('DWI source root does not exist: %s', sourceRoot);
end
mh_util_must_be_file(freeSurferLicense, 'FreeSurfer license');
[status, out] = system('docker info --format "{{.MemTotal}}"');
if status ~= 0
    error('Docker is not available for Synb0-DISCO: %s', strtrim(out));
end
end

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

function validate_subject_anchors(studyRoot, patientName)
anatDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, ...
    'coregistration', 'anat');
if ~isfolder(anatDir)
    error('Missing anatomical coregistration directory: %s', anatDir);
end
assert_has_modality(anatDir, 'T1w');
assert_has_modality(anatDir, 'T2w');
end

function assert_has_modality(anatDir, modality)
files = dir(fullfile(anatDir, ['*', modality, '.nii']));
files = files(~startsWith({files.name}, '._'));
if isempty(files)
    error('No anchorNative %s image found in %s.', modality, anatDir);
end
end

function [rows, movedCount] = move_existing_subject_dwi_outputs(rows, studyRoot, patientName, targetBase, trashRoot)
movedCount = 0;
rawDir = fullfile(studyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
rawNames = { ...
    [targetBase, '.nii.gz'], ...
    [targetBase, '.json'], ...
    [targetBase, '.bval'], ...
    [targetBase, '.bvec']};
for i = 1:numel(rawNames)
    rawPath = fullfile(rawDir, rawNames{i});
    [rows, moved] = move_path_to_trash(rows, patientName, 'rawdata_dwi', rawPath, ...
        fullfile(trashRoot, 'rawdata', patientName, 'ses-preop', 'dwi', rawNames{i}));
    movedCount = movedCount + moved;
    appleDoublePath = fullfile(rawDir, ['._', rawNames{i}]);
    [rows, moved] = move_path_to_trash(rows, patientName, 'rawdata_dwi_appledouble', appleDoublePath, ...
        fullfile(trashRoot, 'rawdata', patientName, 'ses-preop', 'dwi', ['._', rawNames{i}]));
    movedCount = movedCount + moved;
end

preprocDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, 'preprocessing', 'dwi');
if isfolder(preprocDir)
    items = dir(preprocDir);
    items = items(~ismember({items.name}, {'.', '..'}));
    for i = 1:numel(items)
        source = fullfile(preprocDir, items(i).name);
        target = fullfile(trashRoot, 'derivatives', patientName, 'preprocessing', 'dwi', items(i).name);
        [rows, moved] = move_path_to_trash(rows, patientName, 'preprocessing_dwi', source, target);
        movedCount = movedCount + moved;
    end
end

coregAnatDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, ...
    'coregistration', 'anat');
if isfolder(coregAnatDir)
    items = dir(fullfile(coregAnatDir, '*B0*'));
    for i = 1:numel(items)
        source = fullfile(coregAnatDir, items(i).name);
        target = fullfile(trashRoot, 'derivatives', patientName, 'coregistration', 'anat', items(i).name);
        [rows, moved] = move_path_to_trash(rows, patientName, 'coregistration_anat_b0', source, target);
        movedCount = movedCount + moved;
    end
end
end

function [rows, moved] = move_path_to_trash(rows, patientName, phase, source, target)
moved = 0;
subjectId = erase(patientName, 'sub-');
if ~(isfile(source) || isfolder(source))
    return;
end
targetDir = fileparts(target);
mh_util_make_dir(targetDir);
sourceHash = '';
if isfile(source)
    sourceHash = file_sha256(source);
end
movefile(source, target);
moved = 1;
rows = append_cleanup_log(rows, subjectId, patientName, phase, source, target, ...
    sourceHash, 'Moved existing target output to Trash');
end

function [rows, copied] = copy_source_set(rows, subjectId, patientName, sourceBase, sourcePaths, targetPaths)
extensions = {'.nii.gz', '.json', '.bval', '.bvec'};
sourceFiles = {sourcePaths.nii, sourcePaths.json, sourcePaths.bval, sourcePaths.bvec};
targetFiles = {targetPaths.nii, targetPaths.json, targetPaths.bval, targetPaths.bvec};
copied = struct();

for i = 1:numel(extensions)
    source = sourceFiles{i};
    target = targetFiles{i};
    copyfile(source, target);
    sourceHash = file_sha256(source);
    targetHash = file_sha256(target);
    if ~strcmp(sourceHash, targetHash)
        error('Checksum mismatch after copy: %s -> %s', source, target);
    end
    rows = append_import_log(rows, 'copy_result', subjectId, patientName, 'copied', ...
        sourceBase, extensions{i}, source, target, sourceHash, targetHash, ...
        'Copied and checksum-verified');
    copied.(extension_field(extensions{i})) = target;
end
end

function validate_rawdata_import(studyRoot, subjects)
for i = 1:numel(subjects)
    patientName = ['sub-', subjects{i}];
    targetBase = [patientName, '_ses-preop_dwi'];
    targetDir = fullfile(studyRoot, 'rawdata', patientName, 'ses-preop', 'dwi');
    paths = target_dwi_paths(targetDir, targetBase);
    validate_dwi_set(paths.nii, paths.bval, paths.bvec, paths.json);
end

pattern = fullfile(studyRoot, 'rawdata', 'sub-*', 'ses-preop', 'dwi', '*_dwi.*');
files = dir(pattern);
files = files(~startsWith({files.name}, '._'));
expected = numel(subjects) * 4;
if numel(files) ~= expected
    error('Expected %d non-AppleDouble rawdata DWI files, found %d.', expected, numel(files));
end
end

function validate_preprocess_result(studyRoot, subjects, result)
summary = result.summary;
if height(summary) ~= numel(subjects)
    error('Expected %d status rows, found %d.', numel(subjects), height(summary));
end
if ~all(strcmp(string(summary.status), "pending_ui_coregistration"))
    disp(summary(:, {'subject', 'status', 'message'}));
    error('Not all subjects reached pending_ui_coregistration.');
end
if ~all(strcmp(string(summary.coregistration_status), "pending_ui"))
    disp(summary(:, {'subject', 'coregistration_status', 'message'}));
    error('Not all subjects have pending_ui coregistration status.');
end

for i = 1:numel(subjects)
    patientName = ['sub-', subjects{i}];
    base = [patientName, '_ses-preop'];
    dwiDir = fullfile(studyRoot, 'derivatives', 'leaddbs', patientName, 'preprocessing', 'dwi');
    mh_util_must_be_file(fullfile(dwiDir, [base, '_desc-preproc_dwi.nii']), 'corrected DWI');
    mh_util_must_be_file(fullfile(dwiDir, [base, '_desc-preproc_dwi.bval']), 'corrected DWI bval');
    mh_util_must_be_file(fullfile(dwiDir, [base, '_desc-preproc_dwi.bvec']), 'corrected DWI bvec');
    b0Path = fullfile(dwiDir, [base, '_desc-preproc_b0.nii']);
    b0Json = fullfile(dwiDir, [base, '_desc-preproc_b0.json']);
    mh_util_must_be_file(b0Path, 'corrected fake B0');
    mh_util_must_be_file(b0Json, 'corrected fake B0 metadata');
    metadata = jsondecode(fileread(b0Json));
    if ~isfield(metadata, 'FakeCoregisterVolume') || ~metadata.FakeCoregisterVolume
        error('FakeCoregisterVolume metadata is missing or false: %s', b0Json);
    end
    if ~isfield(metadata, 'ExcludeFromNormalization') || ~metadata.ExcludeFromNormalization
        error('ExcludeFromNormalization metadata is missing or false: %s', b0Json);
    end
end

normalizationB0 = dir(fullfile(studyRoot, 'derivatives', 'leaddbs', 'sub-*', ...
    'normalization', 'anat', '*B0*'));
normalizationB0 = normalizationB0(~startsWith({normalizationB0.name}, '._'));
if ~isempty(normalizationB0)
    error('Unexpected B0 files exist under normalization/anat.');
end
end

function rows = append_import_log(rows, phase, subjectId, patientName, status, sourceBase, extension, sourcePath, targetPath, sourceHash, targetHash, message)
rows(end + 1, :) = {phase, subjectId, patientName, status, sourceBase, extension, ...
    sourcePath, targetPath, sourceHash, targetHash, message};
end

function rows = append_cleanup_log(rows, subjectId, patientName, phase, sourcePath, trashPath, sourceHash, message)
rows(end + 1, :) = {subjectId, patientName, phase, sourcePath, trashPath, ...
    sourceHash, message};
end

function write_import_log(path, rows)
if isempty(rows)
    T = cell2table(cell(0, 11), 'VariableNames', import_log_columns());
else
    T = cell2table(rows, 'VariableNames', import_log_columns());
end
writetable(T, path);
end

function columns = import_log_columns()
columns = { ...
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
    'message'};
end

function write_cleanup_log(path, rows)
if isempty(rows)
    T = cell2table(cell(0, 7), 'VariableNames', cleanup_log_columns());
else
    T = cell2table(rows, 'VariableNames', cleanup_log_columns());
end
writetable(T, path);
end

function columns = cleanup_log_columns()
columns = { ...
    'subject', ...
    'patient', ...
    'phase', ...
    'source_path', ...
    'trash_path', ...
    'source_sha256', ...
    'message'};
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
