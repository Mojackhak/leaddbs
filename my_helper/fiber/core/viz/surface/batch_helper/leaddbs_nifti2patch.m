function patch_obj = leaddbs_nifti2patch(nifti_path, cfg_nifti2patch)
%DBSLFP_LEADDBS_NIFTI2PATCH Wrapper around Lead-DBS ea_nifti2patch.
%
% patch_obj = leaddbs_nifti2patch(nifti_path, cfg_nifti2patch)
%
% Inputs:
%   nifti_path: path to .nii or .nii.gz
%   cfg_nifti2patch: struct of name-value parameters (excluding dataPath)
%
% Returns:
%   patch_obj: Lead-DBS patch object

    if ~exist('ea_nifti2patch', 'file')
        error('Lead-DBS function ea_nifti2patch not found on MATLAB path.');
    end

    args = struct2namevalue(cfg_nifti2patch);
    patch_obj = ea_nifti2patch(char(string(nifti_path)), args{:});
end
