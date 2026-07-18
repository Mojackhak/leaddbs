function [hFig, hAx, hPatch, triad, extrema, hCb, hMissingPatch, hBlendPatch] = ea_plot_patch_leaddbs(patchObj, varargin)
%EA_PLOT_PATCH_LEADDBS Visualize a colored patch in the Lead-DBS Elvis viewer.
%
%   [hFig, hAx, hPatch] = EA_PLOT_PATCH_LEADDBS(patchObj)
%   [hFig, hAx, hPatch] = EA_PLOT_PATCH_LEADDBS(patchObj, 'Name', value, ...)
%   [hFig, hAx, hPatch, triad] = EA_PLOT_PATCH_LEADDBS(...)
%   [hFig, hAx, hPatch, triad, extrema] = EA_PLOT_PATCH_LEADDBS(...)
%   [hFig, hAx, hPatch, triad, extrema, hCb] = EA_PLOT_PATCH_LEADDBS(...)
%   [..., hMissingPatch, hBlendPatch] = EA_PLOT_PATCH_LEADDBS(...)
%
% This function:
%   1) Creates a Lead-DBS MNI viewer window using ea_mnifigure()
%   2) Plots the patch using MATLAB's patch() into that figure
%   3) Applies colormap, caxis, alpha and optional colorbar
%   4) Optionally adds an RAS orientation triad and min/max highlights
%   5) Optionally applies a predefined camera view (Lead-DBS ea_view style)
%   6) Optionally exports the current view with a transparent background
%   7) Optionally renders missing-data faces in a constant color (default: gray)
%      with optional "feathering" (smooth blending) at the boundary.
%
% Inputs
%   patchObj : struct produced by EA_NIFTI2PATCH
%
% Name-Value pairs (optional)
%   'AtlasName'    : char/string. If provided, calls ea_mnifigure(AtlasName).
%                   If empty, calls ea_mnifigure() with no arguments.
%   'Alpha'        : override transparency (0..1). Default: patchObj.alpha
%   'FaceColor'    : default 'interp'
%   'EdgeColor'    : default 'none'
%   'Lighting'     : 'gouraud' (default) or 'flat' etc.
%   'Material'     : 'dull' (default), 'shiny', ...
%   'SurfaceLightingProfile' : 'texture' (default) or 'balanced'. The
%                   texture profile uses stronger camera-relative shading;
%                   balanced keeps the flatter legacy-style lighting.
%
%   Missing-data rendering (optional)
%   'MissingDataMode'      : 'gray' (default), 'hide', or 'colormap'
%   'MissingDataFaceColor' : 1x3 RGB for missing faces. Default: [0.6 0.6 0.6]
%   'MissingDataFaceAlpha' : alpha for missing faces. Default: [] (uses Alpha)
%
%   Missing-data boundary smoothing (optional; only used when MissingDataMode='gray')
%   'MissingDataBlendRings'    : integer >= 0. Default: 2
%                                Number of vertex-adjacency rings on the DATA
%                                side to blend towards MissingDataFaceColor.
%                                Set to 0 to disable blending.
%   'MissingDataBlendStrength' : scalar in [0,1]. Default: 1
%                                Global strength multiplier for blending.
%   'MissingDataBlendGamma'    : scalar > 0. Default: 1
%                                Nonlinear exponent for the blend profile.
%                                >1 makes blending more localized to the boundary.
%
%   Camera / view (optional)
%   'ViewStruct'   : struct compatible with Lead-DBS ea_view(). If provided,
%                   the function attempts to apply it using EA_APPLY_VIEW_STRUCT.
%                   Expected fields (any subset):
%                     .az, .el, .camva, .camup, .camproj, .camtarget, .campos
%
%   Export (optional)
%   'ExportFile'        : output filename (e.g., 'scene.png'). Default: ''
%   'ExportTransparent' : logical. Export with transparent background.
%                         Default: true
%   'ExportResolution'  : scalar DPI. Default: 300
%   'ExportRenderer'    : 'opengl' (default) or 'painters'. Opengl is
%                         recommended for transparent patches.
%   'ExportContentType' : 'auto', 'vector', 'image', or 'mixed'.
%                         'mixed' rasterizes the 3D scene while keeping a
%                         vector colorbar in PDF outputs.
%   'FigureVisible'     : 'on', 'off', or ''. Empty preserves MATLAB's
%                         current default.
%   'FigurePosition'    : optional 1x4 figure position for the native
%                         MATLAB backend. Default: [].
%   'FigureBackend'     : 'leaddbs', 'matlab', or 'auto'. Strict headless
%                         batch jobs should use 'matlab' to avoid creating
%                         a Lead-DBS viewer window at all.
%   'StrictHeadless'    : logical. If true and FigureVisible='off', error
%                         if any newly created MATLAB figure remains visible.
%
%   Colorbar (optional)
%   'AddColorbar'     : logical. Default: true
%   'UseSymbolForGreek' : logical. Default: false. When true, exported
%                       colorbar text draws Greek characters with Symbol and
%                       leaves all other text in the configured base font.
%                       The default preserves the original single-font output.
%   'ColorbarLocation': e.g. 'eastoutside' (default), 'southoutside', ...
%   'ColorbarUnits'   : 'normalized' (default) or 'pixels'
%   'ColorbarPosition': 1x4 [x y w h] in ColorbarUnits. Default: []
%   'ColorbarLength'  : scalar length along the long dimension in
%                       ColorbarUnits. Default: []
%   'ColorbarWidth'   : scalar length along the short dimension in
%                       ColorbarUnits. Default: []
%
%   RAS orientation marker (optional)
%   'AddRASTriad'       : logical. Default: true
%   'RASTriadColors'    : 3x3 RGB matrix [R;A;S] or struct with fields R/A/S.
%                         Default: R=[1 0 0], A=[0 1 0], S=[0 0 1]
%   'RASTriadLocation'  : 'southwest' (default), 'southeast', 'northwest',
%                         'northeast', or a 1x4 normalized position vector.
%   'RASTriadSize'      : scalar in (0,1). Default: 0.18
%   'RASTriadPadding'   : scalar in [0,0.2). Default: 0.02
%   'RASTriadAxesPadding' : internal axes padding as a fraction of arrow
%                         length. Default: 0.45
%   'RASTriadLength'    : arrow length in triad units. Default: 1
%   'RASTriadLineWidth' : arrow line width. Default: 2
%   'RASTriadHeadSize'  : arrow head size (quiver 'MaxHeadSize'). Default: []
%   'RASTriadFontSize'  : label font size. Default: 10
%
%   Min/Max markers (optional)
%   'MarkExtrema'           : logical. Default: false
%   'MarkMin'               : logical. Default: true
%   'MarkMax'               : logical. Default: true
%   'ExtremaExcludeZero'    : logical. Exclude vertices with value==0 when
%                             searching extrema. Default: true
%   'ExtremaRadiusMm'       : scalar in mm. Default: 0.5
%   'ExtremaLightenFactor'  : scalar in [0,1]. Default: 0.8
%   'ExtremaMaxColor'       : 1x3 RGB. Default: [1 0 0]
%   'ExtremaMinColor'       : 1x3 RGB. Default: [0 0 1]
%   'ExtremaAlpha'          : scalar in [0,1]. Default: 1
%   'ExtremaFontSize'       : text label font size. Default: 10
%   'ExtremaMarkerSize'     : scatter marker size. Default: 36
%
% Outputs
%   hFig          : figure handle
%   hAx           : axes handle
%   hPatch        : patch handle(s) for the data surface (may be an array)
%                   When blending is enabled, hPatch includes both the main
%                   colormap-mapped patch and the blended truecolor patch.
%   triad         : struct returned by EA_ADD_RAS_TRIAD (if AddRASTriad=true)
%   extrema       : struct returned by EA_MARK_PATCH_EXTREMA (if MarkExtrema=true)
%   hCb           : colorbar handle (if AddColorbar=true)
%   hMissingPatch : patch handle for missing faces (if MissingDataMode='gray')
%   hBlendPatch   : patch handle for the blended boundary region (if enabled)
%
% Requirements
%   - Lead-DBS on the MATLAB path (ea_mnifigure)
%
% Notes
%   - The Lead-DBS manual notes that ea_mnifigure opens the Elvis 3D viewer
%     and you can plot additional content onto it using standard MATLAB
%     commands.

    % Default output for optional helper objects.
    triad = [];
    extrema = [];
    hCb = [];
    hMissingPatch = [];
    hBlendPatch = [];

    if ~isstruct(patchObj) || ~isfield(patchObj, 'faces') || ~isfield(patchObj, 'vertices')
        error('EA_PLOT_PATCH_LEADDBS:BadInput', ...
            'patchObj must be a struct with fields: faces, vertices (and ideally facevertexcdata).');
    end

    ip = inputParser;
    ip.FunctionName = mfilename;

    addParameter(ip, 'AtlasName', '', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'Alpha', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x >= 0 && x <= 1));
    addParameter(ip, 'FaceColor', 'interp', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'EdgeColor', 'none', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'Lighting', 'gouraud', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'Material', 'dull', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'SurfaceLightingProfile', 'texture', @(s) ischar(s) || (isstring(s) && isscalar(s)));

    % Global font (applied to axes, colorbar, and labels)
    addParameter(ip, 'FontName', 'Arial', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'FontFallbackNames', {'Arial','Arial Unicode MS','Helvetica','DejaVu Sans','Liberation Sans'}, ...
        @(x) ischar(x) || isstring(x) || iscellstr(x));
    addParameter(ip, 'RequireSansSerifFont', false, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'UseSymbolForGreek', false, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'PlotAxesPosition', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 4));
    addParameter(ip, 'SurfaceAxesPaddingFraction', 0.0, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    addParameter(ip, 'SurfaceViewPaddingScale', 1.0, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'SurfaceAmbientStrength', 0.38, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'SurfaceDiffuseStrength', 0.84, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'SurfaceSpecularStrength', 0.03, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'SurfaceSpecularExponent', 12, @(x) isnumeric(x) && isscalar(x) && x > 0);

    % Missing-data rendering (optional)
    addParameter(ip, 'MissingDataMode', 'gray', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'MissingDataFaceColor', [0.6 0.6 0.6], @(x) isnumeric(x) && numel(x) == 3);
    addParameter(ip, 'MissingDataFaceAlpha', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x >= 0 && x <= 1));

    % Missing-data boundary smoothing (optional)
    addParameter(ip, 'MissingDataBlendRings', 2, @(x) isnumeric(x) && isscalar(x) && x >= 0 && mod(x,1)==0);
    addParameter(ip, 'MissingDataBlendStrength', 1, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'MissingDataBlendGamma', 1, @(x) isnumeric(x) && isscalar(x) && x > 0);

    % Camera / view
    addParameter(ip, 'ViewStruct', [], @(x) isempty(x) || isstruct(x));

    % Export
    addParameter(ip, 'ExportFile', '', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ExportTransparent', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ExportResolution', 300, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'ExportRenderer', 'opengl', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ExportContentType', 'auto', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'FigureVisible', '', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'FigurePosition', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 4));
    addParameter(ip, 'FigureBackend', 'leaddbs', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'StrictHeadless', false, @(x) islogical(x) && isscalar(x));

    % Colorbar
    addParameter(ip, 'AddColorbar', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'LockColorbar', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ColorbarLocation', 'eastoutside', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ColorbarUnits', 'normalized', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ColorbarPosition', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 4));
    addParameter(ip, 'ColorbarLength', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'ColorbarWidth', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'ColorbarLineWidth', 1.0, @(x) isnumeric(x) && isscalar(x) && x > 0);

    addParameter(ip, 'ColorbarLabel', '', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ColorbarLabelFontSize', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'ColorbarTickFontSize', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'ColorbarTickLength', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x >= 0));
    addParameter(ip, 'ColorbarLabelColor', [0 0 0], @(x) isempty(x) || isnumeric(x) || ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(ip, 'ColorbarTickColor', [0 0 0], @(x) isempty(x) || isnumeric(x) || ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(ip, 'ColorbarLabelOffset', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    addParameter(ip, 'ColorbarLabelOffsetUnits', 'normalized', @(s) ischar(s) || (isstring(s)&&isscalar(s)));
    addParameter(ip, 'ColorbarLabelStyle', 'latex', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ColorbarLabelInterpreter', 'auto', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ColorbarTickLabelInterpreter', 'auto', @(s) ischar(s) || (isstring(s) && isscalar(s)));


    % RAS triad (orientation marker)
    addParameter(ip, 'AddRASTriad', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'RASTriadColors', [], @(x) isempty(x) || (isnumeric(x) && isequal(size(x), [3 3])) || isstruct(x));
    addParameter(ip, 'RASTriadLocation', 'southwest', @(x) (ischar(x) || (isstring(x) && isscalar(x))) || (isnumeric(x) && numel(x) == 4));
    addParameter(ip, 'RASTriadSize', 0.18, @(x) isnumeric(x) && isscalar(x) && x > 0 && x < 1);
    addParameter(ip, 'RASTriadPadding', 0.02, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x < 0.2);
    addParameter(ip, 'RASTriadAxesPadding', 0.45, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    addParameter(ip, 'RASTriadLength', 1, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'RASTriadLineWidth', 2, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'RASTriadHeadSize', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'RASTriadFontSize', 10, @(x) isnumeric(x) && isscalar(x) && x > 0);

    % Min/Max markers
    addParameter(ip, 'MarkExtrema', false, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'MarkMin', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'MarkMax', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ExtremaExcludeZero', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ExtremaRadiusMm', 0.5, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'ExtremaLightenFactor', 0.8, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'ExtremaMaxColor', [1 0 0], @(x) isnumeric(x) && numel(x) == 3);
    addParameter(ip, 'ExtremaMinColor', [0 0 1], @(x) isnumeric(x) && numel(x) == 3);
    addParameter(ip, 'ExtremaAlpha', 1, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'ExtremaFontSize', 10, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'ExtremaMarkerSize', 36, @(x) isnumeric(x) && isscalar(x) && x > 0);

    parse(ip, varargin{:});
    p = ip.Results;
    p = local_resolve_surface_lighting_profile(p);
    if p.RequireSansSerifFont
        p.FontName = local_resolve_sans_serif_font(p.FontName, p.FontFallbackNames, p.ColorbarLabel);
        local_reject_latex_interpreter(p.ColorbarLabelInterpreter, 'ColorbarLabelInterpreter');
        local_reject_latex_interpreter(p.ColorbarTickLabelInterpreter, 'ColorbarTickLabelInterpreter');
    end
    fn = char(p.FontName);
    fontCleanup = local_apply_root_font_defaults(fn); %#ok<NASGU>
    figFontArgs = {};
    axesFontArgs = {};
    if ~isempty(strtrim(fn))
        figFontArgs = {'DefaultAxesFontName', fn, 'DefaultTextFontName', fn};
        axesFontArgs = {'FontName', fn};
    end

    % Open the Lead-DBS Elvis viewer.
    atlasName = char(p.AtlasName);
    visibleMode = lower(strtrim(char(p.FigureVisible)));
    figureBackend = lower(strtrim(char(p.FigureBackend)));
    if isempty(figureBackend) || strcmp(figureBackend, 'auto')
        if p.StrictHeadless && strcmp(visibleMode, 'off')
            figureBackend = 'matlab';
        else
            figureBackend = 'leaddbs';
        end
    end

    figsBefore = findall(groot, 'Type', 'figure');
    oldDefaultVisible = [];
    visibilityCleanup = [];
    if strcmp(visibleMode, 'off')
        oldDefaultVisible = get(groot, 'DefaultFigureVisible');
        set(groot, 'DefaultFigureVisible', 'off');
        visibilityCleanup = onCleanup(@() set(groot, 'DefaultFigureVisible', oldDefaultVisible));
    end

    switch figureBackend
        case 'leaddbs'
            if exist('ea_mnifigure', 'file') ~= 2
                error('EA_PLOT_PATCH_LEADDBS:MissingLeadDBS', ...
                    'ea_mnifigure was not found. Please add Lead-DBS to the MATLAB path.');
            end
            if isempty(strtrim(atlasName))
                ea_mnifigure();
            else
                ea_mnifigure(atlasName);
            end

            hFig = gcf;
            hAx = gca;

        case 'matlab'
            figVisible = visibleMode;
            if isempty(figVisible)
                figVisible = get(groot, 'DefaultFigureVisible');
            end
            figArgs = {};
            if ~isempty(p.FigurePosition)
                figArgs = {'Units', 'pixels', 'Position', double(p.FigurePosition(:))'};
            end
            hFig = figure( ...
                'Visible', figVisible, ...
                'Color', 'white', ...
                'Renderer', char(p.ExportRenderer), ...
                'InvertHardcopy', 'off', ...
                figFontArgs{:}, ...
                figArgs{:});
            hAx = axes('Parent', hFig, ...
                'Visible', 'off', ...
                'Color', 'none', ...
                axesFontArgs{:});
            axis(hAx, 'equal');
            axis(hAx, 'vis3d');
            axis(hAx, 'off');
            view(hAx, 3);
            camproj(hAx, 'orthographic');

        otherwise
            error('EA_PLOT_PATCH_LEADDBS:BadFigureBackend', ...
                'FigureBackend must be leaddbs, matlab, or auto.');
    end

    if strcmp(visibleMode, 'off')
        newFigs = setdiff(findall(groot, 'Type', 'figure'), figsBefore);
        local_force_figures_hidden([hFig; newFigs(:)], p.StrictHeadless);
        clear visibilityCleanup;
    elseif strcmp(visibleMode, 'on')
        try, set(hFig, 'Visible', 'on'); catch, end
    end

    if ~isempty(p.PlotAxesPosition)
        try
            hAx.Units = 'normalized';
            hAx.Position = double(p.PlotAxesPosition(:))';
        catch
        end
    end
    local_enforce_surface_aspect(hAx);

    hold(hAx, 'on');

    % Apply default font (best effort).
    if ~isempty(strtrim(fn))
        try
            set(hFig, 'DefaultAxesFontName', fn, 'DefaultTextFontName', fn);
        catch
        end
        try
            set(hAx, 'FontName', fn);
        catch
        end
    end

    % Add an RAS orientation triad (inset) if requested.
    if p.AddRASTriad
        if exist('ea_add_ras_triad', 'file') == 2
            try
                triad = ea_add_ras_triad(hAx, ...
                    'Colors', p.RASTriadColors, ...
                    'Location', p.RASTriadLocation, ...
                    'Size', p.RASTriadSize, ...
                    'Padding', p.RASTriadPadding, ...
                    'AxesPadding', p.RASTriadAxesPadding, ...
                    'Length', p.RASTriadLength, ...
                    'LineWidth', p.RASTriadLineWidth, ...
                    'HeadSize', p.RASTriadHeadSize, ...
                    'FontSize', p.RASTriadFontSize, ...
                    'FontName', p.FontName);
            catch ME
                warning('EA_PLOT_PATCH_LEADDBS:RASTriadFailed', ...
                    'Failed to add RAS triad: %s', ME.message);
            end
        else
            warning('EA_PLOT_PATCH_LEADDBS:MissingRASTriad', ...
                'ea_add_ras_triad.m was not found; skipping RAS marker.');
        end
    end

    % Determine alpha.
    alphaVal = p.Alpha;
    if isempty(alphaVal)
        if isfield(patchObj, 'alpha') && ~isempty(patchObj.alpha)
            alphaVal = patchObj.alpha;
        else
            alphaVal = 0.6;
        end
    end

    % Determine CData.
    if isfield(patchObj, 'facevertexcdata')
        cdata = patchObj.facevertexcdata;
    else
        cdata = [];
    end

    % Identify faces that contain missing vertices.
    missingFaceMask = false(size(patchObj.faces, 1), 1);
    mv = [];
    if isfield(patchObj, 'missing_vertex_mask') && ~isempty(patchObj.missing_vertex_mask)
        mv = patchObj.missing_vertex_mask(:);
        if numel(mv) == size(patchObj.vertices, 1)
            missingFaceMask = any(mv(patchObj.faces), 2);
        else
            mv = [];
        end
    end

    missingMode = lower(strtrim(char(p.MissingDataMode)));
    if strcmp(missingMode, 'grey')
        missingMode = 'gray';
    end

    % Support passing a MATLAB color name directly as MissingDataMode, e.g.
    % MissingDataMode='yellow'. In that case we treat it as a solid missing
    % face color and keep the 'gray' rendering logic (with blending).
    missingFaceColor = double(p.MissingDataFaceColor(:))';
    [isColorSpec, colSpec] = local_try_parse_color_spec(p.MissingDataMode);
    knownModes = {'gray','hide','remove','colormap','keep','fill','solid','color'};
    if ~ismember(missingMode, knownModes) && isColorSpec
        missingMode = 'gray';
        missingFaceColor = colSpec;
    end

    % Main patch handles (may become an array).
    hPatchMain = [];

    switch missingMode
        case {'gray','solid','color'}
            facesValid = patchObj.faces(~missingFaceMask, :);
            facesMissing = patchObj.faces(missingFaceMask, :);

            if isempty(facesValid)
                facesValid = zeros(0, 3);
            end

            doBlend = ~isempty(mv) && any(missingFaceMask) && p.MissingDataBlendRings > 0 && p.MissingDataBlendStrength > 0;

            if doBlend
                % --- Smoothly blend DATA faces near the missing region towards the missing color ---
                N = double(p.MissingDataBlendRings);
                maxRing = N + 1;

                % Compute vertex ring-distance (in edge steps) from missing vertices.
                ring = local_vertex_ring_distance(patchObj.faces, mv, maxRing);

                % Determine which VALID faces belong to the blend band.
                minRingPerFace = min(ring(patchObj.faces), [], 2);
                nearFaceMask = (~missingFaceMask) & (minRingPerFace <= maxRing);
                farFaceMask  = (~missingFaceMask) & ~nearFaceMask;

                facesFar  = patchObj.faces(farFaceMask, :);
                facesNear = patchObj.faces(nearFaceMask, :);

                if isempty(facesFar)
                    facesFar = zeros(0, 3);
                end
                if isempty(facesNear)
                    facesNear = zeros(0, 3);
                end

                % Plot far faces using scalar colormap mapping (fast, drives the colorbar).
                hPatchFar = patch(hAx, ...
                    'Faces', facesFar, ...
                    'Vertices', patchObj.vertices, ...
                    'FaceVertexCData', cdata, ...
                    'FaceColor', char(p.FaceColor), ...
                    'EdgeColor', char(p.EdgeColor), ...
                    'FaceAlpha', alphaVal, ...
                    'CDataMapping', 'scaled');

                % Plot near faces with truecolor blending to reduce the sharp boundary.
                missColor = missingFaceColor;
                cmap = [];
                if isfield(patchObj, 'colormap') && ~isempty(patchObj.colormap)
                    cmap = patchObj.colormap;
                end
                clim = [];
                if isfield(patchObj, 'clim') && ~isempty(patchObj.clim)
                    clim = patchObj.clim;
                end

                rgbData = local_scalar_to_rgb(cdata, cmap, clim);

                w = zeros(size(ring));
                idx = (ring >= 1) & (ring <= maxRing);
                % Make boundary vertices (ring==1) match the missing color exactly.
                w(idx) = 1 - (ring(idx) - 1) / max(N, 1);
                w = max(0, min(1, w));
                w = w .^ double(p.MissingDataBlendGamma);
                w = w * double(p.MissingDataBlendStrength);
                w = max(0, min(1, w));

                rgbBlend = rgbData .* (1 - w) + missColor .* w;

                hBlendPatch = patch(hAx, ...
                    'Faces', facesNear, ...
                    'Vertices', patchObj.vertices, ...
                    'FaceVertexCData', rgbBlend, ...
                    'FaceColor', 'interp', ...
                    'EdgeColor', char(p.EdgeColor), ...
                    'FaceAlpha', alphaVal, ...
                    'HitTest', 'off');
                try
                    hBlendPatch.PickableParts = 'none';
                catch
                end

                hPatchMain = [hPatchFar; hBlendPatch];

            else
                % No blending: plot all valid faces as one colormap-mapped patch.
                hPatchMain = patch(hAx, ...
                    'Faces', facesValid, ...
                    'Vertices', patchObj.vertices, ...
                    'FaceVertexCData', cdata, ...
                    'FaceColor', char(p.FaceColor), ...
                    'EdgeColor', char(p.EdgeColor), ...
                    'FaceAlpha', alphaVal, ...
                    'CDataMapping', 'scaled');
            end

            % Plot missing faces as a constant color patch.
            if ~isempty(facesMissing)
                missAlpha = p.MissingDataFaceAlpha;
                if isempty(missAlpha)
                    missAlpha = alphaVal;
                end
                missColor = missingFaceColor;
                hMissingPatch = patch(hAx, ...
                    'Faces', facesMissing, ...
                    'Vertices', patchObj.vertices, ...
                    'FaceColor', missColor, ...
                    'EdgeColor', 'none', ...
                    'FaceAlpha', missAlpha, ...
                    'HitTest', 'off');
                try
                    hMissingPatch.PickableParts = 'none';
                catch
                end
            end

        case {'hide','remove'}
            facesValid = patchObj.faces(~missingFaceMask, :);
            if isempty(facesValid)
                facesValid = zeros(0, 3);
            end
            hPatchMain = patch(hAx, ...
                'Faces', facesValid, ...
                'Vertices', patchObj.vertices, ...
                'FaceVertexCData', cdata, ...
                'FaceColor', char(p.FaceColor), ...
                'EdgeColor', char(p.EdgeColor), ...
                'FaceAlpha', alphaVal, ...
                'CDataMapping', 'scaled');

        case {'colormap','keep','fill'}
            hPatchMain = patch(hAx, ...
                'Faces', patchObj.faces, ...
                'Vertices', patchObj.vertices, ...
                'FaceVertexCData', cdata, ...
                'FaceColor', char(p.FaceColor), ...
                'EdgeColor', char(p.EdgeColor), ...
                'FaceAlpha', alphaVal, ...
                'CDataMapping', 'scaled');

        otherwise
            warning('EA_PLOT_PATCH_LEADDBS:BadMissingMode', ...
                'Unknown MissingDataMode: %s (using ''gray'').', char(p.MissingDataMode));
            facesValid = patchObj.faces(~missingFaceMask, :);
            if isempty(facesValid)
                facesValid = zeros(0, 3);
            end
            hPatchMain = patch(hAx, ...
                'Faces', facesValid, ...
                'Vertices', patchObj.vertices, ...
                'FaceVertexCData', cdata, ...
                'FaceColor', char(p.FaceColor), ...
                'EdgeColor', char(p.EdgeColor), ...
                'FaceAlpha', alphaVal, ...
                'CDataMapping', 'scaled');
    end

    % Final patch output (may be an array).
    hPatch = hPatchMain;

    % Apply colormap and clim if available.
    if isfield(patchObj, 'colormap') && ~isempty(patchObj.colormap)
        colormap(hAx, patchObj.colormap);
        try, colormap(hFig, patchObj.colormap); catch, end
        try, setappdata(hFig, 'SurfaceColormap', patchObj.colormap); catch, end
    end
    if isfield(patchObj, 'clim') && ~isempty(patchObj.clim)
        caxis(hAx, patchObj.clim);
    end

    % Apply a predefined camera view (if requested) BEFORE extrema labels.
    if ~isempty(p.ViewStruct)
        if strcmp(figureBackend, 'matlab')
            local_apply_view_struct_native(p.ViewStruct, hAx);
        elseif exist('ea_apply_view_struct', 'file') == 2
            try
                ea_apply_view_struct(p.ViewStruct, hAx);
            catch ME
                warning('EA_PLOT_PATCH_LEADDBS:ViewStructFailed', ...
                    'Failed to apply ViewStruct: %s', ME.message);
            end
        else
            warning('EA_PLOT_PATCH_LEADDBS:MissingApplyView', ...
                'ea_apply_view_struct.m not found; cannot apply ViewStruct.');
        end
    end
    local_enforce_surface_aspect(hAx);
    local_apply_surface_axes_padding(hAx, [hPatch(:); hMissingPatch(:); hBlendPatch(:)], ...
        p.SurfaceAxesPaddingFraction);
    local_apply_surface_view_padding(hAx, p.SurfaceViewPaddingScale);

    local_apply_surface_lighting(hAx, [hPatch(:); hMissingPatch(:); hBlendPatch(:)], p);

    % Ensure the RAS triad (if present) is refreshed immediately after applying a view.
    try
        if exist('ea_refresh_ras_triad', 'file') == 2
            ea_refresh_ras_triad(hAx);
        end
    catch
    end

    % Add extrema markers (min/max) if requested.
    if p.MarkExtrema
        if exist('ea_mark_patch_extrema', 'file') == 2
            try
                extrema = ea_mark_patch_extrema(hAx, patchObj, ...
                    'MarkMin', p.MarkMin, ...
                    'MarkMax', p.MarkMax, ...
                    'ExcludeZero', p.ExtremaExcludeZero, ...
                    'RadiusMm', p.ExtremaRadiusMm, ...
                    'LightenFactor', p.ExtremaLightenFactor, ...
                    'MaxColor', p.ExtremaMaxColor, ...
                    'MinColor', p.ExtremaMinColor, ...
                    'Alpha', p.ExtremaAlpha, ...
                    'FontSize', p.ExtremaFontSize, ...
                    'FontName', p.FontName, ...
                    'MarkerSize', p.ExtremaMarkerSize);
            catch ME
                warning('EA_PLOT_PATCH_LEADDBS:ExtremaFailed', ...
                    'Failed to mark extrema: %s', ME.message);
            end
        else
            warning('EA_PLOT_PATCH_LEADDBS:MissingExtrema', ...
                'ea_mark_patch_extrema.m was not found; skipping extrema markers.');
        end
    end

    % Add and customize colorbar (optional).
    if p.AddColorbar
        try
            hCb = colorbar(hAx, 'Location', char(p.ColorbarLocation));
            try, setappdata(hCb, 'SurfaceColormap', colormap(hAx)); catch, end
            try
                hCb.Units = char(p.ColorbarUnits);
            catch
            end

            % --- Position customization ---
            if ~isempty(p.ColorbarPosition)
                try
                    hCb.Position = double(p.ColorbarPosition(:))';
                catch
                end
            elseif ~isempty(p.ColorbarLength) || ~isempty(p.ColorbarWidth)
                try
                    pos = hCb.Position;
                    ctr = [pos(1) + pos(3)/2, pos(2) + pos(4)/2];
                    isVertical = pos(4) >= pos(3);

                    if isVertical
                        if ~isempty(p.ColorbarWidth),  pos(3) = p.ColorbarWidth;  end
                        if ~isempty(p.ColorbarLength), pos(4) = p.ColorbarLength; end
                    else
                        if ~isempty(p.ColorbarLength), pos(3) = p.ColorbarLength; end
                        if ~isempty(p.ColorbarWidth),  pos(4) = p.ColorbarWidth;  end
                    end

                    pos(1) = ctr(1) - pos(3)/2;
                    pos(2) = ctr(2) - pos(4)/2;
                    hCb.Position = pos;
                catch
                end
            end

            % --- Font and label customization ---
            fn = char(p.FontName);
            if ~isempty(strtrim(fn))
                try, hCb.FontName = fn; catch, end
            end
            if ~isempty(p.ColorbarTickFontSize)
                try, hCb.FontSize = p.ColorbarTickFontSize; catch, end
            end
            if ~isempty(p.ColorbarLineWidth)
                try, hCb.LineWidth = max(1.0, double(p.ColorbarLineWidth)); catch, end
            end
            if ~isempty(p.ColorbarTickLength)
                try, hCb.TickLength = p.ColorbarTickLength; catch, end
            end
            if ~isempty(p.PlotAxesPosition)
                try
                    hAx.Units = 'normalized';
                    hAx.Position = double(p.PlotAxesPosition(:))';
                catch
                end
                local_enforce_surface_aspect(hAx);
            end

            cbLabel = char(p.ColorbarLabel);
            % --- Interpreter customization for colorbar text (tex/latex/none) ---
            if p.RequireSansSerifFont
                local_assert_plain_text_label(cbLabel);
                labelInterp = 'none';
                tickInterp = 'none';
            else
                labelInterp = local_resolve_text_interpreter(p.ColorbarLabelInterpreter, cbLabel);
                tickInterp  = local_resolve_tick_interpreter(p.ColorbarTickLabelInterpreter);
            end
            try
                if isprop(hCb, 'TickLabelInterpreter')
                    hCb.TickLabelInterpreter = tickInterp;
                end
            catch
            end

            if ~isempty(strtrim(cbLabel))
                try
                    % Grab label handle once (avoids repeated dependent-property evaluation).
                    hLbl = hCb.Label;

                    % Set interpreter FIRST to avoid syntax validation under the wrong interpreter.
                    try
                        if isprop(hLbl, 'Interpreter')
                            hLbl.Interpreter = labelInterp;
                        end
                    catch
                    end

                    % Now assign the label string.
                    hLbl.String = cbLabel;

                    % Font settings (best effort; LaTeX may ignore FontName).
                    if ~isempty(strtrim(fn))
                        try, hLbl.FontName = fn; catch, end
                    end
                    if ~isempty(p.ColorbarLabelFontSize)
                        try, hLbl.FontSize = p.ColorbarLabelFontSize; catch, end
                    end
                catch
                    % Fallback for older MATLAB versions.
                    try
                        if isempty(p.ColorbarLabelFontSize)
                            ylabel(hCb, cbLabel, 'FontName', fn, 'Interpreter', labelInterp);
                        else
                            ylabel(hCb, cbLabel, 'FontName', fn, 'FontSize', p.ColorbarLabelFontSize, 'Interpreter', labelInterp);
                        end
                    catch
                    end
                end

            end

            % --- Color customization for colorbar ticks and label ---
            % Tick color controls the colorbar axis/tick labels.
            if ~isempty(p.ColorbarTickColor)
                [tfCol, rgbCol] = local_try_parse_color_spec(p.ColorbarTickColor);
                if tfCol
                    try
                        if isprop(hCb, 'Color')
                            hCb.Color = rgbCol;
                        else
                            % Older handle-graphics fallback
                            if isprop(hCb, 'XColor'); hCb.XColor = rgbCol; end
                            if isprop(hCb, 'YColor'); hCb.YColor = rgbCol; end
                        end
                    catch
                    end
                end
            end

            % Label color can be set independently; if omitted, it follows tick color.
            if ~isempty(p.ColorbarLabelColor)
                [tfLab, rgbLab] = local_try_parse_color_spec(p.ColorbarLabelColor);
                if tfLab
                    try
                        if isprop(hCb, 'Label') && isprop(hCb.Label, 'Color')
                            hCb.Label.Color = rgbLab;
                        else
                            % Older fallback: ylabel on the colorbar axes
                            try
                                hYL = ylabel(hCb, '');
                                set(hYL, 'Color', rgbLab);
                            catch
                            end
                        end
                    catch
                    end
                end
            else
                % If user changed tick color, mirror it to label (best effort).
                try
                    if ~isempty(p.ColorbarTickColor)
                        [tfCol, rgbCol] = local_try_parse_color_spec(p.ColorbarTickColor);
                        if tfCol
                            if isprop(hCb, 'Label') && isprop(hCb.Label, 'Color')
                                hCb.Label.Color = rgbCol;
                            end
                        end
                    end
                catch
                end
            end
            % --- Lock colorbar tick/label orientation and side (prevent flipping) ---
            if p.LockColorbar
                local_fix_colorbar_pose(hCb, p);
                local_install_colorbar_lock(hAx, hCb, p); % add listeners on camera/view changes
            end
        catch ME
            warning('EA_PLOT_PATCH_LEADDBS:ColorbarFailed', ...
                'Failed to create/customize colorbar: %s', ME.message);
            hCb = [];
        end
    end
    
    % --- Adjust colorbar label distance (offset) ---
    if ~isempty(p.ColorbarLabelOffset)
        try
            % Newer MATLAB: cb.Label exists
            hLbl = hCb.Label;
        catch
            % Older MATLAB: use ylabel handle
            hLbl = ylabel(hCb, hCb.Label.String);
        end
    
        % Use requested units for consistent offset
        try
            hLbl.Units = p.ColorbarLabelOffsetUnits;
        catch
            % Some versions may not like units on label; ignore
        end
    
        pos = hLbl.Position;  % [x y z] in label units (usually normalized)
    
        % For vertical colorbars, move along x; for horizontal, move along y.
        if isprop(hCb, 'Orientation') && strcmpi(hCb.Orientation, 'vertical')
            % Eastoutside: + moves further away; Westoutside may need negative.
            pos(1) = pos(1) + p.ColorbarLabelOffset;
        else
            % Southoutside/Northoutside: + moves further away/up; may need sign flip.
            pos(2) = pos(2) + p.ColorbarLabelOffset;
        end
    
        hLbl.Position = pos;
    end
    % --- end label offset ---
        % Export if requested.
        outFile = char(p.ExportFile);
        if ~isempty(strtrim(outFile))
            if exist('ea_export_figure_transparent', 'file') == 2
                try
                    drawnow;
                    ea_export_figure_transparent(hFig, outFile, ...
                        'Transparent', p.ExportTransparent, ...
                        'Resolution', p.ExportResolution, ...
                        'Renderer', char(p.ExportRenderer), ...
                        'ContentType', char(p.ExportContentType), ...
                        'UseSymbolForGreek', p.UseSymbolForGreek);
                    local_assert_pdf_sans_serif(outFile, p);
                catch ME
                    warning('EA_PLOT_PATCH_LEADDBS:ExportFailed', ...
                        'Export failed: %s', ME.message);
                    if p.StrictHeadless || p.RequireSansSerifFont
                        rethrow(ME);
                    end
                end
            else
                warning('EA_PLOT_PATCH_LEADDBS:MissingExport', ...
                    'ea_export_figure_transparent.m not found; cannot export.');
            end
        end
    end

% -------------------------------------------------------------------------
% Helper functions
% -------------------------------------------------------------------------

function fontName = local_resolve_sans_serif_font(fontNameIn, fallbackNames, labelText)
%LOCAL_RESOLVE_SANS_SERIF_FONT Resolve a locally available sans-serif font.

    if nargin < 3
        labelText = '';
    end

    candidates = local_normalize_font_candidates(fontNameIn, fallbackNames);
    labelRequiresUnicode = local_label_requires_unicode_font(labelText);
    if labelRequiresUnicode
        keep = true(size(candidates));
        for i = 1:numel(candidates)
            normalized = regexprep(lower(candidates{i}), '[^a-z0-9]', '');
            keep(i) = ~contains(normalized, 'helvetica');
        end
        candidates = candidates(keep);
    end

    if isempty(candidates)
        error('EA_PLOT_PATCH_LEADDBS:MissingSansFont', ...
            'None of the requested sans-serif fonts are available.');
    end

    available = {};
    try
        available = cellstr(listfonts);
    catch
        available = {};
    end

    for i = 1:numel(candidates)
        idx = find(strcmpi(available, candidates{i}), 1, 'first');
        if ~isempty(idx)
            fontName = available{idx};
            return;
        end
    end

    if local_has_direct_pdf_font_candidate(candidates, labelRequiresUnicode)
        fontName = candidates{1};
        return;
    end

    error('EA_PLOT_PATCH_LEADDBS:MissingSansFont', ...
        'None of the requested sans-serif fonts are available: %s.', strjoin(candidates, ', '));
end

function tf = local_has_direct_pdf_font_candidate(candidates, labelRequiresUnicode)
%LOCAL_HAS_DIRECT_PDF_FONT_CANDIDATE Allow PDF renderer probe/validation to decide.

    tf = false;
    for i = 1:numel(candidates)
        normalized = regexprep(lower(candidates{i}), '[^a-z0-9]', '');
        isUnicodeSans = contains(normalized, 'arial') || ...
            strcmp(normalized, 'dejavusans') || ...
            strcmp(normalized, 'liberationsans');
        if labelRequiresUnicode
            if isUnicodeSans
                tf = true;
                return;
            end
        elseif isUnicodeSans || contains(normalized, 'helvetica')
            tf = true;
            return;
        end
    end
end

function cleanupObj = local_apply_root_font_defaults(fontName)
%LOCAL_APPLY_ROOT_FONT_DEFAULTS Temporarily set root default fonts.

    cleanupObj = [];
    if isempty(strtrim(char(fontName)))
        return;
    end

    try
        oldAxesFont = get(groot, 'DefaultAxesFontName');
        oldTextFont = get(groot, 'DefaultTextFontName');
        set(groot, 'DefaultAxesFontName', fontName, 'DefaultTextFontName', fontName);
        cleanupObj = onCleanup(@() set(groot, ...
            'DefaultAxesFontName', oldAxesFont, ...
            'DefaultTextFontName', oldTextFont));
    catch
        cleanupObj = [];
    end
end

function candidates = local_normalize_font_candidates(fontNameIn, fallbackNames)
%LOCAL_NORMALIZE_FONT_CANDIDATES Convert font inputs to a unique cell array.

    candidates = {};
    candidates = local_append_font_candidates(candidates, fontNameIn);
    candidates = local_append_font_candidates(candidates, fallbackNames);
    candidates = candidates(~cellfun(@isempty, candidates));
    if isempty(candidates)
        candidates = {'Arial', 'Arial Unicode MS', 'Helvetica', 'DejaVu Sans', 'Liberation Sans'};
    end
    [~, idx] = unique(lower(candidates), 'stable');
    candidates = candidates(sort(idx));
end

function candidates = local_append_font_candidates(candidates, value)
%LOCAL_APPEND_FONT_CANDIDATES Append font names from char, string, or cellstr.

    if isempty(value)
        return;
    end

    if ischar(value)
        candidates{end + 1} = strtrim(value); %#ok<AGROW>
    elseif isstring(value)
        for i = 1:numel(value)
            candidates{end + 1} = strtrim(char(value(i))); %#ok<AGROW>
        end
    elseif iscellstr(value)
        for i = 1:numel(value)
            candidates{end + 1} = strtrim(value{i}); %#ok<AGROW>
        end
    end
end

function local_reject_latex_interpreter(interpreterValue, paramName)
%LOCAL_REJECT_LATEX_INTERPRETER Disallow LaTeX in strict sans-serif mode.

    try
        interpreterName = lower(strtrim(char(interpreterValue)));
    catch
        interpreterName = '';
    end

    if strcmp(interpreterName, 'latex')
        error('EA_PLOT_PATCH_LEADDBS:LatexDisallowed', ...
            '%s cannot be latex when RequireSansSerifFont is true.', paramName);
    end
end

function local_assert_plain_text_label(labelText)
%LOCAL_ASSERT_PLAIN_TEXT_LABEL Ensure strict labels cannot invoke TeX/LaTeX.

    if isempty(labelText)
        return;
    end

    if ~isempty(regexp(labelText, '[$\\{}]', 'once'))
        error('EA_PLOT_PATCH_LEADDBS:NonPlainLabel', ...
            'RequireSansSerifFont requires a plain colorbar label without TeX or LaTeX tokens.');
    end
end

function local_assert_pdf_sans_serif(outFile, p)
%LOCAL_ASSERT_PDF_SANS_SERIF Reject PDFs that still embed TeX serif fonts.

    if ~p.RequireSansSerifFont
        return;
    end

    [~, ~, ext] = fileparts(outFile);
    if ~strcmpi(ext, '.pdf')
        return;
    end
    if exist(outFile, 'file') ~= 2
        error('EA_PLOT_PATCH_LEADDBS:MissingPdfOutput', ...
            'Expected PDF output was not created: %s', outFile);
    end

    rawText = local_read_binary_text_lower(outFile);
    fontNames = local_extract_pdf_font_names(rawText);
    if isempty(fontNames)
        local_delete_file_if_exists(outFile);
        error('EA_PLOT_PATCH_LEADDBS:PdfFontsNotFound', ...
            'PDF export did not expose any FontName or BaseFont entries.');
    end

    labelHasGreek = p.UseSymbolForGreek && local_label_has_greek_text(p.ColorbarLabel);
    forbidden = {'mwacmr', 'mwbcmr', 'cmr', 'cmmi', 'cmsy'};
    if ~p.UseSymbolForGreek
        forbidden = unique([forbidden, {'symbol'}], 'stable');
    end
    hit = fontNames(local_font_names_are_forbidden(fontNames, forbidden));
    if ~isempty(hit) || contains(rawText, 'computer modern')
        local_delete_file_if_exists(outFile);
        error('EA_PLOT_PATCH_LEADDBS:ForbiddenPdfFont', ...
            'PDF export embedded forbidden serif/TeX font tokens: %s.', strjoin(unique(hit), ', '));
    end

    allowed = local_allowed_pdf_font_tokens(p.FontName, p.FontFallbackNames);
    if local_label_has_radical_text(p.ColorbarLabel)
        allowed = unique([allowed, {'stixgeneral'}], 'stable');
    end
    if labelHasGreek
        allowed = unique([allowed, {'symbol'}], 'stable');
    end
    badFonts = fontNames(~local_font_names_are_allowed(fontNames, allowed));
    if ~isempty(badFonts)
        local_delete_file_if_exists(outFile);
        error('EA_PLOT_PATCH_LEADDBS:UnexpectedPdfFont', ...
            'PDF export embedded unexpected font names: %s.', strjoin(unique(badFonts), ', '));
    end

    if labelHasGreek && ~any(local_font_names_are_allowed(fontNames, {'symbol'}))
        local_delete_file_if_exists(outFile);
        error('EA_PLOT_PATCH_LEADDBS:GreekSymbolFontMissing', ...
            'PDF export did not expose Symbol for Greek colorbar label text.');
    end

    if local_label_requires_unicode_font(p.ColorbarLabel) && ~labelHasGreek
        helveticaHit = fontNames(local_font_names_are_forbidden(fontNames, {'helvetica'}));
        if ~isempty(helveticaHit)
            local_delete_file_if_exists(outFile);
            error('EA_PLOT_PATCH_LEADDBS:UnicodePdfFontFallback', ...
                'PDF export used Helvetica for a Unicode label and may replace Greek glyphs: %s.', ...
                strjoin(unique(helveticaHit), ', '));
        end

        unicodeAllowed = local_unicode_capable_pdf_font_tokens(p.FontName, p.FontFallbackNames);
        if ~any(local_font_names_are_allowed(fontNames, unicodeAllowed))
            local_delete_file_if_exists(outFile);
            error('EA_PLOT_PATCH_LEADDBS:UnicodePdfFontMissing', ...
                'PDF export did not expose a Unicode-capable sans-serif font for a Unicode label.');
        end
    end

    if ~any(contains(strjoin(fontNames, ' '), allowed))
        local_delete_file_if_exists(outFile);
        error('EA_PLOT_PATCH_LEADDBS:SansFontNotEmbedded', ...
            'PDF export did not expose an expected sans-serif font token.');
    end
end

function rawText = local_read_binary_text_lower(filePath)
%LOCAL_READ_BINARY_TEXT_LOWER Read a binary file as lowercase text.

    fid = fopen(filePath, 'r');
    if fid < 0
        error('EA_PLOT_PATCH_LEADDBS:PdfReadFailed', 'Could not read PDF: %s', filePath);
    end
    cleanupObj = onCleanup(@() fclose(fid));
    bytes = fread(fid, '*uint8')';
    rawText = lower(char(bytes));
    clear cleanupObj;
end

function fontNames = local_extract_pdf_font_names(rawText)
%LOCAL_EXTRACT_PDF_FONT_NAMES Extract normalized PDF FontName/BaseFont tokens.

    matches = regexp(rawText, '/(?:fontname|basefont)\s*/([^\s<>\[\]()/]+)', 'tokens');
    fontNames = cell(numel(matches), 1);
    for i = 1:numel(matches)
        fontNames{i} = matches{i}{1};
        plusIdx = strfind(fontNames{i}, '+');
        if ~isempty(plusIdx)
            fontNames{i} = fontNames{i}(plusIdx(end) + 1:end);
        end
        fontNames{i} = regexprep(fontNames{i}, '[^a-z0-9]', '');
    end
    fontNames = fontNames(~cellfun(@isempty, fontNames));
    fontNames = unique(fontNames, 'stable');
end

function tf = local_font_names_are_allowed(fontNames, allowed)
%LOCAL_FONT_NAMES_ARE_ALLOWED Check every embedded font against allowed tokens.

    tf = false(size(fontNames));
    for i = 1:numel(fontNames)
        tf(i) = any(strcmp(fontNames{i}, allowed)) || any(contains(fontNames{i}, allowed));
    end
end

function tf = local_font_names_are_forbidden(fontNames, forbidden)
%LOCAL_FONT_NAMES_ARE_FORBIDDEN Check embedded fonts against forbidden tokens.

    tf = false(size(fontNames));
    for i = 1:numel(fontNames)
        tf(i) = any(strcmp(fontNames{i}, forbidden)) || any(contains(fontNames{i}, forbidden));
    end
end

function tf = local_label_requires_unicode_font(labelText)
%LOCAL_LABEL_REQUIRES_UNICODE_FONT Return true when the label uses non-ASCII glyphs.

    if isempty(labelText)
        tf = false;
        return;
    end

    try
        labelText = char(string(labelText));
    catch
        try
            labelText = char(labelText);
        catch
            labelText = '';
        end
    end
    tf = any(double(labelText) > 127);
end

function tf = local_label_has_greek_text(labelText)
%LOCAL_LABEL_HAS_GREEK_TEXT Return true when a label contains Greek characters.

    if isempty(labelText)
        tf = false;
        return;
    end

    try
        labelText = char(string(labelText));
    catch
        try
            labelText = char(labelText);
        catch
            labelText = '';
        end
    end
    codes = double(labelText);
    tf = any((codes >= hex2dec('0370') & codes <= hex2dec('03FF')) | ...
        (codes >= hex2dec('1F00') & codes <= hex2dec('1FFF')));
end

function tf = local_label_has_radical_text(labelText)
%LOCAL_LABEL_HAS_RADICAL_TEXT Return true for plain labels containing sqrt text.

    if isempty(labelText)
        tf = false;
        return;
    end

    try
        labelText = char(string(labelText));
    catch
        try
            labelText = char(labelText);
        catch
            labelText = '';
        end
    end
    tf = contains(labelText, '√(');
end

function tokens = local_allowed_pdf_font_tokens(fontName, fallbackNames)
%LOCAL_ALLOWED_PDF_FONT_TOKENS Build expected sans-serif font tokens.

    candidates = local_normalize_font_candidates(fontName, fallbackNames);
    tokens = {'arial', 'arialmt', 'helvetica', 'dejavusans', 'liberationsans'};
    for i = 1:numel(candidates)
        name = lower(candidates{i});
        tokens{end + 1} = name; %#ok<AGROW>
        tokens{end + 1} = regexprep(name, '[^a-z0-9]', ''); %#ok<AGROW>
    end
    tokens = tokens(~cellfun(@isempty, tokens));
    [~, idx] = unique(tokens, 'stable');
    tokens = tokens(sort(idx));
end

function tokens = local_unicode_capable_pdf_font_tokens(fontName, fallbackNames)
%LOCAL_UNICODE_CAPABLE_PDF_FONT_TOKENS Build font tokens allowed for Greek glyphs.

    candidates = local_normalize_font_candidates(fontName, fallbackNames);
    tokens = {'arial', 'arialmt', 'arialunicodems', 'arialunicode', ...
        'dejavusans', 'liberationsans'};
    for i = 1:numel(candidates)
        name = lower(candidates{i});
        normalized = regexprep(name, '[^a-z0-9]', '');
        if contains(normalized, 'arial') || ...
                strcmp(normalized, 'dejavusans') || ...
                strcmp(normalized, 'liberationsans')
            tokens{end + 1} = name; %#ok<AGROW>
            tokens{end + 1} = normalized; %#ok<AGROW>
        end
    end
    tokens = tokens(~cellfun(@isempty, tokens));
    [~, idx] = unique(tokens, 'stable');
    tokens = tokens(sort(idx));
end

function local_delete_file_if_exists(filePath)
%LOCAL_DELETE_FILE_IF_EXISTS Delete a bad export before reporting failure.

    if exist(filePath, 'file') == 2
        try, delete(filePath); catch, end
    end
end

function local_enforce_surface_aspect(hAx)
%LOCAL_ENFORCE_SURFACE_ASPECT Keep anatomical surface geometry undistorted.

    if isempty(hAx) || ~ishandle(hAx)
        return;
    end

    try, axis(hAx, 'equal'); catch, end
    try, axis(hAx, 'vis3d'); catch, end
    try, camproj(hAx, 'orthographic'); catch, end
end

function local_apply_surface_axes_padding(hAx, patchHandles, paddingFraction)
%LOCAL_APPLY_SURFACE_AXES_PADDING Expand 3D limits to avoid surface clipping.

    if isempty(hAx) || ~ishandle(hAx) || isempty(paddingFraction) || paddingFraction <= 0
        return;
    end

    vertices = zeros(0, 3);
    patchHandles = patchHandles(:);
    patchHandles = patchHandles(ishandle(patchHandles));
    for i = 1:numel(patchHandles)
        try
            v = get(patchHandles(i), 'Vertices');
            if isnumeric(v) && size(v, 2) == 3
                vertices = [vertices; double(v)]; %#ok<AGROW>
            end
        catch
        end
    end

    if isempty(vertices)
        return;
    end

    finiteRows = all(isfinite(vertices), 2);
    vertices = vertices(finiteRows, :);
    if isempty(vertices)
        return;
    end

    mins = min(vertices, [], 1);
    maxs = max(vertices, [], 1);
    ranges = maxs - mins;
    fallbackRange = max(ranges);
    if fallbackRange <= 0 || ~isfinite(fallbackRange)
        fallbackRange = 1;
    end
    ranges(ranges <= 0 | ~isfinite(ranges)) = fallbackRange;
    pad = ranges * double(paddingFraction);

    try, xlim(hAx, [mins(1) - pad(1), maxs(1) + pad(1)]); catch, end
    try, ylim(hAx, [mins(2) - pad(2), maxs(2) + pad(2)]); catch, end
    try, zlim(hAx, [mins(3) - pad(3), maxs(3) + pad(3)]); catch, end
    local_enforce_surface_aspect(hAx);
end

function local_apply_surface_view_padding(hAx, paddingScale)
%LOCAL_APPLY_SURFACE_VIEW_PADDING Zoom out slightly to avoid cropped surfaces.

    if isempty(hAx) || ~ishandle(hAx) || isempty(paddingScale) || paddingScale <= 1
        return;
    end

    try
        currentViewAngle = camva(hAx);
        camva(hAx, currentViewAngle * double(paddingScale));
    catch
    end
end

function local_force_figures_hidden(figs, strictHeadless)
%LOCAL_FORCE_FIGURES_HIDDEN Hide MATLAB figures created for batch rendering.

    figs = figs(:);
    figs = figs(ishandle(figs));
    if isempty(figs)
        return;
    end

    for i = 1:numel(figs)
        try
            set(figs(i), 'Visible', 'off');
        catch
        end
    end

    if strictHeadless
        visible = false(size(figs));
        for i = 1:numel(figs)
            try
                visible(i) = strcmpi(get(figs(i), 'Visible'), 'on');
            catch
                visible(i) = false;
            end
        end
        if any(visible)
            error('EA_PLOT_PATCH_LEADDBS:StrictHeadlessVisibleFigure', ...
                'Strict headless mode failed because a MATLAB figure remained visible.');
        end
    end
end

function local_apply_view_struct_native(v, hAx)
%LOCAL_APPLY_VIEW_STRUCT_NATIVE Apply camera fields without calling Lead-DBS.

    if isempty(v) || ~isstruct(v) || isempty(hAx) || ~ishandle(hAx)
        return;
    end

    if isfield(v, 'az') && isfield(v, 'el')
        try, view(hAx, [double(v.az), double(v.el)]); catch, end
    end
    if isfield(v, 'camproj')
        try, camproj(hAx, char(v.camproj)); catch, end
    end
    if isfield(v, 'camva')
        try, camva(hAx, double(v.camva)); catch, end
    end
    if isfield(v, 'camup')
        try, camup(hAx, double(v.camup(:))'); catch, end
    end
    if isfield(v, 'camtarget')
        try, camtarget(hAx, double(v.camtarget(:))'); catch, end
    end
    if isfield(v, 'campos')
        try, campos(hAx, double(v.campos(:))'); catch, end
    end
end

function local_apply_surface_lighting(hAx, patchHandles, p)
%LOCAL_APPLY_SURFACE_LIGHTING Apply stable, camera-aligned surface lighting.

    patchHandles = patchHandles(:);
    patchHandles = patchHandles(ishandle(patchHandles));
    lightingProfile = local_normalize_surface_lighting_profile(p.SurfaceLightingProfile);

    try
        delete(findall(hAx, 'Type', 'light'));
    catch
    end

    lightingMode = lower(strtrim(char(p.Lighting)));
    if isempty(lightingMode)
        lightingMode = 'gouraud';
    end

    try
        lighting(hAx, lightingMode);
    catch
    end

    for i = 1:numel(patchHandles)
        h = patchHandles(i);
        try, material(h, char(p.Material)); catch, end
        try, h.FaceLighting = lightingMode; catch, end
        try, h.BackFaceLighting = 'reverselit'; catch, end
        try, h.AmbientStrength = double(p.SurfaceAmbientStrength); catch, end
        try, h.DiffuseStrength = double(p.SurfaceDiffuseStrength); catch, end
        try, h.SpecularStrength = double(p.SurfaceSpecularStrength); catch, end
        try, h.SpecularExponent = double(p.SurfaceSpecularExponent); catch, end
    end

    if ~strcmp(lightingMode, 'none')
        switch lightingProfile
            case 'texture'
                local_apply_texture_surface_lights(hAx);
            case 'balanced'
                try, camlight(hAx, 'headlight'); catch, end
                try, camlight(hAx, 'left'); catch, end
        end
    end
end

function p = local_resolve_surface_lighting_profile(p)
%LOCAL_RESOLVE_SURFACE_LIGHTING_PROFILE Apply named profile defaults.

    profile = local_normalize_surface_lighting_profile(p.SurfaceLightingProfile);
    p.SurfaceLightingProfile = profile;

    if strcmp(profile, 'balanced')
        p.SurfaceAmbientStrength = 0.85;
        p.SurfaceDiffuseStrength = 0.25;
        p.SurfaceSpecularStrength = 0.00;
        p.SurfaceSpecularExponent = 8;
    end
end

function profile = local_normalize_surface_lighting_profile(profileIn)
%LOCAL_NORMALIZE_SURFACE_LIGHTING_PROFILE Validate the surface lighting profile.

    profile = lower(strtrim(char(string(profileIn))));
    if isempty(profile)
        profile = 'texture';
    end

    if ~ismember(profile, {'texture', 'balanced'})
        error('EA_PLOT_PATCH_LEADDBS:BadLightingProfile', ...
            'SurfaceLightingProfile must be ''texture'' or ''balanced''.');
    end
end

function local_apply_texture_surface_lights(hAx)
%LOCAL_APPLY_TEXTURE_SURFACE_LIGHTS Add camera-relative lights for surface relief.

    try
        target = double(camtarget(hAx));
        camPos = double(campos(hAx));
        up = double(camup(hAx));
        front = local_unit_vector(camPos - target, [0 0 1]);
        up = local_unit_vector(up, [0 0 1]);
        right = local_unit_vector(cross(front, up), [1 0 0]);
        up = local_unit_vector(cross(right, front), up);

        keyDir = local_unit_vector(front * 0.82 + right * 0.82 + up * 0.50, front);
        fillDir = local_unit_vector(front * 0.20 - right * 0.48 - up * 0.10, front);
        rimDir = local_unit_vector(-front * 0.25 - right * 0.10 + up * 0.36, up);

        local_add_infinite_light(hAx, keyDir, [0.95 0.95 0.95]);
        local_add_infinite_light(hAx, fillDir, [0.12 0.12 0.12]);
        local_add_infinite_light(hAx, rimDir, [0.08 0.08 0.08]);
    catch
        try, camlight(hAx, 'left'); catch, end
        try, camlight(hAx, 'headlight'); catch, end
    end
end

function local_add_infinite_light(hAx, directionVector, colorValue)
%LOCAL_ADD_INFINITE_LIGHT Add one infinite light from a normalized direction.

    light('Parent', hAx, ...
        'Style', 'infinite', ...
        'Position', directionVector, ...
        'Color', colorValue);
end

function v = local_unit_vector(value, fallback)
%LOCAL_UNIT_VECTOR Normalize a row vector with a fallback for degenerate input.

    v = double(value(:))';
    n = norm(v);
    if ~isfinite(n) || n <= eps
        v = double(fallback(:))';
        n = norm(v);
    end
    if ~isfinite(n) || n <= eps
        v = [1 0 0];
        n = 1;
    end
    v = v ./ n;
end

function interp = local_resolve_tick_interpreter(mode)
%LOCAL_RESOLVE_TICK_INTERPRETER Keep numeric tick labels in the requested font.

    if nargin < 1 || isempty(mode)
        mode = 'auto';
    end

    try
        s = lower(strtrim(char(mode)));
    catch
        s = 'auto';
    end

    if strcmp(s, 'auto')
        interp = 'tex';
        return;
    end

    known = {'latex','tex','none'};
    if any(strcmp(s, known))
        interp = s;
    else
        interp = 'tex';
    end
end

function ring = local_vertex_ring_distance(faces, missingVerts, maxRing)
%LOCAL_VERTEX_RING_DISTANCE Compute vertex ring-distance from missing vertices.
%
% The distance is computed in unweighted edge-steps (BFS on the mesh graph).
% ring(v)=0 for missing vertices, 1 for their neighbors, etc.

    nv = size(missingVerts, 1);
    if numel(missingVerts) ~= nv
        missingVerts = missingVerts(:);
        nv = numel(missingVerts);
    end

    if isempty(faces)
        ring = inf(nv, 1);
        return;
    end

    % Build a sparse, undirected vertex adjacency matrix.
    e = [faces(:, [1 2]); faces(:, [2 3]); faces(:, [3 1])];
    i = e(:, 1);
    j = e(:, 2);
    A = sparse([i; j], [j; i], true, nv, nv);

    ring = inf(nv, 1);
    ring(missingVerts) = 0;

    visited = missingVerts;
    frontier = missingVerts;

    for step = 1:maxRing
        if ~any(frontier)
            break;
        end
        neigh = (A * double(frontier)) > 0;
        new = neigh & ~visited;
        ring(new) = step;
        visited = visited | new;
        frontier = new;
    end
end

function rgb = local_scalar_to_rgb(val, cmap, clim)
%LOCAL_SCALAR_TO_RGB Map scalar values to RGB using a colormap and clim.
%
% This is used to create a truecolor patch for the blended boundary region
% while keeping a scalar patch elsewhere (for the colorbar).

    if isempty(val)
        rgb = zeros(0, 3);
        return;
    end

    val = double(val(:));

    if isempty(cmap)
        try
            cmap = parula(256);
        catch
            cmap = jet(256);
        end
    end
    cmap = double(cmap);
    n = size(cmap, 1);

    if isempty(clim) || numel(clim) ~= 2 || ~all(isfinite(clim))
        v = val(isfinite(val));
        if isempty(v)
            clim = [0 1];
        else
            clim = [min(v) max(v)];
        end
    end

    if clim(1) == clim(2)
        clim = clim + [-1 1] * eps(clim(1) + 1);
    end

    t = (val - clim(1)) / (clim(2) - clim(1));
    t(~isfinite(t)) = 0;
    t = max(0, min(1, t));

    idx = 1 + round(t * (n - 1));
    idx = max(1, min(n, idx));

    rgb = cmap(idx, :);
end

function [tf, rgb] = local_try_parse_color_spec(spec)
%LOCAL_TRY_PARSE_COLOR_SPEC Try to interpret a user input as a MATLAB color.
%
% Supported inputs (case-insensitive):
%   - short names: 'r','g','b','c','m','y','k','w'
%   - long names : 'red','green','blue','cyan','magenta','yellow','black','white'
%   - gray names : 'gray','grey'
%   - hex codes  : '#RRGGBB'
%
% Output
%   tf  : true if parsing succeeded
%   rgb : 1x3 RGB in [0,1]

    tf = false;
    rgb = [0.6 0.6 0.6];

    if isnumeric(spec) && numel(spec) == 3
        rgb = double(spec(:))';
        rgb = max(0, min(1, rgb));
        tf = all(isfinite(rgb));
        return;
    end

    if ~(ischar(spec) || (isstring(spec) && isscalar(spec)))
        return;
    end

    s = lower(strtrim(char(spec)));
    if isempty(s)
        return;
    end

    switch s
        case {'r','red'}
            rgb = [1 0 0]; tf = true;
        case {'g','green'}
            rgb = [0 1 0]; tf = true;
        case {'b','blue'}
            rgb = [0 0 1]; tf = true;
        case {'c','cyan'}
            rgb = [0 1 1]; tf = true;
        case {'m','magenta'}
            rgb = [1 0 1]; tf = true;
        case {'y','yellow'}
            rgb = [1 1 0]; tf = true;
        case {'k','black'}
            rgb = [0 0 0]; tf = true;
        case {'w','white'}
            rgb = [1 1 1]; tf = true;
        case {'gray','grey','grey50','gray50'}
            rgb = [0.6 0.6 0.6]; tf = true;
        otherwise
            % Hex color code: #RRGGBB
            if numel(s) == 7 && s(1) == '#'
                try
                    r = hex2dec(s(2:3));
                    g = hex2dec(s(4:5));
                    b = hex2dec(s(6:7));
                    rgb = [r g b] / 255;
                    tf = true;
                catch
                    tf = false;
                end
            end
    end
end





function interp = local_resolve_text_interpreter(mode, hint)
%LOCAL_RESOLVE_TEXT_INTERPRETER Resolve an interpreter setting.
%
% Inputs
%   mode : char/string. 'auto', 'latex', 'tex', or 'none'.
%   hint : either a label string (for auto-detection) or an interpreter
%          string ('latex'/'tex'/'none') to follow in auto mode.
%
% Output
%   interp : resolved interpreter string: 'latex' | 'tex' | 'none'
%
% Notes
%   - In 'auto' mode, this function selects 'latex' if the hint contains
%     a '$' character (typical math-mode LaTeX usage). Otherwise it uses
%     'tex' to preserve user-specified FontName (e.g., Arial) when possible.

    if nargin < 1 || isempty(mode)
        mode = 'auto';
    end

    try
        s = lower(strtrim(char(mode)));
    catch
        s = 'auto';
    end

    if nargin < 2
        hint = '';
    end

    % If hint is already a known interpreter, use it in 'auto' mode.
    h = '';
    try
        h = lower(strtrim(char(hint)));
    catch
        h = '';
    end

    known = {'latex','tex','none'};

    if strcmp(s, 'auto')
        if any(strcmp(h, known))
            interp = h;
            return;
        end

        % Auto-detect LaTeX if the label contains '$'.
        hs = '';
        try
            hs = char(hint);
        catch
            hs = '';
        end

        if ~isempty(strfind(hs, '$')) %#ok<STREMP>
            interp = 'latex';
        else
            interp = 'tex';
        end
        return;
    end

    if any(strcmp(s, known))
        interp = s;
    else
        % Safe default
        interp = 'tex';
    end
end


function local_fix_colorbar_pose(cb, p)
%LOCAL_FIX_COLORBAR_POSE Keep colorbar ticks and label on the right/outside.
%
% When the view is mirrored/flipped, some workflows (e.g., viewer helpers)
% may inadvertently toggle the colorbar tick/label side. For modern MATLAB
% ColorBar objects, the tick/label side is controlled by AxisLocation:
%   - 'out' : ticks/labels/label on the outside of the figure
%   - 'in'  : ticks/labels/label on the inside (towards the plot)
%
% For a right-side colorbar (east/eastoutside), AxisLocation='out' means the
% ticks and label stay on the right side.

    if isempty(cb) || ~ishandle(cb)
        return;
    end

    % Do not override manual positioning.
    userManualPos = false;
    try
        userManualPos = isfield(p, 'ColorbarPosition') && ~isempty(p.ColorbarPosition);
    catch
        userManualPos = false;
    end

    % Keep the requested location stable unless the user uses a manual Position.
    if ~userManualPos
        if isfield(p, 'ColorbarLocation') && ~isempty(p.ColorbarLocation)
            try
                cb.Location = char(p.ColorbarLocation);
            catch
            end
        end
    end

    % Modern MATLAB ColorBar: force tick/label side to the outside.
    try
        if isprop(cb, 'AxisLocation')
            cb.AxisLocation = 'out';
            if isprop(cb, 'AxisLocationMode')
                cb.AxisLocationMode = 'manual';
            end
        end
    catch
    end

    % Backwards-compatible fallback (older HG1-style colorbars treated as axes).
    try
        if isprop(cb, 'Orientation') && strcmpi(cb.Orientation, 'vertical')
            if isprop(cb, 'YAxisLocation'); cb.YAxisLocation = 'right'; end
        else
            if isprop(cb, 'XAxisLocation'); cb.XAxisLocation = 'bottom'; end
        end
    catch
    end

    % Keep tick direction outward (visual stability).
    try
        cb.TickDirection = 'out';
        if isprop(cb, 'TickDirectionMode')
            cb.TickDirectionMode = 'manual';
        end
    catch
    end

end


function local_install_colorbar_lock(hAx, hCb, p)
%LOCAL_INSTALL_COLORBAR_LOCK Re-apply fixed colorbar pose on view changes.
%
% The goal is to keep the colorbar tick labels and label on the right side
% even when the main 3D view is mirrored/flipped.

    if isempty(hAx) || ~ishandle(hAx) || isempty(hCb) || ~ishandle(hCb)
        return;
    end

    % Avoid installing twice.
    try
        if isappdata(hCb, 'EA_COLORBAR_LOCK_LISTENERS')
            return;
        end
    catch
    end

    lh = event.listener.empty(0, 1);

    % Listen to camera/view-related properties on the main axes.
    propsAx = {'View', 'CameraPosition', 'CameraTarget', 'CameraUpVector', 'XDir', 'YDir', 'ZDir'};
    for i = 1:numel(propsAx)
        prop = propsAx{i};
        if isprop(hAx, prop)
            try
                lh(end+1,1) = addlistener(hAx, prop, 'PostSet', @(~,~) local_fix_colorbar_pose(hCb, p)); %#ok<AGROW>
            catch
            end
        end
    end

    % Store listeners to keep them alive.
    try
        setappdata(hCb, 'EA_COLORBAR_LOCK_LISTENERS', lh);
    catch
        try
            hFig = ancestor(hAx, 'figure');
            setappdata(hFig, 'EA_COLORBAR_LOCK_LISTENERS', lh);
        catch
        end
    end

    % Apply once immediately.
    local_fix_colorbar_pose(hCb, p);

end
