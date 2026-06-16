function stats = mh_fiber_tck_vta_efield_stats(cfg, tckPath, binaryVtaDwi, efieldDwi)
% Compute VTA-hit and peak e-field statistics for a DWI-space TCK bundle.

thresholdVPerM = cfg.activation.efieldThresholdVPerM;
tck = mh_fiber_load_tck(tckPath, Inf, 1);
binary = ea_load_nii(binaryVtaDwi);
efield = ea_load_nii(efieldDwi);

if ~isequal(size(binary.img), size(efield.img))
    error('mh_fiber_tck_vta_efield_stats:GridMismatch', ...
        'Binary VTA and e-field images have different dimensions.');
end

binaryMask = double(binary.img) ~= 0;
efieldImg = abs(double(efield.img));
imageSize = size(binaryMask);
hit = false(tck.streamlineCount, 1);
peaks = zeros(tck.streamlineCount, 1);

for i = 1:tck.streamlineCount
    points = tck.streamlines{i};
    if isempty(points)
        continue;
    end
    vox = round(ea_mm2vox(points, binaryVtaDwi));
    inside = vox(:, 1) >= 1 & vox(:, 1) <= imageSize(1) & ...
        vox(:, 2) >= 1 & vox(:, 2) <= imageSize(2) & ...
        vox(:, 3) >= 1 & vox(:, 3) <= imageSize(3);
    if ~any(inside)
        continue;
    end
    vox = vox(inside, :);
    ind = sub2ind(imageSize, vox(:, 1), vox(:, 2), vox(:, 3));
    hitInd = ind(binaryMask(ind));
    if isempty(hitInd)
        continue;
    end
    hit(i) = true;
    peaks(i) = max(efieldImg(hitInd));
end

stats = struct();
stats.streamline_count = tck.streamlineCount;
stats.vta_hit_count = nnz(hit);
stats.efield_peak_max_v_per_m = max([0; peaks(hit)]);
stats.efield_peak_mean_v_per_m = mean(peaks(hit), 'omitnan');
if ~isfinite(stats.efield_peak_mean_v_per_m)
    stats.efield_peak_mean_v_per_m = 0;
end
stats.peak_ge_threshold_count = nnz(peaks >= thresholdVPerM);
stats.threshold_v_per_m = thresholdVPerM;
stats.hit_streamline_ids = find(hit);
stats.efield_peak_v_per_m = peaks;
stats.peak_ge_threshold = peaks >= thresholdVPerM;
end
