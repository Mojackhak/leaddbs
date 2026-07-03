function mh_fiber_extract_mean_b0(dwiPath, b0Path, bvals, force)
% Extract the mean b0 image from a 4D DWI using bval < 10.

if nargin < 4
    force = false;
end
if isfile(b0Path) && ~logical(force)
    return;
end

bvals = bvals(:)';
b0Idx = find(bvals < 10);
if isempty(b0Idx)
    error('mh_fiber_extract_mean_b0:MissingB0', ...
        'Cannot extract b0 because no bval < 10 was found.');
end

V = spm_vol(dwiPath);
if numel(V) ~= numel(bvals)
    error('mh_fiber_extract_mean_b0:VolumeCountMismatch', ...
        'DWI volume count (%d) does not match bval count (%d): %s', ...
        numel(V), numel(bvals), dwiPath);
end

b0 = zeros(V(1).dim, 'double');
for i = 1:numel(b0Idx)
    b0 = b0 + double(spm_read_vols(V(b0Idx(i))));
end
b0 = b0 ./ numel(b0Idx);

Vo = V(b0Idx(1));
Vo.fname = b0Path;
Vo.n = [1, 1];
Vo.dt = [16, 0];
Vo.descrip = sprintf('Mean b0 extracted from %s without header recentering', ...
    mh_fiber_nii_basename(dwiPath));
if V(1).dim(3) == 1
    write_single_slice_b0(dwiPath, b0Path, b0);
else
    spm_write_vol(Vo, b0);
end
end

function write_single_slice_b0(dwiPath, b0Path, b0)
info = niftiinfo(dwiPath);
info.ImageSize = info.ImageSize(1:3);
info.PixelDimensions = info.PixelDimensions(1:3);
info.Datatype = 'single';
info.BitsPerPixel = 32;
info.Filename = b0Path;
if isfile(b0Path)
    delete(b0Path);
end
niftiwrite(reshape(single(b0), info.ImageSize), b0Path, info, 'Compressed', false);
end
