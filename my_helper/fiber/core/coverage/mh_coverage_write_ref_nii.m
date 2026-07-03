function mh_coverage_write_ref_nii(ref, img, outputPath, datatype, description)
% Write an image using a reference grid/template.

nii = ref.template;
nii.img = img;
nii.dim = ref.dim;
nii.mat = ref.mat;
nii.dt = [datatype, 0];
nii.n = [1, 1];
nii.descrip = description;
nii.fname = outputPath;
ea_write_nii(nii);
end
