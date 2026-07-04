function test_process_worker_exit_retry()
% Verify process-mode execution retries jobs whose worker exits without a result.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));

testRoot = tempname;
fakeRepoDir = fullfile(testRoot, 'fake_repo');
processWorkDir = fullfile(testRoot, 'process_tasks');
markerDir = fullfile(testRoot, 'markers');
mh_util_make_dir(fakeRepoDir);
mh_util_make_dir(processWorkDir);
mh_util_make_dir(markerDir);
cleanup = onCleanup(@() cleanup_test(testRoot));

write_fake_worker(fullfile(fakeRepoDir, 'mh_vta_compute_task_worker.m'));
setenv('STNSNR_TEST_RETRY_MARKER_DIR', markerDir);

cfg = struct();
cfg.repoDir = fakeRepoDir;
cfg.vta = struct();
cfg.vta.matlabExe = '/Applications/MATLAB_R2024b.app/bin/matlab';
cfg.vta.condaEnv = '';
cfg.vta.processWorkDir = processWorkDir;
cfg.vta.processDryRun = false;
cfg.vta.processPollSeconds = 0.5;
cfg.vta.processTimeoutSeconds = 30;

exec = struct();
exec.parallel_workers = 1;

task = struct();
task.side = 'L';
task.stim_label = 'retry_case';
task.request = struct();

results = mh_vta_run_compute_tasks_process(cfg, struct(), struct(), task, exec);

assert(numel(results) == 1, 'Retry test did not return one result.');
assert(strcmp(results.status, 'complete'), 'Retried job did not complete.');
assert(isfile(fullfile(markerDir, 'failed_once.txt')), ...
    'Fake worker did not simulate an initial missing-result exit.');
assert(isfile(fullfile(markerDir, 'completed_once.txt')), ...
    'Fake worker did not complete after retry.');
retryManifests = dir(fullfile(processWorkDir, 'retry_01_worker_*_manifest.mat'));
assert(~isempty(retryManifests), 'Missing-result retry did not create a retry worker manifest.');
end

function write_fake_worker(path)
lines = [
    "function mh_vta_compute_task_worker(manifestPath)" ...
    "markerDir = getenv('STNSNR_TEST_RETRY_MARKER_DIR');" ...
    "failMarker = fullfile(markerDir, 'failed_once.txt');" ...
    "if ~isfile(failMarker)" ...
    "    fid = fopen(failMarker, 'w'); fprintf(fid, 'failed'); fclose(fid);" ...
    "    return;" ...
    "end" ...
    "data = load(manifestPath, 'manifest');" ...
    "jobs = data.manifest.jobs;" ...
    "for i = 1:numel(jobs)" ...
    "    result = struct('status', 'complete', 'completed_at', char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd HH:mm:ss Z')));" ...
    "    workerStatus = 'complete';" ...
    "    errorReport = struct('identifier', '', 'message', '', 'report', '');" ...
    "    save(jobs(i).result_path, 'result', 'workerStatus', 'errorReport', '-v7.3');" ...
    "end" ...
    "fid = fopen(fullfile(markerDir, 'completed_once.txt'), 'w'); fprintf(fid, 'complete'); fclose(fid);" ...
    "end" ...
    ];
write_text(path, strjoin(lines, newline) + newline);
end

function write_text(path, text)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not open test file for writing: %s', path);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', char(text));
end

function cleanup_test(testRoot)
setenv('STNSNR_TEST_RETRY_MARKER_DIR', '');
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
