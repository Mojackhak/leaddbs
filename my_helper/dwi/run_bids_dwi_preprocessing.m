function result = run_bids_dwi_preprocessing(varargin)
% Validate, plan, or run standard BIDS/Lead-DBS DWI preprocessing.

p = inputParser;
p.FunctionName = 'run_bids_dwi_preprocessing';
p.addParameter('Config', '', @(x) ischar(x) || isstring(x));
p.addParameter('Mode', 'run', @(x) ischar(x) || isstring(x));
p.addParameter('StudyRoot', '', @(x) ischar(x) || isstring(x));
p.addParameter('Session', 'preop', @(x) ischar(x) || isstring(x));
p.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('AnchorModality', 'T2w', @(x) ischar(x) || isstring(x));
p.addParameter('AllowAnchorFallback', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('CoregistrationMethod', 'SPM', @(x) ischar(x) || isstring(x));
p.addParameter('RunCoregistration', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('DistortionCorrection', 'synb0', @(x) ischar(x) || isstring(x));
p.addParameter('PhaseEncodingVector', [0 1 0], @(x) isnumeric(x) && numel(x) == 3);
p.addParameter('TotalReadoutTime', NaN, @(x) isnumeric(x) && isscalar(x));
p.addParameter('DefaultTotalReadoutTime', 0.05, ...
    @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('GenerateOptionalDwiQc', true, @(x) islogical(x) || isnumeric(x));
p.addParameter('FreeSurferLicense', '/Applications/freesurfer/8.2.0/license.txt', ...
    @(x) ischar(x) || isstring(x));
p.addParameter('Synb0ContainerEngine', 'auto', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0Image', 'leonyichencai/synb0-disco:v3.1', ...
    @(x) ischar(x) || isstring(x));
p.addParameter('Synb0MinDockerMemoryGB', 12, ...
    @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Synb0WorkRoot', fullfile(getenv('HOME'), 'Library', 'Caches', ...
    'leaddbs', 'synb0_work'), @(x) ischar(x) || isstring(x));
p.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('ParallelWorkers', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
p.addParameter('MaxConcurrentSynb0', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = p.Results;

repoDir = resolve_repo_dir(opts.RepoDir);
addpath(genpath(repoDir));
provided = supplied_parameter_names(varargin);
overrides = build_config_overrides(opts, provided);
[config, configSource] = mh_fiber_dwi_load_config(opts.Config, overrides);

if logical(opts.DryRun)
    result = legacy_dry_run_result(config, configSource, repoDir);
    return;
end

mode = normalize_mode(opts.Mode);
validate_project_root(config.project.study_root);
subjects = mh_fiber_dwi_resolve_subjects(config);
[jobSpecs, preflight] = build_and_validate_jobs(config, subjects);
jobManifest = build_job_manifest(jobSpecs, preflight);

result = struct();
result.mode = mode;
result.config = config;
result.configSource = configSource;
result.repoDir = repoDir;
result.subjects = subjects;
result.jobSpecs = jobSpecs;
result.preflight = preflight;
result.jobManifest = jobManifest;
result.summary = preflight_status_table(preflight, mode);
runRecord = mh_fiber_dwi_run_records('start', configSource, config, ...
    jobManifest, mode);

try
    if strcmp(mode, 'run')
        processingOptions = build_processing_options(config);
        result.summary = mh_fiber_process_imported_dwi_batch(jobSpecs, processingOptions);
    elseif strcmp(mode, 'plan')
        disp(jobManifest);
    end
catch ME
    failed = preflight_status_table(preflight, 'failed');
    failed.message(:) = {mh_fiber_compact_message(ME.message, 240)};
    mh_fiber_dwi_run_records('finish', runRecord, failed);
    rethrow(ME);
end
runRecord = mh_fiber_dwi_run_records('finish', runRecord, result.summary);
result.runRecord = runRecord;
result.bidsDwiWrapper = config;
end

function repoDir = resolve_repo_dir(repoDir)
repoDir = char(string(repoDir));
if isempty(repoDir)
    repoDir = fileparts(fileparts(fileparts(mfilename('fullpath'))));
end
if ~isfolder(repoDir)
    error('run_bids_dwi_preprocessing:MissingRepoDir', ...
        'Lead-DBS repository does not exist: %s', repoDir);
end
end

function provided = supplied_parameter_names(args)
provided = {};
for i = 1:2:numel(args)
    provided{end + 1} = lower(char(string(args{i}))); %#ok<AGROW>
end
provided = unique(provided, 'stable');
end

function tf = supplied(provided, name)
tf = ismember(lower(name), provided);
end

function overrides = build_config_overrides(opts, provided)
overrides = struct();
hasConfig = ~isempty(char(string(opts.Config)));

if ~hasConfig
    studyRoot = char(string(opts.StudyRoot));
    if isempty(studyRoot)
        error('run_bids_dwi_preprocessing:MissingStudyRoot', ...
            'Provide Config or StudyRoot.');
    end
    [~, projectName] = fileparts(studyRoot);
    if isempty(projectName)
        projectName = 'bids_dwi_project';
    end
    overrides.project = struct( ...
        'name', projectName, ...
        'study_root', studyRoot, ...
        'session', char(string(opts.Session)));
    overrides.subjects = subject_override(opts.SubjectIds);
elseif supplied(provided, 'StudyRoot')
    overrides.project = struct('study_root', char(string(opts.StudyRoot)));
end

if supplied(provided, 'Session')
    overrides = set_nested(overrides, {'project', 'session'}, char(string(opts.Session)));
end
if supplied(provided, 'SubjectIds') && ~isempty(opts.SubjectIds)
    overrides.subjects = subject_override(opts.SubjectIds);
end
if supplied(provided, 'AnchorModality')
    overrides = set_nested(overrides, {'anatomy', 'coregistration_anchor'}, ...
        char(string(opts.AnchorModality)));
end
if supplied(provided, 'AllowAnchorFallback')
    overrides = set_nested(overrides, {'anatomy', 'allow_anchor_fallback'}, ...
        logical(opts.AllowAnchorFallback));
end
if supplied(provided, 'CoregistrationMethod')
    overrides = set_nested(overrides, {'lead_dbs', 'coregistration_method'}, ...
        char(string(opts.CoregistrationMethod)));
end
if supplied(provided, 'RunCoregistration')
    overrides = set_nested(overrides, {'lead_dbs', 'run_coregistration'}, ...
        logical(opts.RunCoregistration));
end
if supplied(provided, 'DistortionCorrection')
    overrides = set_nested(overrides, {'dwi', 'distortion_correction'}, ...
        char(string(opts.DistortionCorrection)));
end
if supplied(provided, 'PhaseEncodingVector')
    overrides = set_nested(overrides, {'dwi', 'phase_encoding_vector'}, ...
        double(opts.PhaseEncodingVector(:)'));
end
if supplied(provided, 'TotalReadoutTime') && isfinite(opts.TotalReadoutTime)
    overrides = set_nested(overrides, {'dwi', 'total_readout_time'}, ...
        struct('strategy', 'fixed', 'seconds', double(opts.TotalReadoutTime)));
elseif supplied(provided, 'DefaultTotalReadoutTime')
    overrides = set_nested(overrides, {'dwi', 'total_readout_time'}, ...
        struct('strategy', 'json_then_fallback', ...
        'seconds', double(opts.DefaultTotalReadoutTime)));
end
if supplied(provided, 'GenerateOptionalDwiQc')
    overrides = set_nested(overrides, {'processing', 'generate_optional_dwi_qc'}, ...
        logical(opts.GenerateOptionalDwiQc));
end
if supplied(provided, 'FreeSurferLicense')
    overrides = set_nested(overrides, {'runtime', 'freesurfer_license'}, ...
        char(string(opts.FreeSurferLicense)));
end
if supplied(provided, 'Synb0ContainerEngine')
    overrides = set_nested(overrides, {'runtime', 'synb0', 'container_engine'}, ...
        char(string(opts.Synb0ContainerEngine)));
end
if supplied(provided, 'Synb0Image')
    overrides = set_nested(overrides, {'runtime', 'synb0', 'container_image'}, ...
        char(string(opts.Synb0Image)));
end
if supplied(provided, 'Synb0WorkRoot')
    overrides = set_nested(overrides, {'runtime', 'synb0', 'work_root'}, ...
        char(string(opts.Synb0WorkRoot)));
end
if supplied(provided, 'Synb0MinDockerMemoryGB')
    overrides = set_nested(overrides, {'execution', 'synb0_min_memory_gb'}, ...
        double(opts.Synb0MinDockerMemoryGB));
end
if supplied(provided, 'Parallel')
    overrides = set_nested(overrides, {'execution', 'parallel'}, logical(opts.Parallel));
end
if supplied(provided, 'ParallelWorkers')
    overrides = set_nested(overrides, {'execution', 'parallel_workers'}, ...
        double(opts.ParallelWorkers));
end
if supplied(provided, 'MaxConcurrentSynb0')
    overrides = set_nested(overrides, {'execution', 'max_concurrent_synb0'}, ...
        double(opts.MaxConcurrentSynb0));
end
if supplied(provided, 'Force')
    overrides = set_nested(overrides, {'execution', 'force'}, logical(opts.Force));
end
end

function subjects = subject_override(subjectIds)
if isempty(subjectIds)
    subjects = struct('mode', 'auto');
else
    ids = cellstr(string(subjectIds));
    subjects = struct('mode', 'explicit', 'ids', {reshape(ids, 1, [])});
end
end

function value = set_nested(value, fields, fieldValue)
if isscalar(fields)
    value.(fields{1}) = fieldValue;
    return;
end
name = fields{1};
if ~isfield(value, name) || ~isstruct(value.(name))
    value.(name) = struct();
end
value.(name) = set_nested(value.(name), fields(2:end), fieldValue);
end

function mode = normalize_mode(mode)
mode = lower(strtrim(char(string(mode))));
if ~ismember(mode, {'validate', 'plan', 'run'})
    error('run_bids_dwi_preprocessing:InvalidMode', ...
        'Mode must be validate, plan, or run.');
end
end

function validate_project_root(studyRoot)
if ~isfolder(studyRoot)
    error('run_bids_dwi_preprocessing:MissingStudyRoot', ...
        'Study root does not exist: %s', studyRoot);
end
end

function [jobSpecs, preflight] = build_and_validate_jobs(config, subjects)
derivativesRoot = fullfile(config.project.study_root, 'derivatives', 'leaddbs');
requireT1 = strcmp(config.dwi.distortion_correction, 'synb0');
jobSpecs = struct([]);
preflight = struct([]);
for i = 1:numel(subjects)
    spec = mh_fiber_dwi_bids_jobspec(config.project.study_root, subjects{i}, ...
        'Session', config.project.session, ...
        'DerivativesRoot', derivativesRoot, ...
        'CoregistrationTag', 'dwi_synb0_fakeb0', ...
        'AnchorModality', config.anatomy.coregistration_anchor, ...
        'AllowT1Fallback', config.anatomy.allow_anchor_fallback, ...
        'RequireT1', requireT1);
    checked = mh_fiber_dwi_validate_jobspec(spec, 'RequireT1', requireT1);
    if i == 1
        jobSpecs = repmat(spec, numel(subjects), 1);
        preflight = repmat(checked, numel(subjects), 1);
    else
        jobSpecs(i) = spec;
        preflight(i) = checked;
    end
end
end

function manifest = build_job_manifest(jobSpecs, preflight)
n = numel(jobSpecs);
subject = cell(n, 1);
session = cell(n, 1);
sourceBase = cell(n, 1);
rawDwi = cell(n, 1);
rawJson = cell(n, 1);
rawBval = cell(n, 1);
rawBvec = cell(n, 1);
anchorAnat = cell(n, 1);
t1Anat = cell(n, 1);
stagedDwi = cell(n, 1);
b0Target = cell(n, 1);
dwiVolumes = zeros(n, 1);
b0Count = zeros(n, 1);
for i = 1:n
    subject{i} = jobSpecs(i).subjectId;
    session{i} = jobSpecs(i).session;
    sourceBase{i} = jobSpecs(i).sourceBase;
    rawDwi{i} = preflight(i).rawDwi;
    rawJson{i} = jobSpecs(i).paths.rawJson;
    rawBval{i} = jobSpecs(i).paths.rawBval;
    rawBvec{i} = jobSpecs(i).paths.rawBvec;
    anchorAnat{i} = jobSpecs(i).anchorAnat;
    t1Anat{i} = jobSpecs(i).t1Anat;
    stagedDwi{i} = jobSpecs(i).paths.dwi;
    b0Target{i} = jobSpecs(i).paths.fakeB0Coreg;
    dwiVolumes(i) = preflight(i).dwiVolumes;
    b0Count(i) = preflight(i).b0Count;
end
manifest = table(subject, session, sourceBase, rawDwi, rawJson, rawBval, ...
    rawBvec, anchorAnat, t1Anat, stagedDwi, b0Target, dwiVolumes, b0Count, ...
    'VariableNames', {'subject', 'session', 'source_base', 'raw_dwi', ...
    'raw_json', 'raw_bval', 'raw_bvec', 'anchor_anat', 't1_anat', ...
    'staged_dwi', 'b0_coreg_target', 'dwi_volumes', 'b0_count'});
end

function status = preflight_status_table(preflight, mode)
n = numel(preflight);
subject = cell(n, 1);
state = cell(n, 1);
message = repmat({'ok'}, n, 1);
for i = 1:n
    subject{i} = preflight(i).subject;
    if strcmp(mode, 'validate')
        state{i} = 'validated';
    elseif strcmp(mode, 'plan')
        state{i} = 'planned';
    else
        state{i} = mode;
    end
end
status = table(subject, state, message, ...
    'VariableNames', {'subject', 'status', 'message'});
end

function opts = build_processing_options(config)
opts = struct();
opts.AnchorModality = config.anatomy.coregistration_anchor;
opts.CoregistrationMethod = config.lead_dbs.coregistration_method;
opts.DistortionCorrection = config.dwi.distortion_correction;
opts.PhaseEncodingVector = config.dwi.phase_encoding_vector;
opts.B0ReferenceStrategy = config.dwi.b0_reference.strategy;
opts.B0Threshold = config.dwi.b0_reference.threshold;
if strcmp(config.dwi.total_readout_time.strategy, 'fixed')
    opts.TotalReadoutTime = config.dwi.total_readout_time.seconds;
else
    opts.TotalReadoutTime = NaN;
end
opts.DefaultTotalReadoutTime = config.dwi.total_readout_time.seconds;
opts.Synb0ContainerEngine = config.runtime.synb0.container_engine;
opts.Synb0Image = config.runtime.synb0.container_image;
opts.FreeSurferLicense = config.runtime.freesurfer_license;
opts.Synb0MinDockerMemoryGB = config.execution.synb0_min_memory_gb;
opts.Synb0WorkRoot = config.runtime.synb0.work_root;
opts.RunCoregistration = config.lead_dbs.run_coregistration;
opts.GenerateOptionalDwiQc = config.processing.generate_optional_dwi_qc;
opts.Parallel = config.execution.parallel;
opts.ParallelWorkers = config.execution.parallel_workers;
opts.MaxConcurrentSynb0 = config.execution.max_concurrent_synb0;
opts.Force = config.execution.force;
end

function result = legacy_dry_run_result(config, source, repoDir)
result = struct();
result.dryRun = true;
result.mode = 'dry-run';
result.config = config;
result.configSource = source;
result.repoDir = repoDir;
if strcmp(config.subjects.mode, 'explicit')
    result.subjects = config.subjects.ids;
else
    result.subjects = {};
end
result.studyRoot = config.project.study_root;
result.subjectSelection = config.subjects.mode;
result.anchorModality = config.anatomy.coregistration_anchor;
result.coregistrationMethod = config.lead_dbs.coregistration_method;
result.runCoregistration = config.lead_dbs.run_coregistration;
result.distortionCorrection = config.dwi.distortion_correction;
result.phaseEncodingVector = config.dwi.phase_encoding_vector;
result.b0ReferenceStrategy = config.dwi.b0_reference.strategy;
result.b0Threshold = config.dwi.b0_reference.threshold;
result.defaultTotalReadoutTime = config.dwi.total_readout_time.seconds;
result.parallel = config.execution.parallel;
result.parallelWorkers = config.execution.parallel_workers;
result.maxConcurrentSynb0 = config.execution.max_concurrent_synb0;
result.force = config.execution.force;
end
