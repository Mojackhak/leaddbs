function base = mh_fiber_strip_nii_ext(name)
% Strip .nii or .nii.gz from a filename or basename.

base = regexprep(char(string(name)), '\.nii(\.gz)?$', '');
end
