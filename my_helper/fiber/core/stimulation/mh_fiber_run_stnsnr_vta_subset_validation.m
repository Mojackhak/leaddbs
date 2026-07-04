function result = mh_fiber_run_stnsnr_vta_subset_validation(varargin)
% Run STN/SNr VTA validation on a copied subject subset.

parser = inputParser;
parser.FunctionName = 'mh_fiber_run_stnsnr_vta_subset_validation';
executionDefaults = mh_vta_default_execution_options();
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SourceSubjectRoot', '/Volumes/VAL/STNSNr/derivatives/leaddbs', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('ValidationRoot', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Workbook', '/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('Sheet', 'Contact Parameters', @(x) ischar(x) || isstring(x));
parser.addParameter('AtlasDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectIDs', strings(0, 1), @is_string_list);
parser.addParameter('SubjectNames', strings(0, 1), @is_string_list);
parser.addParameter('MaxSubjects', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Modes', {'sequential', 'process', 'parpool'}, @is_string_list);
parser.addParameter('ParallelWorkers', 2, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('ForceVta', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ForceOutputs', true, @(x) islogical(x) || isnumeric(x));
parser.addParameter('PrepareOnly', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ReusePreparedRoot', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('VtaGmAtlas', mh_fiber_stnsnr_default_vta_gm_atlas(), ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('VtaModelKey', mh_fiber_stnsnr_default_vta_model_key(), ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('VtaMatlabExe', executionDefaults.matlabExe, ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('VtaCondaEnv', executionDefaults.condaEnv, ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('VtaProcessPollSeconds', executionDefaults.processPollSeconds, ...
    @(x) isnumeric(x) && isscalar(x) && x >= 0.1);
parser.addParameter('VtaProcessTimeoutSeconds', executionDefaults.processTimeoutSeconds, ...
    @(x) isnumeric(x) && isscalar(x) && x >= 0);
parser.addParameter('ThresholdsVPerMm', [0.18, 0.20, 0.22], @(x) isnumeric(x) && isvector(x));
parser.addParameter('MainThresholdVPerMm', 0.20, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('OutputVoxelSizeMm', 0.5, @(x) isnumeric(x) && isscalar(x) && x > 0);
parser.parse(varargin{:});
opts = parser.Results;

repoDir = char(string(opts.RepoDir));
if isempty(repoDir)
    repoDir = mh_util_resolve_repo_dir(mfilename('fullpath'));
end
sourceSubjectRoot = char(string(opts.SourceSubjectRoot));
validationRoot = char(string(opts.ValidationRoot));
if isempty(validationRoot)
    validationRoot = default_validation_root();
end
workbook = char(string(opts.Workbook));
sheetName = char(string(opts.Sheet));
atlasDir = char(string(opts.AtlasDir));
if isempty(atlasDir)
    atlasDir = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', ...
        'atlases', 'Custom_Ewert_Zhang_Middlebrooks0.05');
end

mh_util_must_be_folder(repoDir, 'repository directory');
mh_util_must_be_folder(sourceSubjectRoot, 'source Lead-DBS subject root');
mh_util_must_be_file(workbook, 'stimulation workbook');
mh_util_must_be_folder(atlasDir, 'STN/SNr atlas directory');
copiedSubjectRoot = fullfile(validationRoot, 'derivatives', 'leaddbs');
reusePreparedRoot = logical(opts.ReusePreparedRoot);
if reusePreparedRoot
    assert_prepared_validation_root(validationRoot, sourceSubjectRoot, copiedSubjectRoot);
else
    assert_fresh_validation_root(validationRoot, sourceSubjectRoot);
end

subjects = select_validation_subjects(workbook, sheetName, opts);
if reusePreparedRoot
    copiedSubjects = collect_prepared_subject_subset(subjects, sourceSubjectRoot, copiedSubjectRoot);
else
    mh_util_make_dir(fileparts(validationRoot));
    mh_util_make_dir(copiedSubjectRoot);
    copiedSubjects = copy_subject_subset(subjects, sourceSubjectRoot, copiedSubjectRoot);
end

result = struct();
result.validationRoot = validationRoot;
result.sourceSubjectRoot = sourceSubjectRoot;
result.copiedSubjectRoot = copiedSubjectRoot;
result.workbook = workbook;
result.sheet = sheetName;
result.atlasDir = atlasDir;
result.subjects = copiedSubjects;
result.prepareOnly = logical(opts.PrepareOnly);
result.reusePreparedRoot = reusePreparedRoot;
result.modeResults = struct([]);

if result.prepareOnly
    write_validation_manifest(result, opts);
    return;
end

modes = normalize_modes(opts.Modes);
modeResults = repmat(struct( ...
    'mode', '', ...
    'cohortOutputDir', '', ...
    'processWorkDir', '', ...
    'coverageResult', []), numel(modes), 1);

for i = 1:numel(modes)
    mode = char(modes(i));
    cohortOutputDir = fullfile(validationRoot, 'summary', 'vta', mode);
    processWorkDir = fullfile(validationRoot, 'process_tasks', mode);
    fprintf('\nRunning copied-subset STN/SNr VTA validation mode: %s\n', mode);
    coverageResult = mh_fiber_run_stnsnr_vta_coverage( ...
        'RepoDir', repoDir, ...
        'SubjectRoot', copiedSubjectRoot, ...
        'Workbook', workbook, ...
        'Sheet', sheetName, ...
        'AtlasDir', atlasDir, ...
        'CohortOutputDir', cohortOutputDir, ...
        'ThresholdsVPerMm', opts.ThresholdsVPerMm, ...
        'MainThresholdVPerMm', opts.MainThresholdVPerMm, ...
        'OutputVoxelSizeMm', opts.OutputVoxelSizeMm, ...
        'ForceVta', logical(opts.ForceVta), ...
        'ForceOutputs', logical(opts.ForceOutputs), ...
        'StopOnSubjectError', true, ...
        'SubjectIDs', string({copiedSubjects.id}), ...
        'WriteCohortOutputs', true, ...
        'CohortOnly', false, ...
        'SkipCompletedSubjects', false, ...
        'UseSubjectLocks', false, ...
        'SkipLockedSubjects', false, ...
        'VtaGmAtlas', char(string(opts.VtaGmAtlas)), ...
        'VtaModelKey', char(string(opts.VtaModelKey)), ...
        'VtaExecutionMode', mode, ...
        'VtaParallelWorkers', max(1, round(double(opts.ParallelWorkers))), ...
        'VtaMatlabExe', char(string(opts.VtaMatlabExe)), ...
        'VtaCondaEnv', char(string(opts.VtaCondaEnv)), ...
        'VtaProcessWorkDir', processWorkDir, ...
        'VtaProcessDryRun', false, ...
        'VtaProcessPollSeconds', double(opts.VtaProcessPollSeconds), ...
        'VtaProcessTimeoutSeconds', double(opts.VtaProcessTimeoutSeconds));
    modeResults(i).mode = mode;
    modeResults(i).cohortOutputDir = cohortOutputDir;
    modeResults(i).processWorkDir = processWorkDir;
    modeResults(i).coverageResult = coverageResult;
end

result.modeResults = modeResults;
write_validation_manifest(result, opts);
end

function root = default_validation_root()
timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
root = fullfile('/Volumes/VAL/STNSNr/validation', ['vta_refactor_subset_', timestamp]);
end

function assert_fresh_validation_root(validationRoot, sourceSubjectRoot)
if exist(validationRoot, 'dir') == 7 || exist(validationRoot, 'file') == 2
    error('mh_fiber_run_stnsnr_vta_subset_validation:ValidationRootExists', ...
        'Validation root already exists and will not be overwritten: %s', validationRoot);
end
if path_is_under(validationRoot, sourceSubjectRoot)
    error('mh_fiber_run_stnsnr_vta_subset_validation:UnsafeValidationRoot', ...
        'Validation root must not be inside the source subject root: %s', validationRoot);
end
end

function assert_prepared_validation_root(validationRoot, sourceSubjectRoot, copiedSubjectRoot)
if path_is_under(validationRoot, sourceSubjectRoot)
    error('mh_fiber_run_stnsnr_vta_subset_validation:UnsafeValidationRoot', ...
        'Validation root must not be inside the source subject root: %s', validationRoot);
end
mh_util_must_be_folder(validationRoot, 'prepared validation root');
mh_util_must_be_folder(copiedSubjectRoot, 'prepared copied subject root');
end

function tf = path_is_under(pathValue, rootValue)
pathText = strip_trailing_filesep(char(string(pathValue)));
rootText = strip_trailing_filesep(char(string(rootValue)));
tf = strcmp(pathText, rootText) || startsWith([pathText, filesep], [rootText, filesep]);
end

function text = strip_trailing_filesep(text)
while strlength(string(text)) > 1 && endsWith(text, filesep)
    text = text(1:end-1);
end
end

function subjects = select_validation_subjects(workbook, sheetName, opts)
rows = readtable(workbook, 'Sheet', sheetName, 'VariableNamingRule', 'preserve');
required = {'ID', 'NameEn', 'NameZh'};
mh_util_require_table_vars(rows, required, ...
    'mh_fiber_run_stnsnr_vta_subset_validation:MissingWorkbookColumn', ...
    'Missing workbook column: %s');
subjects = unique(rows(:, required), 'rows', 'stable');
subjects.ID = string(subjects.ID);
subjects.NameEn = string(subjects.NameEn);
subjects.NameZh = string(subjects.NameZh);

subjectIds = normalize_string_list(opts.SubjectIDs);
subjectNames = normalize_string_list(opts.SubjectNames);
if isempty(subjectIds) && isempty(subjectNames)
    maxSubjects = min(height(subjects), max(1, round(double(opts.MaxSubjects))));
    subjects = subjects(1:maxSubjects, :);
    return;
end

keep = false(height(subjects), 1);
if ~isempty(subjectIds)
    keep = keep | ismember(string(subjects.ID), subjectIds);
end
if ~isempty(subjectNames)
    nameCandidates = [string(subjects.NameEn), string(subjects.NameZh), "sub-" + string(subjects.NameEn)];
    for i = 1:numel(subjectNames)
        keep = keep | any(strcmpi(nameCandidates, subjectNames(i)), 2);
    end
end
subjects = subjects(keep, :);
if height(subjects) == 0
    error('mh_fiber_run_stnsnr_vta_subset_validation:NoSelectedSubjects', ...
        'No subjects matched the requested validation subset.');
end
end

function copiedSubjects = copy_subject_subset(subjects, sourceSubjectRoot, copiedSubjectRoot)
copiedSubjects = repmat(struct( ...
    'id', '', ...
    'name_en', '', ...
    'name_zh', '', ...
    'source_dir', '', ...
    'copied_dir', ''), height(subjects), 1);

for i = 1:height(subjects)
    nameEn = char(string(subjects.NameEn(i)));
    patientName = ['sub-', nameEn];
    sourceDir = fullfile(sourceSubjectRoot, patientName);
    copiedDir = fullfile(copiedSubjectRoot, patientName);
    mh_util_must_be_folder(sourceDir, ['source subject directory for ', patientName]);
    if exist(copiedDir, 'dir') == 7 || exist(copiedDir, 'file') == 2
        error('mh_fiber_run_stnsnr_vta_subset_validation:CopiedSubjectExists', ...
            'Copied subject destination already exists: %s', copiedDir);
    end
    fprintf('Copying validation subject %s to %s\n', patientName, copiedDir);
    [ok, message] = copyfile(sourceDir, copiedDir);
    if ~ok
        error('mh_fiber_run_stnsnr_vta_subset_validation:CopyFailed', ...
            'Could not copy %s to %s: %s', sourceDir, copiedDir, message);
    end
    copiedSubjects(i).id = char(string(subjects.ID(i)));
    copiedSubjects(i).name_en = nameEn;
    copiedSubjects(i).name_zh = char(string(subjects.NameZh(i)));
    copiedSubjects(i).source_dir = sourceDir;
    copiedSubjects(i).copied_dir = copiedDir;
end
end

function copiedSubjects = collect_prepared_subject_subset(subjects, sourceSubjectRoot, copiedSubjectRoot)
copiedSubjects = repmat(struct( ...
    'id', '', ...
    'name_en', '', ...
    'name_zh', '', ...
    'source_dir', '', ...
    'copied_dir', ''), height(subjects), 1);

for i = 1:height(subjects)
    nameEn = char(string(subjects.NameEn(i)));
    patientName = ['sub-', nameEn];
    sourceDir = fullfile(sourceSubjectRoot, patientName);
    copiedDir = fullfile(copiedSubjectRoot, patientName);
    mh_util_must_be_folder(sourceDir, ['source subject directory for ', patientName]);
    mh_util_must_be_folder(copiedDir, ['prepared copied subject directory for ', patientName]);
    copiedSubjects(i).id = char(string(subjects.ID(i)));
    copiedSubjects(i).name_en = nameEn;
    copiedSubjects(i).name_zh = char(string(subjects.NameZh(i)));
    copiedSubjects(i).source_dir = sourceDir;
    copiedSubjects(i).copied_dir = copiedDir;
end
end

function modes = normalize_modes(value)
modes = lower(normalize_string_list(value));
allowed = ["sequential"; "process"; "parpool"];
if isempty(modes)
    error('mh_fiber_run_stnsnr_vta_subset_validation:MissingModes', ...
        'At least one validation mode is required.');
end
bad = ~ismember(modes, allowed);
if any(bad)
    error('mh_fiber_run_stnsnr_vta_subset_validation:InvalidMode', ...
        'Unsupported validation mode: %s', char(strjoin(modes(bad), ', ')));
end
modes = unique(modes, 'stable');
end

function values = normalize_string_list(value)
if isempty(value)
    values = strings(0, 1);
    return;
end
if iscell(value) && all(cellfun(@ischar, value))
    value = string(value);
end
if ischar(value)
    value = string(value);
end
value = string(value(:));
parts = strings(0, 1);
for i = 1:numel(value)
    splitValue = string(regexp(char(value(i)), '[,;]+', 'split'));
    parts = [parts; splitValue(:)]; %#ok<AGROW>
end
values = strtrim(parts);
values = values(values ~= "");
values = unique(values, 'stable');
end

function tf = is_string_list(value)
tf = isempty(value) || ischar(value) || isstring(value) || ...
    (iscell(value) && all(cellfun(@ischar, value)));
end

function write_validation_manifest(result, opts)
manifest = struct();
manifest.generated_at = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z'));
manifest.validation_root = result.validationRoot;
manifest.source_subject_root = result.sourceSubjectRoot;
manifest.copied_subject_root = result.copiedSubjectRoot;
manifest.workbook = result.workbook;
manifest.sheet = result.sheet;
manifest.atlas_dir = result.atlasDir;
manifest.prepare_only = result.prepareOnly;
manifest.reuse_prepared_root = result.reusePreparedRoot;
manifest.force_vta = logical(opts.ForceVta);
manifest.force_outputs = logical(opts.ForceOutputs);
manifest.subjects = result.subjects;
manifest.mode_results = mode_results_for_manifest(result.modeResults);
mh_util_write_json(validation_manifest_path(result), manifest);
end

function path = validation_manifest_path(result)
path = fullfile(result.validationRoot, 'validation_manifest.json');
if result.reusePreparedRoot && isfile(path)
    timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
    path = fullfile(result.validationRoot, ['validation_manifest_', timestamp, '.json']);
end
end

function modeResults = mode_results_for_manifest(results)
modeResults = repmat(struct( ...
    'mode', '', ...
    'cohort_output_dir', '', ...
    'process_work_dir', '', ...
    'coverage_long_csv', '', ...
    'contact_qc_csv', ''), numel(results), 1);
for i = 1:numel(results)
    modeResults(i).mode = results(i).mode;
    modeResults(i).cohort_output_dir = results(i).cohortOutputDir;
    modeResults(i).process_work_dir = results(i).processWorkDir;
    if isstruct(results(i).coverageResult)
        modeResults(i).coverage_long_csv = mh_util_get_field( ...
            results(i).coverageResult, 'coverageLongCsv', '');
        modeResults(i).contact_qc_csv = mh_util_get_field( ...
            results(i).coverageResult, 'contactQcCsv', '');
    end
end
end
