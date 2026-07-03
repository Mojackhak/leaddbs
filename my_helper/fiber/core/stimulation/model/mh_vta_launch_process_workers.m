function jobs = mh_vta_launch_process_workers(subjectIds, workerScript, logDir, varargin)
% Launch process-isolated MATLAB workers for subject chunks.

parser = inputParser;
parser.FunctionName = 'mh_vta_launch_process_workers';
parser.addParameter('WorkerCount', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('MatlabExe', '/Applications/MATLAB_R2024b.app/bin/matlab', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('CondaEnv', 'leaddbs', @(x) ischar(x) || isstring(x));
parser.addParameter('Env', struct(), @isstruct);
parser.parse(varargin{:});
opts = parser.Results;

subjectIds = string(subjectIds(:));
if isempty(subjectIds)
    error('mh_vta_launch_process_workers:NoSubjects', ...
        'At least one subject ID is required.');
end
mh_util_must_be_file(workerScript, 'MATLAB worker script', ...
    'mh_vta_launch_process_workers:MissingWorkerScript');
mh_util_make_dir(logDir);

workerCount = max(1, min(round(double(opts.WorkerCount)), numel(subjectIds)));
chunks = mh_fiber_split_subjects(subjectIds, workerCount);
jobRows = cell(workerCount, 7);

for i = 1:workerCount
    ids = chunks{i};
    subjectList = strjoin(ids, ';');
    subjectEnvList = strjoin(ids, ',');
    logPath = fullfile(logDir, sprintf('worker_%02d.log', i));
    batchExpr = sprintf('run(%s)', mh_vta_matlab_string_literal(workerScript));
    innerCmd = mh_vta_matlab_batch_command(opts.MatlabExe, batchExpr, opts.CondaEnv);

    envValues = opts.Env;
    envValues.STNSNR_VTA_SUBJECT_IDS = subjectEnvList;
    envPrefix = env_assignments(envValues);
    cmd = sprintf('%s /bin/zsh -lc %s > %s 2>&1 & echo $!', ...
        envPrefix, mh_fiber_shell_quote(innerCmd), mh_fiber_shell_quote(logPath));

    if logical(opts.DryRun)
        pid = "dry-run";
        statusText = "dry_run";
        fprintf('Dry-run process worker %02d: %s\n', i, subjectList);
    else
        [status, output] = system(cmd);
        if status ~= 0
            error('mh_vta_launch_process_workers:LaunchFailed', ...
                'Could not launch worker %d: %s', i, output);
        end
        pid = strtrim(string(output));
        statusText = "running";
        fprintf('Launched process worker %02d PID %s: %s\n', i, pid, subjectList);
    end

    jobRows(i, :) = {i, subjectList, pid, logPath, statusText, innerCmd, cmd};
end

jobs = cell2table(jobRows, 'VariableNames', ...
    {'worker_index', 'subject_ids', 'pid', 'log_path', 'status', ...
    'inner_command', 'launch_command'});
end

function text = env_assignments(envValues)
names = fieldnames(envValues);
parts = cell(numel(names), 1);
for i = 1:numel(names)
    value = envValues.(names{i});
    if islogical(value)
        if value
            value = 'true';
        else
            value = 'false';
        end
    elseif isnumeric(value)
        value = num2str(value);
    else
        value = char(string(value));
    end
    parts{i} = sprintf('%s=%s', names{i}, mh_fiber_shell_quote(value));
end
text = ['env ', strjoin(parts, ' ')];
end
