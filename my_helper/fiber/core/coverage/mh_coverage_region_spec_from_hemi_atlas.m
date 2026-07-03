function regionSpec = mh_coverage_region_spec_from_hemi_atlas(atlasDir, regionNames)
% Build a region specification for <atlasDir>/{lh,rh}/<region>.nii.gz.

regionNames = string(regionNames);
regionSpec = struct();
regionSpec.categoryScheme = 'membership_partition';
regionSpec.atlasDir = char(string(atlasDir));
regionSpec.regions = repmat(struct('name', '', 'maskPaths', struct('L', '', 'R', '')), ...
    numel(regionNames), 1);

for i = 1:numel(regionNames)
    name = char(regionNames(i));
    regionSpec.regions(i).name = name;
    regionSpec.regions(i).maskPaths = struct( ...
        'L', fullfile(atlasDir, 'lh', [name, '.nii.gz']), ...
        'R', fullfile(atlasDir, 'rh', [name, '.nii.gz']));
end
end
