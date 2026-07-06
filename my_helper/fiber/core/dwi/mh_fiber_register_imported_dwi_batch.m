function result = mh_fiber_register_imported_dwi_batch(varargin)
% Build BIDS DWI job specs, process them, and write the status CSV.

p = inputParser;
p.addParameter('StudyRoot', '', @(x) ischar(x) || isstring(x));
p.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('ImportLog', '', @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('AnchorModality', 'T2w', @(x) ischar(x) || isstring(x));
p.addParameter('CoregistrationTag', 'dwi_t2', @(x) ischar(x) || isstring(x));
p.addParameter('CoregistrationMethod', 'ANTs', @(x) ischar(x) || isstring(x));
p.addParameter('DistortionCorrection', 'none', @(x) ischar(x) || isstring(x));
p.addParameter('PhaseEncodingVector', [0 1 0], @(x) isnumeric(x) && numel(x) == 3);
p.addParameter('TotalReadoutTime', NaN, @(x) isnumeric(x) && isscalar(x));
p.addParameter('DefaultTotalReadoutTime', 0.05, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Synb0ContainerEngine', 'auto', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0Image', 'leonyichencai/synb0-disco:v3.1', @(x) ischar(x) || isstring(x));
p.addParameter('FreeSurferLicense', '', @(x) ischar(x) || isstring(x));
p.addParameter('Synb0MinDockerMemoryGB', 12, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Synb0WorkRoot', '', @(x) ischar(x) || isstring(x));
p.addParameter('AllowT1Fallback', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('RunCoregistration', [], @(x) isempty(x) || islogical(x) || isnumeric(x));
p.addParameter('GenerateOptionalDwiQc', true, @(x) islogical(x) || isnumeric(x));
p.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
p.addParameter('MaxConcurrentSynb0', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x >= 1));
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = normalize_options(p.Results);

validate_options(opts);
addpath(genpath(opts.RepoDir));

derivativesRoot = fullfile(opts.StudyRoot, 'derivatives', 'leaddbs');
importLogDir = fullfile(derivativesRoot, 'import_logs');
mh_util_make_dir(importLogDir);

[subjects, sourceBases] = resolve_subjects(opts);
jobSpecs = build_job_specs(opts, derivativesRoot, subjects, sourceBases);
summary = mh_fiber_process_imported_dwi_batch(jobSpecs, opts);

statusCsv = fullfile(importLogDir, status_filename_from_coreg_tag(opts.CoregistrationTag));
writetable(summary, statusCsv);

result = struct();
result.summary = summary;
result.statusCsv = statusCsv;
result.subjects = subjects;
result.jobSpecs = jobSpecs;

fprintf('\nDWI registration batch summary written to:\n%s\n', statusCsv);
disp(summary(:, {'subject', 'status', 'message', 'anchor_modality', 'coregistration_method', 'low_resolution_warning'}));
end

function opts = normalize_options(opts)
opts.StudyRoot = char(string(opts.StudyRoot));
opts.RepoDir = resolve_repo_dir_from_option(opts.RepoDir);
opts.ImportLog = char(string(opts.ImportLog));
opts.AnchorModality = normalize_anchor_modality(opts.AnchorModality);
opts.CoregistrationTag = char(string(opts.CoregistrationTag));
opts.CoregistrationMethod = normalize_coregistration_method(opts.CoregistrationMethod);
opts.DistortionCorrection = normalize_distortion_correction(opts.DistortionCorrection);
opts.PhaseEncodingVector = double(opts.PhaseEncodingVector(:)');
opts.TotalReadoutTime = double(opts.TotalReadoutTime);
opts.DefaultTotalReadoutTime = double(opts.DefaultTotalReadoutTime);
opts.Synb0ContainerEngine = char(string(opts.Synb0ContainerEngine));
opts.Synb0Image = char(string(opts.Synb0Image));
opts.FreeSurferLicense = char(string(opts.FreeSurferLicense));
opts.Synb0MinDockerMemoryGB = double(opts.Synb0MinDockerMemoryGB);
opts.Synb0WorkRoot = char(string(opts.Synb0WorkRoot));
opts.AllowT1Fallback = logical(opts.AllowT1Fallback);
opts.GenerateOptionalDwiQc = logical(opts.GenerateOptionalDwiQc);
opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
if isempty(opts.MaxConcurrentSynb0)
    opts.MaxConcurrentSynb0 = [];
else
    opts.MaxConcurrentSynb0 = max(1, round(double(opts.MaxConcurrentSynb0)));
end
opts.Force = logical(opts.Force);
if isempty(opts.RunCoregistration)
    opts.RunCoregistration = ~strcmp(opts.DistortionCorrection, 'synb0');
else
    opts.RunCoregistration = logical(opts.RunCoregistration);
end
end

function validate_options(opts)
if isempty(opts.CoregistrationTag)
    error('CoregistrationTag must not be empty.');
end
if isempty(opts.StudyRoot)
    error('mh_fiber_register_imported_dwi_batch:MissingStudyRootParameter', ...
        'StudyRoot must be provided.');
end
if ~isfolder(opts.StudyRoot)
    error('mh_fiber_register_imported_dwi_batch:MissingStudyRoot', ...
        'Study root does not exist: %s', opts.StudyRoot);
end
if ~isfolder(opts.RepoDir)
    error('mh_fiber_register_imported_dwi_batch:MissingRepoDir', ...
        'Lead-DBS repository does not exist: %s', opts.RepoDir);
end
end

function jobSpecs = build_job_specs(opts, derivativesRoot, subjects, sourceBases)
jobSpecs = struct([]);
for i = 1:numel(subjects)
    spec = mh_fiber_dwi_bids_jobspec(opts.StudyRoot, subjects{i}, ...
        'DerivativesRoot', derivativesRoot, ...
        'CoregistrationTag', opts.CoregistrationTag, ...
        'AnchorModality', opts.AnchorModality, ...
        'AllowT1Fallback', opts.AllowT1Fallback, ...
        'SourceBase', lookup_source_base(sourceBases, subjects{i}), ...
        'RequireT1', strcmp(opts.DistortionCorrection, 'synb0'));
    if i == 1
        jobSpecs = repmat(spec, numel(subjects), 1);
    else
        jobSpecs(i) = spec;
    end
end
end

function anchorModality = normalize_anchor_modality(anchorModality)
anchorModality = char(string(anchorModality));
switch lower(anchorModality)
    case {'t1', 't1w'}
        anchorModality = 'T1w';
    case {'t2', 't2w'}
        anchorModality = 'T2w';
    otherwise
        error('Unsupported AnchorModality: %s. Use T1w or T2w.', anchorModality);
end
end

function coregMethod = normalize_coregistration_method(coregMethod)
coregMethod = char(string(coregMethod));
switch lower(strtrim(coregMethod))
    case {'ants', 'ants (avants 2008)'}
        coregMethod = 'ANTs';
    case {'spm', 'spm (friston 2007)'}
        coregMethod = 'SPM';
    case {'hybrid spm & ants', 'hybridspmants', 'hybrid spm and ants'}
        coregMethod = 'Hybrid SPM & ANTs';
    case {'flirt bbr', 'flirtbbr', 'bbr', 'fsl flirt bbr'}
        coregMethod = 'FLIRT BBR';
    otherwise
        error('Unsupported CoregistrationMethod: %s. Use ANTs, SPM, Hybrid SPM & ANTs, or FLIRT BBR.', coregMethod);
end
end

function distortionCorrection = normalize_distortion_correction(distortionCorrection)
distortionCorrection = lower(strtrim(char(string(distortionCorrection))));
switch distortionCorrection
    case {'', 'none', 'off', 'false', 'no'}
        distortionCorrection = 'none';
    case {'synb0', 'synb0-disco', 'synb0_disco'}
        distortionCorrection = 'synb0';
    otherwise
        error('Unsupported DistortionCorrection: %s. Use none or synb0.', distortionCorrection);
end
end

function statusName = status_filename_from_coreg_tag(coregTag)
if strcmp(coregTag, 'dwi')
    statusName = 'dwi_registration_status.csv';
else
    suffix = regexprep(coregTag, '^dwi', '');
    statusName = ['dwi_registration', suffix, '_status.csv'];
end
end

function [subjects, sourceBases] = resolve_subjects(opts)
sourceBases = containers.Map('KeyType', 'char', 'ValueType', 'char');
importSubjects = {};

if ~isempty(opts.ImportLog) && isfile(opts.ImportLog)
    [importSubjects, sourceBases] = read_subjects_from_import_log(opts.ImportLog);
end

if ~isempty(opts.SubjectIds)
    subjects = cellstr(string(opts.SubjectIds));
elseif ~isempty(importSubjects)
    subjects = importSubjects;
else
    subjects = discover_subjects_from_rawdata(opts.StudyRoot);
end

subjects = stable_unique(subjects);
if isempty(subjects)
    error('mh_fiber_register_imported_dwi_batch:NoSubjects', ...
        ['No subjects were provided or discovered. Provide SubjectIds, pass an ImportLog ', ...
        'with copied DWI rows, or add BIDS DWI files under StudyRoot/rawdata/sub-*/ses-preop/dwi/.']);
end
end

function [subjects, sourceBases] = read_subjects_from_import_log(importLog)
subjects = {};
sourceBases = containers.Map('KeyType', 'char', 'ValueType', 'char');
try
    T = readtable(importLog, 'TextType', 'string');
    if all(ismember(["phase", "subject", "status", "source_base", "extension"], string(T.Properties.VariableNames)))
        copied = T(strcmp(T.phase, "copy_result") & strcmp(T.status, "copied") & strcmp(T.extension, ".nii.gz"), :);
        subjects = stable_unique(cellstr(copied.subject));
        for i = 1:height(T)
            subjStr = string(T.subject(i));
            srcStr = string(T.source_base(i));
            if ~ismissing(subjStr) && ~ismissing(srcStr) && strlength(subjStr) > 0 && strlength(srcStr) > 0
                sourceBases(char(subjStr)) = char(srcStr);
            end
        end
    end
catch ME
    warning('mh_fiber_register_imported_dwi_batch:ImportLogReadFailed', ...
        'Could not parse import log %s: %s', importLog, ME.message);
end
end

function subjects = discover_subjects_from_rawdata(studyRoot)
pattern = fullfile(studyRoot, 'rawdata', 'sub-*', 'ses-preop', 'dwi', '*_dwi.nii.gz');
dwiFiles = dir(pattern);
dwiFiles = dwiFiles(~startsWith({dwiFiles.name}, '._'));
subjects = {};
for i = 1:numel(dwiFiles)
    dwiDir = dwiFiles(i).folder;
    sessionDir = fileparts(fileparts(dwiDir));
    [~, patientName] = fileparts(sessionDir);
    if startsWith(patientName, 'sub-')
        subjects{end+1} = char(extractAfter(patientName, 'sub-')); %#ok<AGROW>
    end
end
subjects = stable_unique(subjects);
end

function out = stable_unique(values)
values = string(values);
out = {};
for i = 1:numel(values)
    if ismissing(values(i))
        continue;
    end
    value = char(values(i));
    if ~isempty(value) && ~any(strcmp(out, value))
        out{end+1} = value; %#ok<AGROW>
    end
end
end

function repoDir = resolve_repo_dir_from_option(repoDir)
repoDir = char(string(repoDir));
if ~isempty(repoDir)
    return;
end

repoDir = mh_util_resolve_repo_dir(mfilename('fullpath'));
if ~isfile(fullfile(repoDir, 'ea_normalize.m'))
    error('mh_fiber_register_imported_dwi_batch:RepoRootNotFound', ...
        'Could not resolve Lead-DBS repository root. Provide RepoDir explicitly.');
end
end

function sourceBase = lookup_source_base(sourceBases, subjectId)
if isKey(sourceBases, subjectId)
    sourceBase = sourceBases(subjectId);
else
    sourceBase = '';
end
end
