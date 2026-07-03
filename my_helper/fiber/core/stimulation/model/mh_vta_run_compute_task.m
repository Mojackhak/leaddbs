function result = mh_vta_run_compute_task(cfg, S, options, task)
% Execute one atomic VTA compute task through the model facade.

request = task.request;
request.sides = {task.side};
vta = mh_vta_compute(cfg, S, options, request);

sideCode = task.side;
result = task;
result.status = 'complete';
result.efield_mni = vta.mni.(sideCode).efieldNii;
result.binary_mni = vta.mni.(sideCode).binaryNii;
result.efield_native = vta.native.(sideCode).efieldNii;
result.binary_native = vta.native.(sideCode).binaryNii;
result.completed_at = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd HH:mm:ss Z'));
end
