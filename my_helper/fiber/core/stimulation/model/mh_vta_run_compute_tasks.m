function results = mh_vta_run_compute_tasks(cfg, S, options, tasks)
% Run an array of atomic VTA compute tasks using the configured execution mode.

if isempty(tasks)
    results = struct([]);
    return;
end

tasks = tasks(:);
exec = mh_vta_execution_config(cfg, numel(tasks));
resultCells = cell(numel(tasks), 1);

switch exec.mode
    case 'sequential'
        for i = 1:numel(tasks)
            resultCells{i} = mh_vta_run_compute_task(cfg, S, options, tasks(i));
        end
    case 'parpool'
        parfor i = 1:numel(tasks)
            resultCells{i} = mh_vta_run_compute_task(cfg, S, options, tasks(i));
        end
    otherwise
        error('mh_vta_run_compute_tasks:UnsupportedMode', ...
            'Unsupported VTA execution mode: %s', exec.mode);
end

results = vertcat(resultCells{:});
end
