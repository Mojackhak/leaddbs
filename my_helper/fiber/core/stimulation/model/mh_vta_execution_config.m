function exec = mh_vta_execution_config(cfg, taskCount)
% Resolve VTA task execution mode and worker count.

if nargin < 2 || isempty(taskCount)
    taskCount = 1;
end

defaults = mh_vta_default_execution_options();
exec = struct();
exec.requested_mode = get_vta_option(cfg, 'executionMode', defaults.executionMode);
exec.mode = lower(char(string(exec.requested_mode)));
exec.parallel = logical(get_vta_option(cfg, 'parallel', defaults.parallel));
exec.parallel_workers = max(1, round(double(get_vta_option(cfg, ...
    'parallelWorkers', defaults.parallelWorkers))));
exec.task_count = max(0, double(taskCount));

if exec.task_count <= 1 && ~strcmp(exec.mode, 'process')
    exec.mode = 'sequential';
    exec.parallel = false;
    exec.parallel_workers = 1;
    exec.reason = 'single_task';
    return;
end

switch exec.mode
    case 'sequential'
        exec.parallel = false;
        exec.parallel_workers = 1;
        exec.reason = 'sequential_mode';
    case 'parpool'
        exec.parallel = true;
        exec.parallel_workers = min(exec.parallel_workers, exec.task_count);
        [available, reason] = parallel_available(exec.parallel_workers);
        if ~available
            warning('mh_vta_execution_config:ParallelUnavailable', ...
                'Parallel execution requested but unavailable (%s). Falling back to sequential.', reason);
            exec.mode = 'sequential';
            exec.parallel = false;
            exec.parallel_workers = 1;
            exec.reason = reason;
        else
            exec.reason = 'parpool';
        end
    case 'process'
        exec.parallel = true;
        exec.parallel_workers = min(exec.parallel_workers, max(1, exec.task_count));
        exec.reason = 'process';
    otherwise
        error('mh_vta_execution_config:UnsupportedMode', ...
            'Unsupported VTA execution mode: %s', exec.mode);
end
end

function value = get_vta_option(cfg, fieldName, fallback)
if isfield(cfg, 'vta') && isfield(cfg.vta, fieldName)
    value = cfg.vta.(fieldName);
else
    value = fallback;
end
end

function [available, reason] = parallel_available(workerCount)
available = false;
if exist('parpool', 'file') ~= 2 || exist('gcp', 'file') ~= 2 || ...
        ~license('test', 'Distrib_Computing_Toolbox')
    reason = 'Parallel Computing Toolbox not available';
    return;
end

pool = gcp('nocreate');
if isempty(pool)
    parpool('local', workerCount);
end
available = true;
reason = 'available';
end
