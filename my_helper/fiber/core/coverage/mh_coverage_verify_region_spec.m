function mh_coverage_verify_region_spec(regionSpec, errorPrefix)
% Validate that a membership-partition region specification has masks.

if nargin < 2 || strlength(string(errorPrefix)) == 0
    errorPrefix = 'mh_coverage_verify_region_spec';
end
errorPrefix = char(string(errorPrefix));
if ~isfield(regionSpec, 'regions') || isempty(regionSpec.regions)
    error([errorPrefix, ':MissingRegions'], 'regionSpec.regions is required.');
end
if isfield(regionSpec, 'categoryScheme') && ...
        ~strcmp(char(string(regionSpec.categoryScheme)), 'membership_partition')
    error([errorPrefix, ':UnsupportedCategoryScheme'], ...
        'Unsupported category scheme: %s.', char(string(regionSpec.categoryScheme)));
end
for i = 1:numel(regionSpec.regions)
    region = regionSpec.regions(i);
    if ~isfield(region, 'name') || strlength(string(region.name)) == 0
        error([errorPrefix, ':MissingRegionName'], 'Each region requires a name.');
    end
    if ~isfield(region, 'maskPaths') || ~isfield(region.maskPaths, 'L') || ...
            ~isfield(region.maskPaths, 'R')
        error([errorPrefix, ':MissingRegionMaskPaths'], ...
            'Region %s requires L and R mask paths.', char(string(region.name)));
    end
    mh_util_must_be_file(region.maskPaths.L, ['left ', char(string(region.name)), ' atlas mask'], ...
        [errorPrefix, ':MissingFile']);
    mh_util_must_be_file(region.maskPaths.R, ['right ', char(string(region.name)), ' atlas mask'], ...
        [errorPrefix, ':MissingFile']);
end
end
