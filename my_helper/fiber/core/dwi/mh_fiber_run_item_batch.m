function rows = mh_fiber_run_item_batch(itemCount, itemFn, emptyRow, varargin)
% Run independent batch items with optional subject-level parfor dispatch.

parser = inputParser;
parser.FunctionName = 'mh_fiber_run_item_batch';
parser.addRequired('itemCount', @(x) isnumeric(x) && isscalar(x) && x >= 0);
parser.addRequired('itemFn', @(x) isa(x, 'function_handle'));
parser.addRequired('emptyRow', @isstruct);
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('WorkerSetupFcn', [], @(x) isempty(x) || isa(x, 'function_handle'));
parser.addParameter('ProgressLabelFcn', [], @(x) isempty(x) || isa(x, 'function_handle'));
parser.parse(itemCount, itemFn, emptyRow, varargin{:});
opts = parser.Results;

itemCount = round(double(itemCount));
workerCount = max(1, round(double(opts.ParallelWorkers)));
useParallel = logical(opts.Parallel) && itemCount > 1 && ...
    workerCount > 1 && mh_fiber_ensure_parallel_pool(workerCount);
workerSetupFcn = opts.WorkerSetupFcn;
progressLabelFcn = opts.ProgressLabelFcn;
rows = repmat(emptyRow, itemCount, 1);

if useParallel
    parfor (i = 1:itemCount, workerCount)
        rows(i) = run_one_item(itemFn, i, false, true, workerSetupFcn);
    end
else
    for i = 1:itemCount
        emit_progress(progressLabelFcn, i, itemCount);
        useItemParallel = logical(opts.Parallel) && itemCount == 1;
        rows(i) = run_one_item(itemFn, i, useItemParallel, false, workerSetupFcn);
    end
end
end

function row = run_one_item(itemFn, itemIndex, useItemParallel, isParallelWorker, workerSetupFcn)
if isParallelWorker && ~isempty(workerSetupFcn)
    workerSetupFcn();
end
row = itemFn(itemIndex, useItemParallel, isParallelWorker);
end

function emit_progress(progressLabelFcn, itemIndex, itemCount)
if isempty(progressLabelFcn)
    return;
end
fprintf('\n[%d/%d] %s\n', itemIndex, itemCount, char(string(progressLabelFcn(itemIndex))));
end
