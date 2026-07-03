function cfg = mh_vta_apply_execution_options(cfg, opts)
% Apply task execution options to a VTA configuration struct.

cfg.vta.executionMode = validate_execution_mode(get_option(opts, ...
    'VtaExecutionMode', cfg.vta.executionMode));
cfg.vta.parallelWorkers = max(1, round(double(get_option(opts, ...
    'VtaParallelWorkers', cfg.vta.parallelWorkers))));
cfg.vta.parallel = ~strcmp(cfg.vta.executionMode, 'sequential') && ...
    cfg.vta.parallelWorkers > 1;
cfg.vta.matlabExe = char(string(get_option(opts, ...
    'VtaMatlabExe', cfg.vta.matlabExe)));
cfg.vta.condaEnv = char(string(get_option(opts, ...
    'VtaCondaEnv', cfg.vta.condaEnv)));
cfg.vta.processWorkDir = char(string(get_option(opts, ...
    'VtaProcessWorkDir', cfg.vta.processWorkDir)));
cfg.vta.processPollSeconds = max(0.1, double(get_option(opts, ...
    'VtaProcessPollSeconds', cfg.vta.processPollSeconds)));
cfg.vta.processTimeoutSeconds = max(0, double(get_option(opts, ...
    'VtaProcessTimeoutSeconds', cfg.vta.processTimeoutSeconds)));
end

function value = get_option(opts, fieldName, fallback)
if isfield(opts, fieldName)
    value = opts.(fieldName);
else
    value = fallback;
end
end

function mode = validate_execution_mode(value)
mode = lower(char(string(value)));
if ~ismember(mode, {'sequential', 'parpool', 'process'})
    error('mh_vta_apply_execution_options:InvalidExecutionMode', ...
        'Unsupported VTA execution mode: %s', mode);
end
end
