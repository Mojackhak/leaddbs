function volume = mh_vta_read_vat_volume(matPath)
% Read Lead-DBS vatvolume from a binary VTA MAT file.

if ~isfile(matPath)
    volume = NaN;
    return;
end
data = load(matPath, 'vatvolume');
if isfield(data, 'vatvolume')
    volume = data.vatvolume;
else
    volume = NaN;
end
end
