function cfg_plot_patch = default_plot_patch_config()
%DBSLFP_DEFAULT_PLOT_PATCH_CONFIG Default config for ea_plot_patch_leaddbs.
%
% Returns:
%   cfg_plot_patch: struct converted to name-value pairs for ea_plot_patch_leaddbs.
%
% Notes:
% - Excludes ViewStruct / ColorbarLabel / ExportFile which are set per job.

    fontsize     = 32;
    tickfontsize = 27;

    cfg_plot_patch = struct();
    cfg_plot_patch.FontName                = 'Arial';
    cfg_plot_patch.FontFallbackNames       = {'Arial', 'Arial Unicode MS', 'Helvetica', 'DejaVu Sans', 'Liberation Sans'};
    cfg_plot_patch.RequireSansSerifFont    = true;
    cfg_plot_patch.UseSymbolForGreek       = false;
    cfg_plot_patch.FigurePosition          = [100 100 1200 900];
    cfg_plot_patch.MissingDataMode         = 'gray';
    cfg_plot_patch.MissingDataBlendRings   = 0;
    cfg_plot_patch.PlotAxesPosition        = [0.15 0.20 0.56 0.64];
    cfg_plot_patch.SurfaceAxesPaddingFraction = 0.10;
    cfg_plot_patch.SurfaceViewPaddingScale = 1.18;
    cfg_plot_patch.SurfaceLightingProfile  = 'texture';
    cfg_plot_patch.SurfaceAmbientStrength  = 0.38;
    cfg_plot_patch.SurfaceDiffuseStrength  = 0.84;
    cfg_plot_patch.SurfaceSpecularStrength = 0.03;
    cfg_plot_patch.SurfaceSpecularExponent = 12;
    cfg_plot_patch.AddColorbar             = true;
    cfg_plot_patch.ColorbarUnits           = 'normalized';
    cfg_plot_patch.ColorbarPosition        = [0.76 0.25 0.035 0.56];
    cfg_plot_patch.ColorbarLineWidth       = 1.0;
    cfg_plot_patch.ColorbarTickColor       = [0 0 0];
    cfg_plot_patch.ColorbarLabelColor      = [0 0 0];
    cfg_plot_patch.ColorbarLabelStyle      = 'plain';
    cfg_plot_patch.ColorbarLabelInterpreter = 'none';
    cfg_plot_patch.ColorbarTickLabelInterpreter = 'none';
    cfg_plot_patch.ColorbarLabelFontSize   = fontsize;
    cfg_plot_patch.ColorbarTickFontSize    = tickfontsize;
    cfg_plot_patch.ColorbarLabelOffset     = 0.6;
    cfg_plot_patch.MarkExtrema             = false;
    cfg_plot_patch.RASTriadLocation        = [0.040 0.040 0.175 0.175];
    cfg_plot_patch.RASTriadAxesPadding     = 0.50;
    cfg_plot_patch.RASTriadFontSize        = tickfontsize;
    cfg_plot_patch.RASTriadLineWidth       = 5;
    cfg_plot_patch.RASTriadHeadSize        = 1.0;
    cfg_plot_patch.ExportResolution        = 450;
    cfg_plot_patch.ExportContentType       = 'auto';
    cfg_plot_patch.FigureVisible           = 'off';
    cfg_plot_patch.FigureBackend           = 'leaddbs';
    cfg_plot_patch.StrictHeadless          = false;
end
