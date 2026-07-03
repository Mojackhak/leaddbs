function summary = mh_coverage_category_summary_table(tableIn, groupVars, varargin)
% Summarize category coverage volumes and percentages by stable groups.

if nargin < 2
    groupVars = {};
end

parser = inputParser;
parser.FunctionName = 'mh_coverage_category_summary_table';
parser.addParameter('ThresholdColumn', 'threshold_v_per_mm', @(x) ischar(x) || isstring(x));
parser.addParameter('CategoryColumn', 'category', @(x) ischar(x) || isstring(x));
parser.addParameter('VolumeColumn', 'volume_mm3', @(x) ischar(x) || isstring(x));
parser.addParameter('PercentColumn', 'percent_total_vta', @(x) ischar(x) || isstring(x));
parser.addParameter('IncludeCounts', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('CountColumn', 'n_components', @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectColumn', 'subject_id', @(x) ischar(x) || isstring(x));
parser.addParameter('SubjectCountColumn', 'n_subjects', @(x) ischar(x) || isstring(x));
parser.addParameter('IncludeIqr', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('IncludeMinMax', false, @(x) islogical(x) || isnumeric(x));
parser.parse(varargin{:});
opts = parser.Results;

groupVars = normalize_group_vars(groupVars);
thresholdColumn = char(string(opts.ThresholdColumn));
categoryColumn = char(string(opts.CategoryColumn));
volumeColumn = char(string(opts.VolumeColumn));
percentColumn = char(string(opts.PercentColumn));
subjectColumn = char(string(opts.SubjectColumn));

includeCounts = logical(opts.IncludeCounts);
includeIqr = logical(opts.IncludeIqr);
includeMinMax = logical(opts.IncludeMinMax);

requiredVars = [groupVars, {thresholdColumn, categoryColumn, volumeColumn, percentColumn}];
if includeCounts
    requiredVars = [requiredVars, {subjectColumn}];
end
assert_table_columns(tableIn, requiredVars);

keyVars = [groupVars, {thresholdColumn, categoryColumn}];
[G, keyTable] = findgroups(tableIn(:, keyVars));

summary = keyTable;
if includeCounts
    summary.(char(string(opts.CountColumn))) = splitapply(@numel, tableIn.(volumeColumn), G);
    summary.(char(string(opts.SubjectCountColumn))) = splitapply( ...
        @(x) numel(unique(string(x))), tableIn.(subjectColumn), G);
end
summary.mean_volume_mm3 = splitapply(@(x) mean(x, 'omitnan'), tableIn.(volumeColumn), G);
summary.median_volume_mm3 = splitapply(@(x) median(x, 'omitnan'), tableIn.(volumeColumn), G);
summary.sd_volume_mm3 = splitapply(@(x) std(x, 'omitnan'), tableIn.(volumeColumn), G);
if includeIqr
    summary.iqr_volume_mm3 = splitapply(@mh_coverage_iqr, tableIn.(volumeColumn), G);
end
if includeMinMax
    summary.min_volume_mm3 = splitapply(@(x) min(x, [], 'omitnan'), tableIn.(volumeColumn), G);
    summary.max_volume_mm3 = splitapply(@(x) max(x, [], 'omitnan'), tableIn.(volumeColumn), G);
end
summary.mean_percent_total_vta = splitapply(@(x) mean(x, 'omitnan'), ...
    tableIn.(percentColumn), G);
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
    error('mh_coverage_category_summary_table:MissingColumn', ...
        'Coverage table is missing required column: %s', strjoin(missing, ', '));
end
end
