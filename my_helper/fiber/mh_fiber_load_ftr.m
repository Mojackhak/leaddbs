function ftr = mh_fiber_load_ftr(ftrPath)
% Load a Lead-DBS FTR file and guarantee mm coordinates plus original fiber IDs.

if ~isfile(ftrPath)
    error('mh_fiber_load_ftr:MissingFile', 'FTR file does not exist: %s', ftrPath);
end

[fibers, idx, voxmm, mat, vals] = ea_loadfibertracts(ftrPath);

if size(fibers, 2) < 3
    error('mh_fiber_load_ftr:InvalidFibers', 'Fiber matrix must have at least 3 columns: %s', ftrPath);
end

if strcmp(voxmm, 'vox')
    if isempty(mat)
        error('mh_fiber_load_ftr:MissingAffine', 'Voxel-space fibers are missing an affine matrix: %s', ftrPath);
    end
    fibers(:, 1:3) = ea_vox2mm(fibers(:, 1:3), mat);
    voxmm = 'mm';
end

if size(fibers, 2) == 3
    if sum(idx) ~= size(fibers, 1)
        error('mh_fiber_load_ftr:IdxMismatch', 'sum(idx) does not match number of fiber points: %s', ftrPath);
    end
    fibers(:, 4) = repelem((1:numel(idx))', idx);
end

ftr = struct();
ftr.path = ftrPath;
ftr.fibers = double(fibers(:, 1:4));
ftr.idx = double(idx(:));
ftr.vals = vals(:);
ftr.voxmm = voxmm;
ftr.fiberCount = numel(idx);
ftr.pointCount = size(ftr.fibers, 1);

end
