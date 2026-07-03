function result = mh_coverage_threshold_sampled_efields(sampledEfields, ref, threshold, regionMasks, varargin)
% Combine sampled e-fields at one threshold and summarize coverage categories.

parser = inputParser;
parser.FunctionName = 'mh_coverage_threshold_sampled_efields';
parser.addParameter('ErrorId', 'mh_coverage_threshold_sampled_efields:CategorySumMismatch', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('ErrorMessage', 'Category voxel sum does not equal total VTA voxel count.', ...
    @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

hitCount = zeros(ref.dim, 'uint16');
for i = 1:numel(sampledEfields)
    hitCount = hitCount + uint16(sampledEfields{i} >= threshold);
end

result = struct();
result.vta_mask = hitCount > 0;
result.overlap_mask = hitCount > 1;
result.categories = mh_coverage_classify_membership(result.vta_mask, regionMasks);
result.total_voxels = nnz(result.vta_mask);
result.total_volume_mm3 = result.total_voxels * ref.voxel_volume_mm3;
result.overlap_voxels = nnz(result.overlap_mask);
result.overlap_volume_mm3 = result.overlap_voxels * ref.voxel_volume_mm3;

categorySum = mh_coverage_category_voxel_sum(result.categories);
if categorySum ~= result.total_voxels
    error(char(string(opts.ErrorId)), char(string(opts.ErrorMessage)));
end

result.category_rows = mh_coverage_category_summary_rows( ...
    result.categories, result.vta_mask, ref.voxel_volume_mm3);
end
