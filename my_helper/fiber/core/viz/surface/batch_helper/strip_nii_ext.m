function out_base = strip_nii_ext(nifti_path)
%DBSLFP_STRIP_NII_EXT Remove .nii or .nii.gz from a path.
%
% out_base = strip_nii_ext(nifti_path)
%
% Examples:
%   '/a/b/c.nii.gz' -> '/a/b/c'
%   '/a/b/c.nii'    -> '/a/b/c'

    p = char(string(nifti_path));
    p_lower = lower(p);

    if endsWith(p_lower, '.nii.gz')
        out_base = p(1:end-7);
    elseif endsWith(p_lower, '.nii')
        out_base = p(1:end-4);
    else
        out_base = p;
    end
end
