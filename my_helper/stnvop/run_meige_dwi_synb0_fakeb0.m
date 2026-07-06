function result = run_meige_dwi_synb0_fakeb0(varargin)
% Run or dry-run the Meige DWI Synb0/eddy fake-B0 preprocessing workflow.

p = inputParser;
p.FunctionName = 'run_meige_dwi_synb0_fakeb0';
p.addParameter('RunMode', 'pilot', @(x) ischar(x) || isstring(x));
p.addParameter('StudyRoot', '/Volumes/VAL/meige', @(x) ischar(x) || isstring(x));
p.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
p.addParameter('SubjectIds', {}, @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('PilotSubjects', {'Meige001', 'Meige008', 'Meige021'}, ...
    @(x) iscell(x) || isstring(x) || ischar(x));
p.addParameter('FreeSurferLicense', '/Applications/freesurfer/8.2.0/license.txt', ...
    @(x) ischar(x) || isstring(x));
p.addParameter('PhaseEncodingVector', [0 1 0], @(x) isnumeric(x) && numel(x) == 3);
p.addParameter('DefaultTotalReadoutTime', 0.05, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Synb0MinDockerMemoryGB', 12, @(x) isnumeric(x) && isscalar(x) && x >= 0);
p.addParameter('Synb0WorkRoot', fullfile(getenv('HOME'), 'Library', 'Caches', ...
    'leaddbs', 'meige_synb0_work'), @(x) ischar(x) || isstring(x));
p.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('ParallelWorkers', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
p.addParameter('MaxConcurrentSynb0', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
p.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
p.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
p.parse(varargin{:});
opts = p.Results;

repoDir = resolve_repo_dir(opts.RepoDir);
addpath(genpath(repoDir));

runMode = normalize_run_mode(opts.RunMode);
subjects = resolve_subjects(opts.SubjectIds, opts.PilotSubjects, runMode);
config = wrapper_config(opts, repoDir, runMode, subjects);

if logical(opts.DryRun)
    result = config;
    result.dryRun = true;
    return;
end

result = run_project_dwi_fake_b0_coreg( ...
    'StudyRoot', config.studyRoot, ...
    'RepoDir', config.repoDir, ...
    'SubjectIds', config.subjects, ...
    'FreeSurferLicense', config.freeSurferLicense, ...
    'PhaseEncodingVector', config.phaseEncodingVector, ...
    'DefaultTotalReadoutTime', config.defaultTotalReadoutTime, ...
    'Synb0MinDockerMemoryGB', config.synb0MinDockerMemoryGB, ...
    'Synb0WorkRoot', config.synb0WorkRoot, ...
    'Parallel', config.parallel, ...
    'ParallelWorkers', config.parallelWorkers, ...
    'MaxConcurrentSynb0', config.maxConcurrentSynb0, ...
    'Force', config.force);
result.meigeWrapper = config;
end

function repoDir = resolve_repo_dir(repoDir)
repoDir = char(string(repoDir));
if ~isempty(repoDir)
    return;
end
repoDir = fileparts(fileparts(fileparts(mfilename('fullpath'))));
end

function runMode = normalize_run_mode(runMode)
runMode = lower(strtrim(char(string(runMode))));
switch runMode
    case {'pilot', 'cohort'}
        return;
    otherwise
        error('run_meige_dwi_synb0_fakeb0:InvalidRunMode', ...
            'RunMode must be pilot or cohort.');
end
end

function subjects = resolve_subjects(subjectIds, pilotSubjects, runMode)
if ~isempty(subjectIds)
    subjects = cellstr(string(subjectIds));
    return;
end
if strcmp(runMode, 'pilot')
    subjects = cellstr(string(pilotSubjects));
else
    subjects = cohort_subjects();
end
end

function subjects = cohort_subjects()
subjects = cell(1, 22);
for i = 1:21
    subjects{i} = sprintf('Meige%03d', i);
end
subjects{22} = 'Dys022';
end

function config = wrapper_config(opts, repoDir, runMode, subjects)
config = struct();
config.dryRun = false;
config.runMode = runMode;
config.studyRoot = char(string(opts.StudyRoot));
config.repoDir = repoDir;
config.subjects = subjects;
config.freeSurferLicense = char(string(opts.FreeSurferLicense));
config.phaseEncodingVector = double(opts.PhaseEncodingVector(:)');
config.defaultTotalReadoutTime = double(opts.DefaultTotalReadoutTime);
config.synb0MinDockerMemoryGB = double(opts.Synb0MinDockerMemoryGB);
config.synb0WorkRoot = char(string(opts.Synb0WorkRoot));
config.parallel = logical(opts.Parallel);
config.parallelWorkers = max(1, round(double(opts.ParallelWorkers)));
config.maxConcurrentSynb0 = max(1, round(double(opts.MaxConcurrentSynb0)));
config.force = logical(opts.Force);
config.coregistrationTag = 'dwi_synb0_fakeb0';
config.distortionCorrection = 'synb0';
config.runCoregistration = false;
config.anchorModality = 'T2w';
config.allowT1Fallback = false;
end
