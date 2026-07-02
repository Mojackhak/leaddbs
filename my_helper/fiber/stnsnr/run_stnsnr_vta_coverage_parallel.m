% Launch independent MATLAB batch workers for patient-level VTA coverage.

repoDir = '/Users/mojackhu/Github/leaddbs';
cd(repoDir);
addpath(genpath(repoDir));

subjectRoot = '/Volumes/VAL/STNSNr/derivatives/leaddbs';
workbook = '/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx';
cohortOutputDir = '/Volumes/VAL/STNSNr/summary/vta';
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
chunks = mh_fiber_split_subjects(subjectIds, workerCount);
timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss'));
logDir = fullfile(cohortOutputDir, 'logs', ['parallel_', timestamp]);
mkdir(logDir);

jobRows = cell(workerCount, 5);
for i = 1:workerCount
    ids = chunks{i};
    subjectList = strjoin(ids, ',');
    logPath = fullfile(logDir, sprintf('worker_%02d.log', i));
    batchExpr = sprintf('run(''%s'')', workerScript);
    innerCmd = sprintf(['if command -v conda >/dev/null 2>&1; then ', ...
        'conda run -n leaddbs %s -batch %s; else %s -batch %s; fi'], ...
        mh_fiber_shell_quote(matlabExe), mh_fiber_shell_quote(batchExpr), ...
        mh_fiber_shell_quote(matlabExe), mh_fiber_shell_quote(batchExpr));
    cmd = sprintf(['env STNSNR_VTA_SUBJECT_IDS=%s ', ...
        'STNSNR_VTA_SKIP_COMPLETED=true ', ...
        'STNSNR_VTA_SKIP_LOCKED=false ', ...
        '/bin/zsh -lc %s > %s 2>&1 & echo $!'], ...
        mh_fiber_shell_quote(subjectList), mh_fiber_shell_quote(innerCmd), ...
        mh_fiber_shell_quote(logPath));
    if dryRun
        pid = "dry-run";
        statusText = "dry_run";
        fprintf('Dry-run worker %02d: %s\n', i, subjectList);
    else
        [status, output] = system(cmd);
        if status ~= 0
            error('run_stnsnr_vta_coverage_parallel:LaunchFailed', ...
                'Could not launch worker %d: %s', i, output);
        end
        pid = strtrim(string(output));
        statusText = "running";
        fprintf('Launched worker %02d PID %s: %s\n', i, pid, subjectList);
    end
    jobRows(i, :) = {i, subjectList, pid, logPath, statusText};
end

jobs = cell2table(jobRows, 'VariableNames', ...
    {'worker_index', 'subject_ids', 'pid', 'log_path', 'status'});
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
