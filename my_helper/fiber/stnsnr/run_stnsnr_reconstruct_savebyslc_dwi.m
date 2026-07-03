function status = run_stnsnr_reconstruct_savebyslc_dwi(varargin)
% Repair STNSNr SaveBySlc mosaic DWI exports through the reusable DWI backend.

parser = inputParser;
parser.FunctionName = 'run_stnsnr_reconstruct_savebyslc_dwi';
parser.addParameter('RepoDir', '/Users/mojackhu/Github/leaddbs', @(x) ischar(x) || isstring(x));
parser.addParameter('StudyRoot', '/Volumes/VAL/STNSNr', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceRoot', '/Volumes/VAL/STNSNrdwi', @(x) ischar(x) || isstring(x));
parser.addParameter('RawRoot', '/Volumes/VAL/raw', @(x) ischar(x) || isstring(x));
parser.addParameter('RepairRoot', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Subjects', {'GengHui', 'ZhaoPeiGen'}, @(x) iscell(x) || isstring(x) || ischar(x));
parser.addParameter('ReplaceRawdata', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = normalize_options(parser.Results);

addpath(genpath(opts.RepoDir));
if isempty(opts.RepairRoot)
    timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    opts.RepairRoot = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs', ...
        'import_logs', ['savebyslc_repair_', timestamp]);
end

inputs = build_inputs(opts);
status = mh_fiber_reconstruct_mosaic_dwi_batch(inputs, ...
    'Parallel', opts.Parallel, ...
    'ParallelWorkers', opts.ParallelWorkers, ...
    'Force', opts.Force, ...
    'DryRun', opts.DryRun);

mh_util_make_dir(opts.RepairRoot);
writetable(status, fullfile(opts.RepairRoot, 'mosaic_reconstruction_status.csv'));

if opts.ReplaceRawdata && ~opts.DryRun
    replacement = replace_rawdata_outputs(status, opts);
    writetable(replacement, fullfile(opts.RepairRoot, 'rawdata_replacement_log.csv'));
    status = outerjoin(status, replacement, 'Keys', 'Subject', 'MergeKeys', true);
end

fprintf('\nSTNSNr SaveBySlc reconstruction status:\n%s\n', ...
    fullfile(opts.RepairRoot, 'mosaic_reconstruction_status.csv'));
end

function opts = normalize_options(opts)
fields = {'RepoDir', 'StudyRoot', 'SourceRoot', 'RawRoot', 'RepairRoot'};
for i = 1:numel(fields)
    opts.(fields{i}) = char(string(opts.(fields{i})));
end
if ischar(opts.Subjects) || isstring(opts.Subjects)
    opts.Subjects = cellstr(string(opts.Subjects));
end
opts.ReplaceRawdata = logical(opts.ReplaceRawdata);
opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
opts.Force = logical(opts.Force);
opts.DryRun = logical(opts.DryRun);
end

function inputs = build_inputs(opts)
specs = subject_specs();
subjects = opts.Subjects(:);
rows = cell(numel(subjects), 8);

for i = 1:numel(subjects)
    subject = subjects{i};
    idx = strcmp(specs.Subject, subject);
    if ~any(idx)
        error('run_stnsnr_reconstruct_savebyslc_dwi:UnsupportedSubject', ...
            'No STNSNr SaveBySlc repair spec is defined for subject: %s', subject);
    end
    spec = specs(idx, :);
    sourceDir = fullfile(opts.SourceRoot, ['sub-', subject]);
    sourceBase = char(spec.SourceBase);
    rawPatientDir = char(spec.RawPatientDir);
    dicomSeriesDir = char(spec.DicomSeriesDir);
    outputDir = fullfile(opts.RepairRoot, ['sub-', subject]);
    outputBase = ['sub-', subject, '_ses-preop_dwi'];

    rows(i, :) = { ...
        subject, ...
        fullfile(sourceDir, [sourceBase, '.nii.gz']), ...
        fullfile(sourceDir, [sourceBase, '.json']), ...
        fullfile(sourceDir, [sourceBase, '.bval']), ...
        fullfile(sourceDir, [sourceBase, '.bvec']), ...
        fullfile(opts.RawRoot, rawPatientDir, dicomSeriesDir), ...
        outputDir, ...
        outputBase};
end

inputs = cell2table(rows, 'VariableNames', {'Subject', 'SourceNifti', ...
    'SourceJson', 'SourceBval', 'SourceBvec', 'DicomDir', 'OutputDir', ...
    'OutputBase'});
end

function specs = subject_specs()
specs = table( ...
    ["GengHui"; "ZhaoPeiGen"], ...
    ["sub-GengHui_epi_dti_tra_dir64_2.0mm_s901"; ...
     "sub-ZhaoPeiGen_epi_dti_tra_dir64_2.0mm_s901"], ...
    ["GENG HUI 8"; "ZHAO PEI GEN 8"], ...
    ["epi_dti_tra_dir64_2.0mm_SaveBySlc"; ...
     "epi_dti_tra_dir64_2.0mm_SaveBySlc"], ...
    'VariableNames', {'Subject', 'SourceBase', 'RawPatientDir', 'DicomSeriesDir'});
end

function replacement = replace_rawdata_outputs(status, opts)
timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
trashRoot = fullfile(getenv('HOME'), '.Trash', ['leaddbs_savebyslc_rawdata_', timestamp]);
mh_util_make_dir(trashRoot);

rows = {};
for i = 1:height(status)
    subject = char(string(status.Subject(i)));
    if ~strcmp(char(string(status.Status(i))), 'reconstructed')
        rows(end + 1, :) = {subject, 'skipped', '', '', 'reconstruction did not succeed'}; %#ok<AGROW>
        continue;
    end

    targetDir = fullfile(opts.StudyRoot, 'rawdata', ['sub-', subject], 'ses-preop', 'dwi');
    targetBase = ['sub-', subject, '_ses-preop_dwi'];
    mh_util_make_dir(targetDir);
    sourceFiles = {char(string(status.OutputNifti(i))), char(string(status.OutputJson(i))), ...
        char(string(status.OutputBval(i))), char(string(status.OutputBvec(i)))};
    targetFiles = {fullfile(targetDir, [targetBase, '.nii.gz']), ...
        fullfile(targetDir, [targetBase, '.json']), ...
        fullfile(targetDir, [targetBase, '.bval']), ...
        fullfile(targetDir, [targetBase, '.bvec'])};

    for j = 1:numel(targetFiles)
        if isfile(targetFiles{j})
            trashed = move_to_trash(targetFiles{j}, trashRoot);
            rows(end + 1, :) = {subject, 'trashed_existing', targetFiles{j}, trashed, 'moved old rawdata file to Trash'}; %#ok<AGROW>
        end
        copyfile(sourceFiles{j}, targetFiles{j}, 'f');
        rows(end + 1, :) = {subject, 'copied_repaired', sourceFiles{j}, targetFiles{j}, 'copied repaired rawdata file'}; %#ok<AGROW>
    end
end

replacement = cell2table(rows, 'VariableNames', {'Subject', 'ReplacementStatus', ...
    'SourcePath', 'TargetPath', 'ReplacementMessage'});
end

function trashPath = move_to_trash(path, trashRoot)
mh_util_make_dir(trashRoot);
[~, name, ext] = fileparts(path);
if strcmp(ext, '.gz')
    [~, innerName, innerExt] = fileparts(name);
    name = [innerName, innerExt, ext];
else
    name = [name, ext];
end
trashPath = fullfile(trashRoot, name);
counter = 1;
while isfile(trashPath)
    trashPath = fullfile(trashRoot, sprintf('%s_%03d', name, counter));
    counter = counter + 1;
end
movefile(path, trashPath);
end
