function mh_vta_compute_task_worker(manifestPath)
% Execute serialized VTA compute tasks inside an isolated MATLAB process.

manifestPath = char(string(manifestPath));
data = load(manifestPath, 'manifest');
manifest = data.manifest;
jobs = manifest.jobs;
failureCount = 0;

for i = 1:numel(jobs)
    workerStatus = run_one_job(jobs(i), manifestPath);
    if ~strcmp(workerStatus, 'complete')
        failureCount = failureCount + 1;
    end
end

if failureCount > 0
    error('mh_vta_compute_task_worker:TaskFailed', ...
        '%d serialized VTA task(s) failed. See per-task result files.', failureCount);
end
end

function workerStatus = run_one_job(job, manifestPath)
payloadPath = char(string(job.payload_path));
resultPath = char(string(job.result_path));
payload = struct();

try
    payloadData = load(payloadPath, 'payload');
    payload = payloadData.payload;
    result = mh_vta_run_compute_task(payload.cfg, payload.S, ...
        payload.options, payload.task);
    workerStatus = 'complete';
    errorReport = struct('identifier', '', 'message', '', 'report', '');
catch ME
    result = failed_result(payload, ME);
    workerStatus = 'error';
    errorReport = struct( ...
        'identifier', ME.identifier, ...
        'message', ME.message, ...
        'report', exception_report(ME));
end

result.process_payload = payloadPath;
result.process_result = resultPath;
result.process_worker_manifest = manifestPath;
save(resultPath, 'result', 'workerStatus', 'errorReport', '-v7.3');
end

function result = failed_result(payload, ME)
if isfield(payload, 'task')
    result = payload.task;
else
    result = struct();
end
result.status = 'error';
result.error_identifier = ME.identifier;
result.error_message = ME.message;
result.completed_at = char(datetime('now', 'TimeZone', 'local', ...
    'Format', 'yyyy-MM-dd HH:mm:ss Z'));
end

function report = exception_report(ME)
try
    report = getReport(ME, 'extended', 'hyperlinks', 'off');
catch
    report = ME.message;
end
end
