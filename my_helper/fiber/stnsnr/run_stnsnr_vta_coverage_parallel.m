% Launch independent MATLAB batch workers for patient-level VTA coverage.

repoDir = '/Users/mojackhu/Github/leaddbs';
cd(repoDir);
addpath(genpath(repoDir));

subjectRoot = '/Volumes/VAL/STNSNr/derivatives/leaddbs';
workbook = '/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx';
cohortOutputDir = '/Volumes/VAL/STNSNr/summary/vta';
workerScript = fullfile(repoDir, 'my_helper', 'fiber', 'stnsnr', ...
    'run_stnsnr_vta_coverage_worker.m');
matlabExe = getenv_default('STNSNR_MATLAB_EXE', '/Applications/MATLAB_R2024b.app/bin/matlab');
workerCount = env_number('STNSNR_VTA_WORKERS', 2);
dryRun = env_flag('STNSNR_VTA_DRY_RUN', false);

rows = readtable(workbook, 'Sheet', 'Contact Parameters', 'VariableNamingRule', 'preserve', ...
    'TextType', 'string');
subjectIds = unique(string(rows.ID), 'stable');
requestedIds = split_env_list(getenv('STNSNR_VTA_SUBJECT_IDS'));
if ~isempty(requestedIds)
    subjectIds = subjectIds(ismember(subjectIds, requestedIds));
end
if isempty(subjectIds)
    error('run_stnsnr_vta_coverage_parallel:NoSubjects', ...
        'No subjects are available for parallel launch.');
end

workerCount = max(1, min(workerCount, numel(subjectIds)));
chunks = split_subjects(subjectIds, workerCount);
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
        shell_quote(matlabExe), shell_quote(batchExpr), ...
        shell_quote(matlabExe), shell_quote(batchExpr));
    cmd = sprintf(['env STNSNR_VTA_SUBJECT_IDS=%s ', ...
        'STNSNR_VTA_SKIP_COMPLETED=true ', ...
        'STNSNR_VTA_SKIP_LOCKED=false ', ...
        '/bin/zsh -lc %s > %s 2>&1 & echo $!'], ...
        shell_quote(subjectList), shell_quote(innerCmd), shell_quote(logPath));
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

function chunks = split_subjects(subjectIds, workerCount)
chunks = cell(workerCount, 1);
for i = 1:workerCount
    chunks{i} = strings(0, 1);
end
for i = 1:numel(subjectIds)
    workerIdx = mod(i - 1, workerCount) + 1;
    chunks{workerIdx}(end+1, 1) = subjectIds(i);
end
end

function values = split_env_list(rawValue)
if isempty(rawValue)
    values = strings(0, 1);
    return;
end
parts = string(regexp(rawValue, '[,;]+', 'split'));
values = strtrim(parts(:));
values = values(values ~= "");
end

function value = env_number(name, defaultValue)
rawValue = strtrim(string(getenv(name)));
if rawValue == ""
    value = defaultValue;
    return;
end
value = str2double(rawValue);
if isnan(value) || value < 1 || value ~= fix(value)
    error('run_stnsnr_vta_coverage_parallel:InvalidEnvNumber', ...
        'Invalid positive integer for %s: %s', name, rawValue);
end
end

function value = env_flag(name, defaultValue)
rawValue = lower(strtrim(string(getenv(name))));
if rawValue == ""
    value = defaultValue;
elseif ismember(rawValue, ["1", "true", "yes", "on"])
    value = true;
elseif ismember(rawValue, ["0", "false", "no", "off"])
    value = false;
else
    error('run_stnsnr_vta_coverage_parallel:InvalidEnvFlag', ...
        'Invalid logical value for %s: %s', name, rawValue);
end
end

function value = getenv_default(name, defaultValue)
rawValue = string(getenv(name));
if strlength(rawValue) == 0
    value = defaultValue;
else
    value = char(rawValue);
end
end

function quoted = shell_quote(value)
value = char(string(value));
quoted = ['''', strrep(value, '''', '''"''"'''), ''''];
end
