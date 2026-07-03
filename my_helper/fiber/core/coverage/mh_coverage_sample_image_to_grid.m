function mask = mh_coverage_sample_image_to_grid(source, ref, threshold, mode)
% Sample a source NIfTI image onto a reference grid as a logical mask.

mask = false(ref.dim);
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
        vals = sourceImg(lin);
        switch char(string(mode))
            case 'threshold'
                hit = vals >= threshold;
            case 'binary'
                hit = vals > threshold;
            otherwise
                error('mh_coverage_sample_image_to_grid:InvalidSampleMode', ...
                    'Invalid sample mode: %s', char(string(mode)));
        end
        idxInside = idx(inside);
        mask(idxInside(hit)) = true;
    end
end
end
