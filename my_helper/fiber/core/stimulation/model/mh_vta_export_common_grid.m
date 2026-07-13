function mh_vta_export_common_grid(meshPointsMm, fieldValues, anchorPath, outputPath)
% Interpolate a continuous FEM E-field onto the native anchor geometry.

anchorPath = char(string(anchorPath));
outputPath = char(string(outputPath));
if ~isfile(anchorPath)
    error('mh_vta_export_common_grid:MissingAnchor', ...
        'Native anchor NIfTI does not exist: %s', anchorPath);
end
validateattributes(meshPointsMm, {'numeric'}, {'2d', 'ncols', 3, 'real'}, ...
    mfilename, 'meshPointsMm');
validateattributes(fieldValues, {'numeric'}, {'vector', 'real'}, ...
    mfilename, 'fieldValues');
fieldValues = double(fieldValues(:));
if size(meshPointsMm, 1) ~= numel(fieldValues)
    error('mh_vta_export_common_grid:SizeMismatch', ...
        'meshPointsMm rows must match the number of field values.');
end

valid = all(isfinite(meshPointsMm), 2) & isfinite(fieldValues);
if nnz(valid) < 4
    error('mh_vta_export_common_grid:InsufficientSamples', ...
        'At least four finite FEM samples are required for 3-D interpolation.');
end
points = double(meshPointsMm(valid, :));
values = fieldValues(valid);
interpolant = scatteredInterpolant( ...
    points(:, 1), points(:, 2), points(:, 3), values, 'linear', 'none');

anchor = ea_load_nii(anchorPath);
dimensions = double(anchor.dim(1:3));
sampled = nan(dimensions, 'single');
chunkSize = 250000;
for first = 1:chunkSize:prod(dimensions)
    last = min(prod(dimensions), first + chunkSize - 1);
    indices = (first:last)';
    [i, j, k] = ind2sub(dimensions, indices);
    xyzMm = ea_vox2mm([i, j, k], anchor.mat);
    sampled(indices) = single(interpolant(xyzMm(:, 1), xyzMm(:, 2), xyzMm(:, 3)));
end

output = anchor;
output.img = sampled;
output.dim = dimensions;
output.dt = [16, machine_endian_code()];
output.pinfo = [1; 0; 0];
output.descrip = 'Continuous FEM E-field on native anchor grid (V/m)';
output.fname = outputPath;
ensure_parent_directory(outputPath);
ea_write_nii(output);
end

function code = machine_endian_code()
[~, ~, endian] = computer;
code = double(endian == 'B');
end

function ensure_parent_directory(path)
parent = fileparts(path);
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
end
