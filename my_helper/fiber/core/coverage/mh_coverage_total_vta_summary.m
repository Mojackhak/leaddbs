function summary = mh_coverage_total_vta_summary(tableIn, groupVars, varargin)
% Summarize maximum total VTA volume by stable groups.

if nargin < 2
    groupVars = {};
end

parser = inputParser;
parser.FunctionName = 'mh_coverage_total_vta_summary';
parser.addParameter('ValueColumn', 'total_vta_volume_mm3', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputColumn', 'total_vta_volume_mm3', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

groupVars = normalize_group_vars(groupVars);
valueColumn = char(string(opts.ValueColumn));
outputColumn = char(string(opts.OutputColumn));
assert_table_columns(tableIn, [groupVars, {valueColumn}]);

if isempty(groupVars)
    total = max(tableIn.(valueColumn));
    summary = table(total, 'VariableNames', {outputColumn});
    return;
end

[G, keyTable] = findgroups(tableIn(:, groupVars));
total = splitapply(@(x) max(x), tableIn.(valueColumn), G);
summary = keyTable;
summary.(outputColumn) = total;
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
    error('mh_coverage_total_vta_summary:MissingColumn', ...
        'Coverage table is missing required column: %s', strjoin(missing, ', '));
end
end
