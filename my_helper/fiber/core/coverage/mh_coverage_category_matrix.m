function [groupLabels, categoryLabels, matrix] = mh_coverage_category_matrix(groupValues, categoryValues, values)
% Build a stable group-by-category matrix from long-form coverage values.

groupValues = string(groupValues);
categoryValues = string(categoryValues);
values = double(values);

groupLabels = unique(groupValues, 'stable');
categoryLabels = unique(categoryValues, 'stable');
matrix = zeros(numel(groupLabels), numel(categoryLabels));

for g = 1:numel(groupLabels)
    for c = 1:numel(categoryLabels)
        row = groupValues == groupLabels(g) & categoryValues == categoryLabels(c);
        if any(row)
            matrix(g, c) = values(find(row, 1));
        end
    end
end
end
