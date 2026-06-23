function [selectedIds, perFiberVoxelInd] = mh_fiber_select_by_mask(ftr, maskNiiOrPath)
% Select original fiber IDs whose points intersect a nonzero NIfTI mask.

if ischar(maskNiiOrPath) || isstring(maskNiiOrPath)
    maskNii = ea_load_nii(char(maskNiiOrPath));
else
    maskNii = maskNiiOrPath;
end

maskInd = find(maskNii.img(:) ~= 0);
if isempty(maskInd)
    selectedIds = zeros(0, 1);
    perFiberVoxelInd = struct('fiber_ids', zeros(0, 1), 'voxels', {{}});
    return;
end

[xvox, yvox, zvox] = ind2sub(size(maskNii.img), maskInd);
maskMm = ea_vox2mm([xvox, yvox, zvox], maskNii.mat);

pointMask = all(ftr.fibers(:, 1:3) >= min(maskMm), 2) & ...
    all(ftr.fibers(:, 1:3) <= max(maskMm), 2);

if ~any(pointMask)
    selectedIds = zeros(0, 1);
    perFiberVoxelInd = struct('fiber_ids', zeros(0, 1), 'voxels', {{}});
    return;
end

trimmedFiber = ftr.fibers(pointMask, :);
[trimmedFiberInd, ~, trimmedFiberGroup] = unique(trimmedFiber(:, 4));
fibVoxInd = splitapply(@(fib) {ea_mm2uniqueVoxInd(fib, maskNii)}, trimmedFiber(:, 1:3), trimmedFiberGroup);

valid = ~cellfun(@(x) any(isnan(x)), fibVoxInd);
trimmedFiberInd = trimmedFiberInd(valid);
fibVoxInd = fibVoxInd(valid);

connected = cellfun(@(fib) any(ismember(fib, maskInd)), fibVoxInd);
selectedIds = trimmedFiberInd(connected);

perFiberVoxelInd = struct();
perFiberVoxelInd.fiber_ids = trimmedFiberInd;
perFiberVoxelInd.voxels = fibVoxInd;

end
