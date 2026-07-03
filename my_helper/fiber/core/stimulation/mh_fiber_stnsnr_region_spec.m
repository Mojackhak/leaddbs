function regionSpec = mh_fiber_stnsnr_region_spec(atlasDir)
% Build the project-injected STN/SNr classification atlas specification.

regionSpec = mh_coverage_region_spec_from_hemi_atlas(atlasDir, {'STN', 'SNr'});
regionSpec.project = 'STNSNr';
regionSpec.description = 'Project-injected STN/SNr classification atlas specification.';
end
