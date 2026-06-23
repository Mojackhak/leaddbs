function out = mh_fiber_subset_ftr(ftr, selectedIds, metadata)
% Create a Lead-DBS-loadable FTR subset while preserving original fiber IDs as metadata.

if nargin < 3
    metadata = struct();
end

selectedIds = unique(double(selectedIds(:)), 'stable');
selectedIds = selectedIds(selectedIds >= 1 & selectedIds <= ftr.fiberCount);

out = struct();
out.ea_fibformat = '1.1';
out.fourindex = 1;
out.voxmm = 'mm';
out.source_ftr = ftr.path;
out.original_fiber_ids = selectedIds;

if isempty(selectedIds)
    out.fibers = zeros(0, 4);
    out.idx = zeros(0, 1);
    out.vals = zeros(0, 1);
else
    pointMask = ismember(ftr.fibers(:, 4), selectedIds);
    oldPointIds = ftr.fibers(pointMask, 4);
    [~, newPointIds] = ismember(oldPointIds, selectedIds);
    out.fibers = [ftr.fibers(pointMask, 1:3), newPointIds];
    out.idx = accumarray(newPointIds, 1, [numel(selectedIds), 1]);
    out.vals = ones(numel(selectedIds), 1);
end

metaFields = fieldnames(metadata);
for i = 1:numel(metaFields)
    out.(metaFields{i}) = metadata.(metaFields{i});
end

end
