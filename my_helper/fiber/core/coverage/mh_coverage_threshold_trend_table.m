function trend = mh_coverage_threshold_trend_table(tableIn, groupVars, varargin)
% Summarize mean total VTA volume by threshold and optional groups.

if nargin < 2
    groupVars = {};
end

parser = inputParser;
parser.FunctionName = 'mh_coverage_threshold_trend_table';
parser.addParameter('ThresholdColumn', 'threshold_v_per_mm', @(x) ischar(x) || isstring(x));
parser.addParameter('ValueColumn', 'total_vta_volume_mm3', @(x) ischar(x) || isstring(x));
parser.addParameter('MeanColumn', 'mean_total_vta_volume_mm3', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

groupVars = normalize_group_vars(groupVars);
thresholdColumn = char(string(opts.ThresholdColumn));
valueColumn = char(string(opts.ValueColumn));
meanColumn = char(string(opts.MeanColumn));

requiredVars = [groupVars, {thresholdColumn, valueColumn}];
assert_table_columns(tableIn, requiredVars);

totalRows = unique(tableIn(:, requiredVars), 'rows');
keyVars = [groupVars, {thresholdColumn}];
[G, keyTable] = findgroups(totalRows(:, keyVars));
meanTotal = splitapply(@(x) mean(x, 'omitnan'), totalRows.(valueColumn), G);

trend = keyTable;
trend.(meanColumn) = meanTotal;
end

function groupVars = normalize_group_vars(groupVars)
if isempty(groupVars)
    groupVars = {};
else
    groupVars = cellstr(string(groupVars));
    keep = strlength(string(groupVars)) > 0;
    groupVars = groupVars(keep);
end
end

function assert_table_columns(tableIn, requiredVars)
missing = setdiff(requiredVars, tableIn.Properties.VariableNames, 'stable');
if ~isempty(missing)
    error('mh_coverage_threshold_trend_table:MissingColumn', ...
        'Coverage table is missing required column: %s', strjoin(missing, ', '));
end
end
