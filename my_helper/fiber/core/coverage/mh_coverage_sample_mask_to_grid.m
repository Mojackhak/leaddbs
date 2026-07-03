function mask = mh_coverage_sample_mask_to_grid(sourcePath, ref)
% Sample an atlas mask onto the reference grid using img > 0.

source = ea_load_nii(sourcePath);
mask = mh_coverage_sample_image_to_grid(source, ref, 0, 'binary');
end
