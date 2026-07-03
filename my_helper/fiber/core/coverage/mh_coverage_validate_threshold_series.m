function mh_coverage_validate_threshold_series(totalRows, groupVars, thresholds, varargin)
% Validate per-group threshold coverage completeness and monotonic VTA volumes.

parser = inputParser;
parser.FunctionName = 'mh_coverage_validate_threshold_series';
parser.addParameter('ThresholdColumn', 'threshold_v_per_mm', @(x) ischar(x) || isstring(x));
parser.addParameter('ValueColumn', 'total_vta_volume_mm3', @(x) ischar(x) || isstring(x));
parser.addParameter('Tolerance', 1e-6, @(x) isnumeric(x) && isscalar(x));
parser.addParameter('MissingErrorId', 'mh_coverage_validate_threshold_series:MissingThresholdRows', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('MissingMessage', 'Missing threshold rows for %s.', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('MonotonicErrorId', 'mh_coverage_validate_threshold_series:ThresholdMonotonicityFailed', ...
    @(x) ischar(x) || isstring(x));
parser.addParameter('MonotonicMessage', 'VTA volume is not monotonic for %s.', ...
    @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

groupVars = cellstr(string(groupVars));
thresholdColumn = char(string(opts.ThresholdColumn));
valueColumn = char(string(opts.ValueColumn));
assert_table_columns(totalRows, [groupVars, {thresholdColumn, valueColumn}]);

if isempty(groupVars)
    G = ones(height(totalRows), 1);
    keyTable = table();
else
    [G, keyTable] = findgroups(totalRows(:, groupVars));
end

for g = 1:max_group(G)
    one = sortrows(totalRows(G == g, :), thresholdColumn);
    groupValues = group_value_args(keyTable, groupVars, g);
    if height(one) ~= numel(thresholds)
        error(char(string(opts.MissingErrorId)), char(string(opts.MissingMessage)), groupValues{:});
    end
    vols = one.(valueColumn);
    if any(diff(vols) > double(opts.Tolerance))
        error(char(string(opts.MonotonicErrorId)), char(string(opts.MonotonicMessage)), groupValues{:});
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
    values{i} = char(string(column(rowIndex)));
end
end

function assert_table_columns(tableIn, requiredVars)
missing = setdiff(requiredVars, tableIn.Properties.VariableNames, 'stable');
if ~isempty(missing)
    error('mh_coverage_validate_threshold_series:MissingColumn', ...
        'Coverage table is missing required column: %s', strjoin(missing, ', '));
end
end
