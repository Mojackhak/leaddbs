function count = mh_coverage_category_voxel_sum(categories)
% Count voxels assigned to all dynamic coverage categories.

count = 0;
for i = 1:numel(categories.field_names)
    count = count + nnz(categories.(categories.field_names{i}));
end
end
