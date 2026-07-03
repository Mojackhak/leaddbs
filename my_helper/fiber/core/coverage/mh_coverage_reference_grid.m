function ref = mh_coverage_reference_grid(efieldPaths, voxelSize, varargin)
% Build a shared output grid covering one or more e-field images.

parser = inputParser;
parser.FunctionName = 'mh_coverage_reference_grid';
parser.addParameter('MaxVoxels', 12000000, @(x) isnumeric(x) && isscalar(x) && x > 0);
parser.addParameter('ErrorId', 'mh_coverage_reference_grid:ReferenceGridTooLarge', ...
    @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

efieldPaths = cellstr(string(efieldPaths));
if isempty(efieldPaths)
    error('mh_coverage_reference_grid:MissingInputs', ...
        'At least one e-field path is required.');
end

allCorners = zeros(0, 3);
template = ea_load_nii(efieldPaths{1});
for i = 1:numel(efieldPaths)
    nii = ea_load_nii(efieldPaths{i});
    dim = size(nii.img);
    corners = [ ...
        1, 1, 1; dim(1), 1, 1; 1, dim(2), 1; 1, 1, dim(3); ...
        dim(1), dim(2), 1; dim(1), 1, dim(3); 1, dim(2), dim(3); dim(1), dim(2), dim(3)];
    allCorners = [allCorners; ea_vox2mm(corners, nii.mat)]; %#ok<AGROW>
end

minMm = floor(min(allCorners, [], 1) ./ voxelSize) .* voxelSize - voxelSize;
maxMm = ceil(max(allCorners, [], 1) ./ voxelSize) .* voxelSize + voxelSize;
dim = max(1, ceil((maxMm - minMm) ./ voxelSize) + 1);
if prod(dim) > opts.MaxVoxels
    error(char(opts.ErrorId), 'Reference grid is too large: %s voxels.', mat2str(dim));
end

mat = [voxelSize, 0, 0, minMm(1); 0, voxelSize, 0, minMm(2); ...
    0, 0, voxelSize, minMm(3); 0, 0, 0, 1];
ref = struct();
ref.dim = dim;
ref.mat = mat;
ref.template = template;
ref.voxel_size_mm = voxelSize;
ref.voxel_volume_mm3 = abs(det(mat(1:3, 1:3)));
end
