function regionMasks = mh_coverage_sample_region_masks(regionSpec, sideCode, ref)
% Sample all region masks for one hemisphere onto a reference grid.

sideCode = upper(char(string(sideCode)));
regionMasks = repmat(struct('name', '', 'mask', []), numel(regionSpec.regions), 1);
for i = 1:numel(regionSpec.regions)
    region = regionSpec.regions(i);
    path = region.maskPaths.(sideCode);
    mask = mh_coverage_sample_mask_to_grid(path, ref);
    if ~any(mask(:))
        error('mh_coverage_sample_region_masks:EmptyReslicedAtlasMask', ...
            'Empty %s mask after reslicing for side %s.', char(string(region.name)), sideCode);
    end
    regionMasks(i).name = char(string(region.name));
    regionMasks(i).mask = mask;
end
end
