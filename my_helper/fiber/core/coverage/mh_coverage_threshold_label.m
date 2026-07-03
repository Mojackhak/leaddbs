function label = mh_coverage_threshold_label(value)
% Format a numeric coverage threshold for stable output filenames.

label = strrep(sprintf('%.2f', value), '.', 'p');
end
