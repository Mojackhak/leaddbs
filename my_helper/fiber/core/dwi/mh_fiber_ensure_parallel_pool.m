function available = mh_fiber_ensure_parallel_pool(workerCount)
% Ensure a local parallel pool with at least the requested worker count.

workerCount = max(1, round(double(workerCount)));
available = false;
if exist('parpool', 'file') ~= 2 || exist('gcp', 'file') ~= 2 || ...
        ~license('test', 'Distrib_Computing_Toolbox')
    return;
end

try
    pool = gcp('nocreate');
    if isempty(pool)
        parpool('local', workerCount);
    elseif pool.NumWorkers < workerCount
        delete(pool);
        parpool('local', workerCount);
    end
    available = true;
catch
    available = false;
end
end
