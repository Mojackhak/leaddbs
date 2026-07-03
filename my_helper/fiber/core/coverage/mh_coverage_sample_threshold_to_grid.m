function mask = mh_coverage_sample_threshold_to_grid(sourcePath, ref, threshold)
% Threshold an e-field image after sampling it onto the reference grid.

source = ea_load_nii(sourcePath);
mask = mh_coverage_sample_image_to_grid(source, ref, threshold, 'threshold');
end
