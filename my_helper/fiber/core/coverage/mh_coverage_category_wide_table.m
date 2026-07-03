function wide = mh_coverage_category_wide_table(tableIn, keyVars)
% Convert long-form category coverage rows into a volume-by-category wide table.

if nargin < 2 || isempty(keyVars)
    wideInput = tableIn;
else
    keyVars = cellstr(string(keyVars));
    requiredVars = [keyVars, {'category', 'volume_mm3'}];
    assert_table_columns(tableIn, requiredVars);
    wideInput = tableIn(:, requiredVars);
end

wide = unstack(wideInput, 'volume_mm3', 'category');
end

function assert_table_columns(tableIn, requiredVars)
missing = setdiff(requiredVars, tableIn.Properties.VariableNames, 'stable');
if ~isempty(missing)
    error('mh_coverage_category_wide_table:MissingColumn', ...
        'Coverage table is missing required column: %s', strjoin(missing, ', '));
end
end
