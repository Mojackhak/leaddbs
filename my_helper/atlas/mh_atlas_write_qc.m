function qc = mh_atlas_write_qc(spec, records)
% Compute and write ROI mask QC metrics.

if isempty(records)
    error('mh_atlas_write_qc:NoRecords', 'No records to QC.');
end

refInfo = niftiinfo(spec.reference_image);
qc = struct([]);

for i = 1:numel(records)
    rec = records(i);
    info = niftiinfo(rec.output_file);
    data = niftiread(info);
    mask = data > 0;
    voxelCount = nnz(mask);
    voxelVolume = prod(double(info.PixelDimensions(1:3)));
    [centroidX, centroidY, centroidZ] = mask_centroid(mask, info);

    item = struct();
    item.atlas_name = rec.atlas_name;
    item.roi_name = rec.roi_name;
    item.side = rec.side;
    item.role = rec.role;
    item.category = rec.category;
    item.output_file = rec.output_file;
    item.voxel_count = voxelCount;
    item.volume_mm3 = voxelCount * voxelVolume;
    item.centroid_x = centroidX;
    item.centroid_y = centroidY;
    item.centroid_z = centroidZ;
    item.empty_mask = voxelCount == 0;
    item.grid_match = grids_match(info, refInfo);
    item.side_ok = side_check(rec.side, centroidX, item.empty_mask);
    qc = append_item(qc, item); %#ok<AGROW>
end

tbl = struct2table(qc);
writetable(tbl, fullfile(spec.output_dir, 'roi_qc.csv'));
end

function qc = append_item(qc, item)
if isempty(qc)
    qc = item;
else
    qc(end+1) = item;
end
end

function [x, y, z] = mask_centroid(mask, info)
idx = find(mask);
if isempty(idx)
    x = NaN;
    y = NaN;
    z = NaN;
    return;
end
[i, j, k] = ind2sub(size(mask), idx);
T = info.Transform.T;
coords = [double(i(:))-1, double(j(:))-1, double(k(:))-1, ones(numel(i), 1)] * T;
x = mean(coords(:, 1));
y = mean(coords(:, 2));
z = mean(coords(:, 3));
end

function tf = grids_match(info, refInfo)
sameSize = isequal(info.ImageSize, refInfo.ImageSize);
samePix = max(abs(double(info.PixelDimensions(1:3)) - double(refInfo.PixelDimensions(1:3)))) < 1e-6;
sameTransform = max(abs(info.Transform.T(:) - refInfo.Transform.T(:))) < 1e-6;
tf = sameSize && samePix && sameTransform;
end

function tf = side_check(side, centroidX, emptyMask)
if emptyMask || isnan(centroidX)
    tf = false;
    return;
end
switch upper(char(string(side)))
    case 'L'
        tf = centroidX < 0;
    case 'R'
        tf = centroidX > 0;
    otherwise
        tf = false;
end
end
