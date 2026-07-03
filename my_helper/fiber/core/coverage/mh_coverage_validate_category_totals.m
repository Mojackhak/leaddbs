function mh_coverage_validate_category_totals(tableIn, groupVars, expectedRows, varargin)
% Validate category row counts and voxel sums within each coverage group.

parser = inputParser;
parser.FunctionName = 'mh_coverage_validate_category_totals';
parser.addParameter('VoxelColumn', 'voxel_count', @(x) ischar(x) || isstring(x));
parser.addParameter('TotalVoxelColumn', 'total_vta_voxels', @(x) ischar(x) || isstring(x));
parser.addParameter('Tolerance', 0, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('CountErrorId', 'mh_coverage_validate_category_totals:UnexpectedRowCount', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('CountMessage', 'Unexpected category row count for %s.', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('SumErrorId', 'mh_coverage_validate_category_totals:VoxelSumMismatch', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('SumMessage', 'Category voxel count does not equal total VTA voxel count.', ...
    @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

groupVars = cellstr(string(groupVars));
voxelColumn = char(string(opts.VoxelColumn));
totalVoxelColumn = char(string(opts.TotalVoxelColumn));
assert_table_columns(tableIn, [groupVars, {voxelColumn, totalVoxelColumn}]);

if isempty(groupVars)
    G = ones(height(tableIn), 1);
    keyTable = table();
else
    [G, keyTable] = findgroups(tableIn(:, groupVars));
end

for g = 1:max_group(G)
    one = tableIn(G == g, :);
    groupValues = group_value_args(keyTable, groupVars, g);
    if height(one) ~= expectedRows
        error(char(string(opts.CountErrorId)), char(string(opts.CountMessage)), groupValues{:});
    end
    totalVoxels = one.(totalVoxelColumn);
    if abs(sum(one.(voxelColumn)) - totalVoxels(1)) > double(opts.Tolerance)
        error(char(string(opts.SumErrorId)), char(string(opts.SumMessage)), groupValues{:});
    end
end
end

function nGroups = max_group(G)
if isempty(G)
    nGroups = 0;
else
    nGroups = max(G);
end
end

function values = group_value_args(keyTable, groupVars, rowIndex)
if isempty(groupVars)
    values = {'all'};
    return;
end
values = cell(1, numel(groupVars));
for i = 1:numel(groupVars)
    column = keyTable.(groupVars{i});
    value = column(rowIndex);
    if iscell(value)
        value = value{1};
    end
    if isstring(value) || iscategorical(value)
        values{i} = char(string(value));
    else
        values{i} = value;
    end
end
end

function assert_table_columns(tableIn, requiredVars)
missing = setdiff(requiredVars, tableIn.Properties.VariableNames, 'stable');
if ~isempty(missing)
    error('mh_coverage_validate_category_totals:MissingColumn', ...
        'Coverage table is missing required column: %s', strjoin(missing, ', '));
end
end
