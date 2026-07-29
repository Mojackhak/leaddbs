function cfg_nifti2patch = default_nifti2patch_config()
%DBSLFP_DEFAULT_NIFTI2PATCH_CONFIG Default config for ea_nifti2patch.
%
% Returns:
%   cfg_nifti2patch: struct converted to name-value pairs for ea_nifti2patch.
%
% Notes:
% - These are defaults copied from the original monolithic script.
% - The caller can override fields as needed.

    cfg_nifti2patch = struct();
    cfg_nifti2patch.TemplateNifti              = [];
    cfg_nifti2patch.SurfaceMode                = 'mask';
    cfg_nifti2patch.MaskThreshold              = -9999;
    cfg_nifti2patch.MaskIsovalue               = 0.5;
    cfg_nifti2patch.VolumeSmoothingSigmaMm     = 0.0;
    cfg_nifti2patch.SurfaceSmoothingIters      = 20;
    cfg_nifti2patch.SurfaceSmoothingMethod     = 'taubin';
    cfg_nifti2patch.SurfaceSmoothingLambda     = 0.5;
    cfg_nifti2patch.SurfaceSmoothingMu         = -0.1;
    cfg_nifti2patch.Alpha                      = 1.0;
    cfg_nifti2patch.Colormap                   = 'vik';
    cfg_nifti2patch.CLimMode                   = 'symmetric';
    cfg_nifti2patch.GeometryUpsampleFactor     = 1;
    cfg_nifti2patch.ColorSampling              = 'insideOnly';
    cfg_nifti2patch.SampleDepthMm              = 1.0;
    cfg_nifti2patch.ReduceFactor               = 1;
end
