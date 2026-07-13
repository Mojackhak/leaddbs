function status = mh_vta_execute_canonical_task(task, varargin)
% Dispatch one validated canonical task to FEM or derived execution.

parser = inputParser;
parser.FunctionName = mfilename;
parser.addParameter('SolveFunction', @default_solve, ...
    @(value) isa(value, 'function_handle'));
parser.addParameter('DerivedFunction', @mh_vta_derive_canonical_group_peak, ...
    @(value) isa(value, 'function_handle'));
parser.parse(varargin{:});

if strcmp(task.kind, 'alternating_group_peak')
    status = parser.Results.DerivedFunction(task);
else
    status = parser.Results.SolveFunction(task);
end
end

function status = default_solve(task)
status = mh_vta_backend_simbio_onesolve_canonical(task);
end
