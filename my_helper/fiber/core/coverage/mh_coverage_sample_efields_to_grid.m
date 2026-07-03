function sampledEfields = mh_coverage_sample_efields_to_grid(efieldPaths, ref)
% Sample a list of scalar e-field NIfTIs onto one reference grid.

efieldPaths = cellstr(string(efieldPaths));
sampledEfields = cell(numel(efieldPaths), 1);
for i = 1:numel(efieldPaths)
    sampledEfields{i} = mh_coverage_sample_scalar_to_grid(efieldPaths{i}, ref);
end
end
