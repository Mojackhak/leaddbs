% Launch independent MATLAB batch workers for patient-level VTA coverage.

repoDir = '/Users/mojackhu/Github/leaddbs';
cd(repoDir);
addpath(genpath(repoDir));

subjectRoot = mh_fiber_getenv_default('STNSNR_VTA_SUBJECT_ROOT', ...
    '/Volumes/VAL/STNSNr/derivatives/leaddbs');
workbook = mh_fiber_getenv_default('STNSNR_VTA_WORKBOOK', ...
    '/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx');
cohortOutputDir = mh_fiber_getenv_default('STNSNR_VTA_COHORT_OUTPUT_DIR', ...
    '/Volumes/VAL/STNSNr/summary/vta');
workerScript = fullfile(repoDir, 'my_helper', 'fiber', 'stnsnr', ...
    'run_stnsnr_vta_coverage_worker.m');
matlabExe = mh_fiber_getenv_default('STNSNR_MATLAB_EXE', '/Applications/MATLAB_R2024b.app/bin/matlab');
workerCount = mh_fiber_env_number('STNSNR_VTA_WORKERS', 2, ...
    'run_stnsnr_vta_coverage_parallel:InvalidEnvNumber');
dryRun = mh_fiber_env_flag('STNSNR_VTA_DRY_RUN', false, ...
    'run_stnsnr_vta_coverage_parallel:InvalidEnvFlag');

rows = readtable(workbook, 'Sheet', 'Contact Parameters', 'VariableNamingRule', 'preserve', ...
    'TextType', 'string');
subjectIds = unique(string(rows.ID), 'stable');
requestedIds = mh_fiber_split_env_list(getenv('STNSNR_VTA_SUBJECT_IDS'));
if ~isempty(requestedIds)
    subjectIds = subjectIds(ismember(subjectIds, requestedIds));
end
if isempty(subjectIds)
    error('run_stnsnr_vta_coverage_parallel:NoSubjects', ...
        'No subjects are available for parallel launch.');
end

workerCount = max(1, min(workerCount, numel(subjectIds)));
timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
logDir = fullfile(cohortOutputDir, 'logs', ['parallel_', timestamp]);
envValues = struct();
envValues.STNSNR_VTA_SUBJECT_ROOT = subjectRoot;
envValues.STNSNR_VTA_WORKBOOK = workbook;
envValues.STNSNR_VTA_COHORT_OUTPUT_DIR = cohortOutputDir;
envValues.STNSNR_VTA_SKIP_COMPLETED = true;
envValues.STNSNR_VTA_SKIP_LOCKED = false;
envValues.STNSNR_VTA_GM_ATLAS = mh_fiber_getenv_default( ...
    'STNSNR_VTA_GM_ATLAS', 'DISTAL Minimal (Ewert 2017)');
envValues.STNSNR_VTA_MODEL_KEY = mh_fiber_getenv_default( ...
    'STNSNR_VTA_MODEL_KEY', 'simbio');
envValues.STNSNR_VTA_EXECUTION_MODE = mh_fiber_getenv_default( ...
    'STNSNR_VTA_EXECUTION_MODE', 'sequential');
envValues.STNSNR_VTA_PARALLEL_WORKERS = mh_fiber_getenv_default( ...
    'STNSNR_VTA_PARALLEL_WORKERS', '1');
envValues.STNSNR_VTA_TASK_MATLAB_EXE = mh_fiber_getenv_default( ...
    'STNSNR_VTA_TASK_MATLAB_EXE', matlabExe);
envValues.STNSNR_VTA_TASK_CONDA_ENV = mh_fiber_getenv_default( ...
    'STNSNR_VTA_TASK_CONDA_ENV', 'leaddbs');
envValues.STNSNR_VTA_PROCESS_WORK_DIR = mh_fiber_getenv_default( ...
    'STNSNR_VTA_PROCESS_WORK_DIR', '');
envValues.STNSNR_VTA_PROCESS_POLL_SECONDS = mh_fiber_getenv_default( ...
    'STNSNR_VTA_PROCESS_POLL_SECONDS', '2');
envValues.STNSNR_VTA_PROCESS_TIMEOUT_SECONDS = mh_fiber_getenv_default( ...
    'STNSNR_VTA_PROCESS_TIMEOUT_SECONDS', '0');

jobs = mh_vta_launch_process_workers(subjectIds, workerScript, logDir, ...
    'WorkerCount', workerCount, ...
    'MatlabExe', matlabExe, ...
    'DryRun', dryRun, ...
    'CondaEnv', 'leaddbs', ...
    'Env', envValues);
jobsCsv = fullfile(logDir, 'parallel_jobs.csv');
writetable(jobs, jobsCsv);
writetable(jobs, fullfile(cohortOutputDir, 'parallel_jobs_latest.csv'));

if dryRun
    fprintf('\nDry-run prepared %d independent MATLAB batch worker(s); no workers were launched.\n', workerCount);
else
    fprintf('\nLaunched %d independent MATLAB batch worker(s).\n', workerCount);
end
fprintf('Worker log directory: %s\n', logDir);
fprintf('Job table: %s\n', jobsCsv);
fprintf('After workers finish, run:\n');
fprintf('/Applications/MATLAB_R2024b.app/bin/matlab -batch "run(''%s'')"\n', ...
    fullfile(repoDir, 'my_helper', 'fiber', 'stnsnr', ...
    'run_stnsnr_vta_coverage_cohort_aggregate.m'));
