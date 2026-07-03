function values = mh_coverage_sample_scalar_to_grid(sourcePath, ref)
% Sample a scalar NIfTI image onto a reference grid with nearest neighbors.

source = ea_load_nii(sourcePath);
values = nan(ref.dim);
sourceImg = double(source.img);
sourceSize = size(sourceImg);
total = prod(ref.dim);
chunkSize = 250000;

for startIdx = 1:chunkSize:total
    stopIdx = min(total, startIdx + chunkSize - 1);
    idx = (startIdx:stopIdx)';
    [x, y, z] = ind2sub(ref.dim, idx);
    xyzMm = ea_vox2mm([x, y, z], ref.mat);
    srcVox = round(ea_mm2vox(xyzMm, source.mat));
    inside = srcVox(:, 1) >= 1 & srcVox(:, 1) <= sourceSize(1) & ...
        srcVox(:, 2) >= 1 & srcVox(:, 2) <= sourceSize(2) & ...
        srcVox(:, 3) >= 1 & srcVox(:, 3) <= sourceSize(3);
    if any(inside)
        lin = sub2ind(sourceSize, srcVox(inside, 1), srcVox(inside, 2), srcVox(inside, 3));
        idxInside = idx(inside);
        values(idxInside) = sourceImg(lin);
    end
end
end
