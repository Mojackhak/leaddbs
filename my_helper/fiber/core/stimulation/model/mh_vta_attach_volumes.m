function vta = mh_vta_attach_volumes(vta)
% Attach native VTA volume fields when binary MAT files are available.

vta.volume = struct();
for sideCell = {'R', 'L'}
    side = sideCell{1};
    if isfield(vta, 'native') && isfield(vta.native, side) && ...
            isfield(vta.native.(side), 'binaryMat')
        vta.volume.(side) = mh_vta_read_vat_volume(vta.native.(side).binaryMat);
    else
        vta.volume.(side) = NaN;
    end
end
end
