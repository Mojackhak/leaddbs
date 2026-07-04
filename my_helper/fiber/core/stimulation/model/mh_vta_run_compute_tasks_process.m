function results = mh_vta_run_compute_tasks_process(cfg, S, options, tasks, exec)
% Run atomic VTA compute tasks through isolated MATLAB worker processes.

tasks = tasks(:);
if isempty(tasks)
    results = struct([]);
    return;
end

settings = process_settings(cfg, exec, numel(tasks));
jobs = prepare_task_payloads(cfg, S, options, tasks, settings.work_dir);
workerJobs = prepare_worker_manifests(jobs, settings, 0);

if settings.dry_run
    results = dry_run_results(tasks, jobs, workerJobs);
    return;
end

pendingJobs = jobs;
retryIndex = 0;
while true
    workerJobs = prepare_worker_manifests(pendingJobs, settings, retryIndex);
    workerJobs = launch_workers(workerJobs, settings);
    [complete, missingJobs] = wait_for_results(pendingJobs, workerJobs, settings);
    if complete
        break;
    end

    if retryIndex >= settings.max_retries
        missingNames = char(strjoin(string({missingJobs.task_name}), ', '));
        error('mh_vta_run_compute_tasks_process:WorkerExited', ...
            'A VTA task worker exited before writing result(s): %s', missingNames);
    end

    retryIndex = retryIndex + 1;
    pendingJobs = missingJobs;
    fprintf('Retrying %d missing VTA process task(s), retry %d of %d.\n', ...
        numel(pendingJobs), retryIndex, settings.max_retries);
end
results = load_results(jobs);
end

function settings = process_settings(cfg, exec, taskCount)
defaults = mh_vta_default_execution_options();
settings = struct();
settings.repo_dir = mh_util_get_field(cfg, 'repoDir', ...
    mh_util_resolve_repo_dir(mfilename('fullpath')));
settings.worker_count = max(1, min(exec.parallel_workers, taskCount));
settings.matlab_exe = mh_vta_config_field(cfg, 'matlabExe', ...
    defaults.matlabExe);
settings.conda_env = mh_vta_config_field(cfg, 'condaEnv', defaults.condaEnv);
settings.dry_run = logical(mh_vta_config_field(cfg, 'processDryRun', ...
    defaults.processDryRun));
settings.poll_seconds = max(0.1, double(mh_vta_config_field(cfg, ...
    'processPollSeconds', defaults.processPollSeconds)));
settings.timeout_seconds = max(0, double(mh_vta_config_field(cfg, ...
    'processTimeoutSeconds', defaults.processTimeoutSeconds)));
settings.max_retries = max(0, round(double(mh_vta_config_field(cfg, ...
    'processMaxRetries', defaults.processMaxRetries))));

workDir = char(string(mh_vta_config_field(cfg, 'processWorkDir', defaults.processWorkDir)));
if isempty(workDir)
    outputDir = char(string(mh_util_get_field(cfg, 'outputDir', tempdir)));
    timestamp = char(datetime('now', 'Format', 'yyyyMMdd_HHmmss_SSS'));
    workDir = fullfile(outputDir, 'vta_process_tasks', timestamp);
end
settings.work_dir = workDir;
mh_util_make_dir(settings.work_dir);
end

function jobs = prepare_task_payloads(cfg, S, options, tasks, workDir)
jobs = repmat(struct( ...
    'task_index', 0, ...
    'payload_path', '', ...
    'result_path', '', ...
    'log_path', '', ...
    'task_name', ''), numel(tasks), 1);

for i = 1:numel(tasks)
    taskName = process_task_name(i, tasks(i));
    payloadPath = fullfile(workDir, [taskName, '_payload.mat']);
    resultPath = fullfile(workDir, [taskName, '_result.mat']);
    logPath = fullfile(workDir, [taskName, '.log']);
    payload = struct('cfg', cfg, 'S', S, 'options', options, 'task', tasks(i));
    save(payloadPath, 'payload', '-v7.3');

    jobs(i).task_index = i;
    jobs(i).payload_path = payloadPath;
    jobs(i).result_path = resultPath;
    jobs(i).log_path = logPath;
    jobs(i).task_name = taskName;
end
end

function taskName = process_task_name(index, task)
label = sprintf('task_%03d', index);
if isfield(task, 'stim_label')
    label = sprintf('%s_%s', label, mh_util_sanitize_label(task.stim_label));
end
if isfield(task, 'side')
    label = sprintf('%s_%s', label, upper(char(string(task.side))));
end
taskName = label;
end

function workerJobs = prepare_worker_manifests(jobs, settings, retryIndex)
chunks = split_indices(numel(jobs), settings.worker_count);
workerJobs = repmat(struct( ...
    'worker_index', 0, ...
    'manifest_path', '', ...
    'log_path', '', ...
    'pid', '', ...
    'status', '', ...
    'task_indices', [], ...
    'inner_command', '', ...
    'launch_command', ''), settings.worker_count, 1);

for i = 1:settings.worker_count
    taskIndices = chunks{i};
    manifest = struct();
    manifest.repo_dir = settings.repo_dir;
    manifest.jobs = jobs(taskIndices);
    manifest.created_at = char(datetime('now', 'TimeZone', 'local', ...
        'Format', 'yyyy-MM-dd HH:mm:ss Z'));
    manifestPath = fullfile(settings.work_dir, ...
        worker_manifest_name(i, retryIndex));
    save(manifestPath, 'manifest', '-v7.3');

    workerJobs(i).worker_index = i;
    workerJobs(i).manifest_path = manifestPath;
    workerJobs(i).log_path = fullfile(settings.work_dir, ...
        worker_log_name(i, retryIndex));
    workerJobs(i).status = 'prepared';
    workerJobs(i).task_indices = taskIndices;
end
end

function name = worker_manifest_name(workerIndex, retryIndex)
if retryIndex == 0
    name = sprintf('worker_%02d_manifest.mat', workerIndex);
else
    name = sprintf('retry_%02d_worker_%02d_manifest.mat', retryIndex, workerIndex);
end
end

function name = worker_log_name(workerIndex, retryIndex)
if retryIndex == 0
    name = sprintf('worker_%02d.log', workerIndex);
else
    name = sprintf('retry_%02d_worker_%02d.log', retryIndex, workerIndex);
end
end

function chunks = split_indices(taskCount, workerCount)
chunks = cell(workerCount, 1);
for i = 1:workerCount
    chunks{i} = zeros(0, 1);
end
for i = 1:taskCount
    workerIndex = mod(i - 1, workerCount) + 1;
    chunks{workerIndex}(end+1, 1) = i;
end
end

function results = dry_run_results(tasks, jobs, workerJobs)
resultCells = cell(numel(tasks), 1);
for i = 1:numel(tasks)
    result = tasks(i);
    result.status = 'dry_run';
    result.completed_at = '';
    result.process_payload = jobs(i).payload_path;
    result.process_result = jobs(i).result_path;
    result.process_log = jobs(i).log_path;
    result.process_worker = matching_worker_index(workerJobs, i);
    result.pid = 'dry-run';
    resultCells{i} = result;
end
results = vertcat(resultCells{:});
end

function workerIndex = matching_worker_index(workerJobs, taskIndex)
workerIndex = NaN;
for i = 1:numel(workerJobs)
    if any(workerJobs(i).task_indices == taskIndex)
        workerIndex = workerJobs(i).worker_index;
        return;
    end
end
end

function workerJobs = launch_workers(workerJobs, settings)
for i = 1:numel(workerJobs)
    batchExpr = sprintf('cd(%s); addpath(genpath(pwd)); mh_vta_compute_task_worker(%s)', ...
        mh_vta_matlab_string_literal(settings.repo_dir), ...
        mh_vta_matlab_string_literal(workerJobs(i).manifest_path));
    innerCmd = mh_vta_matlab_batch_command(settings.matlab_exe, batchExpr, ...
        settings.conda_env);
    cmd = sprintf('/bin/zsh -lc %s > %s 2>&1 & echo $!', ...
        mh_fiber_shell_quote(innerCmd), ...
        mh_fiber_shell_quote(workerJobs(i).log_path));
    [status, output] = system(cmd);
    if status ~= 0
        error('mh_vta_run_compute_tasks_process:LaunchFailed', ...
            'Could not launch VTA task worker %d: %s', i, output);
    end
    workerJobs(i).pid = strtrim(string(output));
    workerJobs(i).status = 'running';
    workerJobs(i).inner_command = innerCmd;
    workerJobs(i).launch_command = cmd;
end
end

function [complete, missingJobs] = wait_for_results(jobs, workerJobs, settings)
timer = tic;
complete = false;
missingJobs = jobs([]);
while true
    done = all(arrayfun(@(job) isfile(job.result_path), jobs));
    if done
        complete = true;
        return;
    end

    for i = 1:numel(workerJobs)
        workerDone = all(arrayfun(@(job) isfile(job.result_path), ...
            jobs(workerJobs(i).task_indices)));
        if ~workerDone && ~process_alive(workerJobs(i).pid)
            missingJobs = jobs(~arrayfun(@(job) isfile(job.result_path), jobs));
            return;
        end
    end

    if settings.timeout_seconds > 0 && toc(timer) > settings.timeout_seconds
        error('mh_vta_run_compute_tasks_process:Timeout', ...
            'Timed out waiting for VTA task worker results after %.1f seconds.', ...
            settings.timeout_seconds);
    end
    pause(settings.poll_seconds);
end
end

function alive = process_alive(pid)
pidText = strtrim(char(string(pid)));
if isempty(pidText) || strcmp(pidText, 'dry-run')
    alive = false;
    return;
end
[status, ~] = system(sprintf('kill -0 %s >/dev/null 2>&1', ...
    mh_fiber_shell_quote(pidText)));
alive = status == 0;
end

function results = load_results(jobs)
resultCells = cell(numel(jobs), 1);
failed = strings(numel(jobs), 1);
failedCount = 0;
for i = 1:numel(jobs)
    data = load(jobs(i).result_path, 'result', 'workerStatus', 'errorReport');
    result = data.result;
    result.process_payload = jobs(i).payload_path;
    result.process_result = jobs(i).result_path;
    result.process_log = jobs(i).log_path;
    if ~strcmp(data.workerStatus, 'complete')
        failedCount = failedCount + 1;
        failed(failedCount, 1) = string(data.errorReport.message);
    end
    resultCells{i} = result;
end

if failedCount > 0
    failed = failed(1:failedCount);
error('mh_vta_run_compute_tasks_process:TaskFailed', ...
    'One or more VTA process tasks failed: %s', char(strjoin(failed, ' | ')));
end
results = vertcat(resultCells{:});
end
