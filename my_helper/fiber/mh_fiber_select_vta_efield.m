function stats = mh_fiber_select_vta_efield(ftr, binaryVtaPath, efieldPath, thresholdVPerM)
% Select VTA-hit fibers and record peak e-field at VTA-intersecting voxels.

if nargin < 4 || isempty(thresholdVPerM)
    thresholdVPerM = 200;
end

binaryVta = ea_load_nii(binaryVtaPath);
efield = ea_load_nii(efieldPath);

if ~isequal(size(binaryVta.img), size(efield.img))
    error('mh_fiber_select_vta_efield:GridMismatch', ...
        'Binary VTA and e-field images have different dimensions.');
end

[selectedIds, perFiberVoxelInd] = mh_fiber_select_by_mask(ftr, binaryVta);
vtaInd = find(binaryVta.img(:) ~= 0);

peaks = zeros(numel(selectedIds), 1);
for i = 1:numel(selectedIds)
    sourceIdx = find(perFiberVoxelInd.fiber_ids == selectedIds(i), 1);
    vox = perFiberVoxelInd.voxels{sourceIdx};
    hitVox = intersect(vox(:), vtaInd);
    if isempty(hitVox)
        peaks(i) = 0;
    else
        peaks(i) = max(abs(double(efield.img(hitVox))));
    end
end

stats = struct();
stats.fiber_ids = selectedIds(:);
stats.efield_peak_v_per_m = peaks(:);
stats.peak_ge_threshold = peaks(:) >= thresholdVPerM;
stats.threshold_v_per_m = thresholdVPerM;
stats.vta_voxel_count = numel(vtaInd);
stats.vta_volume_mm3 = read_vta_volume(binaryVta, binaryVtaPath);

end

function volume = read_vta_volume(binaryVta, binaryVtaPath)
[stimDir, name] = fileparts(binaryVtaPath);
matPath = fullfile(stimDir, [name, '.mat']);
if isfile(matPath)
    data = load(matPath, 'vatvolume');
    if isfield(data, 'vatvolume')
        volume = data.vatvolume;
        return;
    end
end

voxelVolume = abs(det(binaryVta.mat(1:3, 1:3)));
volume = nnz(binaryVta.img) * voxelVolume;
end
