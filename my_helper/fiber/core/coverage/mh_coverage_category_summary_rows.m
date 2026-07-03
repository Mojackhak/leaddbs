function rows = mh_coverage_category_summary_rows(categories, vtaMask, voxelVolume)
% Summarize category voxel counts, volumes, and percentages.

names = categories.names;
fieldNames = categories.field_names;
totalVoxels = nnz(vtaMask);
rows = cell(numel(names), 5);
for i = 1:numel(names)
    count = nnz(categories.(fieldNames{i}));
    volume = count * voxelVolume;
    percentTotal = 100 * count / max(1, totalVoxels);
    denominator = categories.denominators(i);
    if isnan(denominator) || denominator == 0
        percentAnatomical = NaN;
    else
        percentAnatomical = 100 * count / denominator;
    end
    rows(i, :) = {names{i}, count, volume, percentTotal, percentAnatomical};
end
end
