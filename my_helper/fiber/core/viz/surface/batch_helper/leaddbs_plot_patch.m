function leaddbs_plot_patch(patch_obj, cfg_plot)
%DBSLFP_LEADDBS_PLOT_PATCH Wrapper around Lead-DBS ea_plot_patch_leaddbs.
%
% leaddbs_plot_patch(patch_obj, cfg_plot)
%
% Inputs:
%   patch_obj: object returned by ea_nifti2patch
%   cfg_plot: struct of name-value parameters for ea_plot_patch_leaddbs
%
% Notes:
% - This wrapper does not catch errors; the caller decides how to handle failures.

    if ~exist('ea_plot_patch_leaddbs', 'file')
        error('Lead-DBS function ea_plot_patch_leaddbs not found on MATLAB path.');
    end

    args = struct2namevalue(cfg_plot);
    ea_plot_patch_leaddbs(patch_obj, args{:});
end
