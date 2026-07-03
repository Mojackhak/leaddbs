function value = mh_coverage_iqr(values)
% Compute a NaN-robust interquartile range for coverage summaries.

values = values(~isnan(values));
if isempty(values)
    value = NaN;
else
    value = quantile(values, 0.75) - quantile(values, 0.25);
end
end
