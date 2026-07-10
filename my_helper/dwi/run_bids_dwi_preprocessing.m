function result = run_bids_dwi_preprocessing(varargin)
% Run or dry-run standard BIDS/Lead-DBS DWI preprocessing.

p = inputParser;
p.FunctionName = 'run_bids_dwi_preprocessing';
p.addParameter('StudyRoot', '', @(x) ischar(x) || isstring(x));
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

subjects = normalize_subjects(opts.SubjectIds);
config = wrapper_config(opts, repoDir, subjects);

if logical(opts.DryRun)
    result = config;
    result.dryRun = true;
    return;
end

if isempty(config.studyRoot)
    error('run_bids_dwi_preprocessing:MissingStudyRoot', ...
        'StudyRoot must be provided.');
end

result = mh_fiber_register_imported_dwi_batch( ...
    'StudyRoot', config.studyRoot, ...
    'RepoDir', config.repoDir, ...
    'SubjectIds', config.subjects, ...
    'AnchorModality', config.anchorModality, ...
    'CoregistrationTag', 'dwi_synb0_fakeb0', ...
    'CoregistrationMethod', config.coregistrationMethod, ...
    'DistortionCorrection', config.distortionCorrection, ...
    'PhaseEncodingVector', config.phaseEncodingVector, ...
    'TotalReadoutTime', config.totalReadoutTime, ...
    'DefaultTotalReadoutTime', config.defaultTotalReadoutTime, ...
    'Synb0ContainerEngine', config.synb0ContainerEngine, ...
    'Synb0Image', config.synb0Image, ...
    'FreeSurferLicense', config.freeSurferLicense, ...
    'Synb0MinDockerMemoryGB', config.synb0MinDockerMemoryGB, ...
    'Synb0WorkRoot', config.synb0WorkRoot, ...
    'AllowT1Fallback', config.allowAnchorFallback, ...
    'RunCoregistration', config.runCoregistration, ...
    'GenerateOptionalDwiQc', config.generateOptionalDwiQc, ...
    'Parallel', config.parallel, ...
    'ParallelWorkers', config.parallelWorkers, ...
    'MaxConcurrentSynb0', config.maxConcurrentSynb0, ...
    'Force', config.force);
result.bidsDwiWrapper = config;
end

function repoDir = resolve_repo_dir(repoDir)
repoDir = char(string(repoDir));
if isempty(repoDir)
    repoDir = fileparts(fileparts(fileparts(mfilename('fullpath'))));
end
end

function subjects = normalize_subjects(subjectIds)
if isempty(subjectIds)
    subjects = {};
else
    subjects = cellstr(string(subjectIds));
end
end

function config = wrapper_config(opts, repoDir, subjects)
config = struct();
config.dryRun = false;
config.studyRoot = char(string(opts.StudyRoot));
config.repoDir = repoDir;
config.subjects = subjects;
if isempty(subjects)
    config.subjectSelection = 'discover';
else
    config.subjectSelection = 'explicit';
end
config.anchorModality = char(string(opts.AnchorModality));
config.allowAnchorFallback = logical(opts.AllowAnchorFallback);
config.coregistrationMethod = char(string(opts.CoregistrationMethod));
config.runCoregistration = logical(opts.RunCoregistration);
config.distortionCorrection = char(string(opts.DistortionCorrection));
config.phaseEncodingVector = double(opts.PhaseEncodingVector(:)');
config.totalReadoutTime = double(opts.TotalReadoutTime);
config.defaultTotalReadoutTime = double(opts.DefaultTotalReadoutTime);
config.generateOptionalDwiQc = logical(opts.GenerateOptionalDwiQc);
config.freeSurferLicense = char(string(opts.FreeSurferLicense));
config.synb0ContainerEngine = char(string(opts.Synb0ContainerEngine));
config.synb0Image = char(string(opts.Synb0Image));
config.synb0MinDockerMemoryGB = double(opts.Synb0MinDockerMemoryGB);
config.synb0WorkRoot = char(string(opts.Synb0WorkRoot));
config.parallel = logical(opts.Parallel);
config.parallelWorkers = max(1, round(double(opts.ParallelWorkers)));
config.maxConcurrentSynb0 = max(1, round(double(opts.MaxConcurrentSynb0)));
config.force = logical(opts.Force);
end
