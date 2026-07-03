function categoryCount = mh_coverage_region_category_count(regionSpec)
% Return the membership-partition category count for a region specification.

if ~isfield(regionSpec, 'regions') || isempty(regionSpec.regions)
    error('mh_coverage_region_category_count:MissingRegions', ...
        'regionSpec.regions is required.');
end
if isfield(regionSpec, 'categoryScheme') && ...
        ~strcmp(char(string(regionSpec.categoryScheme)), 'membership_partition')
    error('mh_coverage_region_category_count:UnsupportedCategoryScheme', ...
        'Unsupported category scheme: %s.', char(string(regionSpec.categoryScheme)));
end

categoryCount = 2 ^ numel(regionSpec.regions);
end
