function task = mh_vta_validate_canonical_task(task)
% Validate one canonical task definition and its resolved runtime context.

task = mh_vta_validate_canonical_task_definition(task);
task = mh_vta_validate_canonical_task_runtime(task);
end
