function chunks = mh_fiber_split_subjects(subjectIds, workerCount)
% Split subject IDs into round-robin worker chunks.

chunks = cell(workerCount, 1);
for i = 1:workerCount
    chunks{i} = strings(0, 1);
end

for i = 1:numel(subjectIds)
    workerIdx = mod(i - 1, workerCount) + 1;
    chunks{workerIdx}(end+1, 1) = subjectIds(i);
end
