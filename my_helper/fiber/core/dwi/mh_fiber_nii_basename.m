function base = mh_fiber_nii_basename(path)
% Return a NIfTI filename basename without .nii or .nii.gz.

[~, name, ext] = fileparts(char(string(path)));
if strcmp(ext, '.gz')
    [~, innerName, innerExt] = fileparts(name);
    name = [innerName, innerExt];
else
    name = [name, ext];
end
base = mh_fiber_strip_nii_ext(name);
end
