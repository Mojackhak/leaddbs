function status = mh_vta_execute_canonical_task(task, varargin)
% Dispatch one validated canonical task to FEM or derived execution.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('SolveFunction', @default_solve, ...
    @(value) isa(value, 'function_handle'));
parser.addParameter('DerivedFunction', @mh_vta_derive_canonical_group_peak, ...
    @(value) isa(value, 'function_handle'));
parser.addParameter('EventEmitter', [], ...
    @(value) isempty(value) || isa(value, 'function_handle'));
parser.parse(varargin{:});

if strcmp(task.kind, 'alternating_group_peak')
    if isequal(parser.Results.DerivedFunction, ...
            @mh_vta_derive_canonical_group_peak)
        status = default_derived(task, parser.Results.EventEmitter);
    else
        status = parser.Results.DerivedFunction(task);
    end
else
    if isequal(parser.Results.SolveFunction, @default_solve)
        status = default_solve(task, parser.Results.EventEmitter);
    else
        status = parser.Results.SolveFunction(task);
    end
end
end

function status = default_solve(task, eventEmitter)
status = mh_vta_backend_simbio_onesolve_canonical(task, ...
    'EventEmitter', eventEmitter, 'TaskId', task.task_id);
end

function status = default_derived(task, eventEmitter)
status = mh_vta_derive_canonical_group_peak(task, ...
    'EventEmitter', eventEmitter, 'TaskId', task.task_id);
end
