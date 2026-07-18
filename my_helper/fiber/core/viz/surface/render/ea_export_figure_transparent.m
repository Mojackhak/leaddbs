function ea_export_figure_transparent(hFig, outFile, varargin)
%EA_EXPORT_FIGURE_TRANSPARENT Export a figure snapshot with optional transparency.
%
%   EA_EXPORT_FIGURE_TRANSPARENT(hFig, outFile)
%   EA_EXPORT_FIGURE_TRANSPARENT(hFig, outFile, 'Name', value, ...)
%
% This helper exports the current figure to a file.
%
% Behavior
%   - If Transparent==true, the function tries to export with a transparent
%     background ('none') first.
%   - If the output does not contain transparency (or if an error occurs),
%     the function falls back to BackgroundColor (default: white).
%   - If Transparent==false, the function exports using BackgroundColor.
%
% Supported output formats
%   - Raster: .png (recommended), .tif, .jpg, ...
%   - Vector (best effort): .pdf, .svg, .eps
%
% Inputs
%   hFig    : figure handle (use gcf if empty)
%   outFile : output filename
%
% Name-Value pairs
%   'Transparent'     : logical. Default: true
%   'BackgroundColor' : background color used when not transparent, and as a
%                       fallback if transparency fails. Default: 'white'.
%                       Supported:
%                         - 'white','black','none','k','w', ...
%                         - 1x3 numeric RGB in [0,1]
%   'Resolution'      : scalar DPI. Default: 300 (raster only)
%   'Renderer'        : 'opengl' (default) or 'painters'
%   'ContentType'     : 'auto', 'vector', 'image', or 'mixed'. 'mixed'
%                       applies to PDF export and rasterizes the figure
%                       without colorbars, then redraws colorbars as vector
%                       objects in the final PDF.
%   'UseSymbolForGreek' : logical. Default: false. When true, vector
%                       colorbar text draws Greek characters with Symbol and
%                       all other characters with the base font.
%
% Notes
%   - Transparent backgrounds are most reliable with exportgraphics() and PNG.
%   - Lead-DBS ea_mnifigure() often uses a dark figure background. This
%     function temporarily overrides figure/axes colors for exporting and
%     restores them afterwards.
%   - For complex 3D scenes, vector exports may partially rasterize content
%     even when using PDF/SVG (this is a MATLAB limitation).

    if nargin < 1 || isempty(hFig)
        hFig = gcf;
    end
    if nargin < 2 || isempty(outFile)
        error('EA_EXPORT_FIGURE_TRANSPARENT:BadInput', 'outFile must be provided.');
    end
    if ~ishandle(hFig) || ~strcmp(get(hFig, 'Type'), 'figure')
        error('EA_EXPORT_FIGURE_TRANSPARENT:BadFigure', 'hFig must be a valid figure handle.');
    end

    ip = inputParser;
    ip.FunctionName = mfilename;

    addParameter(ip, 'Transparent', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'BackgroundColor', 'white', @local_is_background_spec);
    addParameter(ip, 'Resolution', 300, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'Renderer', 'opengl', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ContentType', 'auto', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'UseSymbolForGreek', false, @(x) islogical(x) && isscalar(x));

    parse(ip, varargin{:});
    p = ip.Results;

    outFile = char(outFile);
    [outDir,~,ext] = fileparts(outFile);
    if isempty(ext)
        ext = '.png';
        outFile = [outFile ext];
    end
    if ~isempty(outDir) && exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end

    isVector = any(strcmpi(ext, {'.pdf','.svg','.eps'}));

    % Normalize background spec to a MATLAB-friendly form.
    bgFallback = local_normalize_background_spec(p.BackgroundColor);

    % Cache current appearance so we can restore it.
    oldFigColor = get(hFig, 'Color');
    oldInvert   = get(hFig, 'InvertHardcopy');
    oldRenderer = get(hFig, 'Renderer');

    ax = findall(hFig, 'Type', 'axes');
    oldAxColor = cell(numel(ax), 1);
    for i = 1:numel(ax)
        try
            oldAxColor{i} = get(ax(i), 'Color');
        catch
            oldAxColor{i} = [];
        end
    end

    % Helper to apply a background mode.
    function apply_bg(bg)
        % bg: 'none' | color name | 1x3 RGB
        try
            set(hFig, 'InvertHardcopy', 'off');
        catch
        end
        try
            set(hFig, 'Renderer', char(p.Renderer));
        catch
        end

        try
            set(hFig, 'Color', bg);
        catch
            % If MATLAB rejects a background spec, fall back to white.
            set(hFig, 'Color', 'white');
            bg = 'white';
        end

        % Make axes backgrounds transparent so the figure color shows through.
        for ii = 1:numel(ax)
            try, set(ax(ii), 'Color', 'none'); catch, end
        end
    end

    % Helper to actually export once (best effort).
    function do_export(bg)
        contentType = local_resolve_content_type(p.ContentType, isVector);
        if local_has_exportgraphics()
            if strcmp(contentType, 'mixed') && strcmpi(ext, '.pdf')
                local_export_mixed_pdf(hFig, outFile, bg, p.Resolution, p.Renderer, p.UseSymbolForGreek);
            elseif isVector
                exportgraphics(hFig, outFile, ...
                    'BackgroundColor', bg, ...
                    'ContentType', contentType);
            else
                exportgraphics(hFig, outFile, ...
                    'BackgroundColor', bg, ...
                    'Resolution', p.Resolution);
            end
        else
            % Fallback: print() with renderer flags.
            dev = '-dpng';
            if strcmpi(ext, '.tif') || strcmpi(ext, '.tiff')
                dev = '-dtiff';
            elseif strcmpi(ext, '.jpg') || strcmpi(ext, '.jpeg')
                dev = '-djpeg';
            elseif strcmpi(ext, '.pdf')
                dev = '-dpdf';
            elseif strcmpi(ext, '.svg')
                dev = '-dsvg';
            elseif strcmpi(ext, '.eps')
                dev = '-depsc2';
            end

            rflag = '';
            if strcmpi(char(p.Renderer), 'opengl')
                rflag = '-opengl';
            elseif strcmpi(char(p.Renderer), 'painters')
                rflag = '-painters';
            end

            if isVector
                % Vector exports typically ignore resolution.
                if isempty(rflag)
                    print(hFig, outFile, dev);
                else
                    print(hFig, outFile, dev, rflag);
                end
            else
                resArg = sprintf('-r%d', round(p.Resolution));
                if isempty(rflag)
                    print(hFig, outFile, dev, resArg);
                else
                    print(hFig, outFile, dev, resArg, rflag);
                end
            end
        end
    end

    % Helper to test if a PNG contains *actual* transparency.
    function tf = png_has_transparency(fname)
        tf = false;
        if exist(fname, 'file') ~= 2
            return;
        end
        [~,~,e] = fileparts(fname);
        if ~strcmpi(e, '.png')
            return;
        end
        try
            [~,~,a] = imread(fname);
            if isempty(a)
                tf = false;
                return;
            end
            a = double(a(:));
            tf = any(a < max(a));
        catch
            tf = false;
        end
    end

    transparentOK = false;

    try
        if p.Transparent
            % Try transparent first.
            apply_bg('none');
            try
                do_export('none');
                if isVector
                    % No robust post-check for vector files; if export succeeded,
                    % we accept it.
                    transparentOK = true;
                else
                    transparentOK = png_has_transparency(outFile);
                end
            catch
                transparentOK = false;
            end
        end

        % Fallback: export with user-specified background color.
        if ~transparentOK
            apply_bg(bgFallback);
            do_export(bgFallback);
        end

    catch ME
        % Restore state before throwing.
        try, set(hFig, 'Color', oldFigColor); catch, end
        try, set(hFig, 'InvertHardcopy', oldInvert); catch, end
        try, set(hFig, 'Renderer', oldRenderer); catch, end
        for i = 1:numel(ax)
            try
                if ~isempty(oldAxColor{i})
                    set(ax(i), 'Color', oldAxColor{i});
                end
            catch
            end
        end
        rethrow(ME);
    end

    % Restore original figure/axes appearance.
    try, set(hFig, 'Color', oldFigColor); catch, end
    try, set(hFig, 'InvertHardcopy', oldInvert); catch, end
    try, set(hFig, 'Renderer', oldRenderer); catch, end
    for i = 1:numel(ax)
        try
            if ~isempty(oldAxColor{i})
                set(ax(i), 'Color', oldAxColor{i});
            end
        catch
        end
    end
end

% -------------------------------------------------------------------------
% Local helpers
% -------------------------------------------------------------------------

function contentType = local_resolve_content_type(contentTypeIn, isVector)
%LOCAL_RESOLVE_CONTENT_TYPE Normalize exportgraphics content type.

    contentType = lower(strtrim(char(contentTypeIn)));
    if isempty(contentType) || strcmp(contentType, 'auto')
        if isVector
            contentType = 'vector';
        else
            contentType = 'image';
        end
        return;
    end

    valid = {'vector','image','mixed'};
    if ~any(strcmp(contentType, valid))
        error('EA_EXPORT_FIGURE_TRANSPARENT:BadContentType', ...
            'ContentType must be auto, vector, image, or mixed.');
    end

    if strcmp(contentType, 'mixed') && ~isVector
        contentType = 'image';
    end
end

function tf = local_has_exportgraphics()
%LOCAL_HAS_EXPORTGRAPHICS Return true for m-file, p-code, or built-in variants.

    exportgraphics_status = exist('exportgraphics', 'file');
    tf = any(exportgraphics_status == [2 5 6]);
end

function local_export_mixed_pdf(hFig, outFile, bg, resolution, rendererName, useSymbolForGreek)
%LOCAL_EXPORT_MIXED_PDF Export a raster scene with vector colorbar overlays.

    colorbarSpecs = local_capture_colorbars(hFig, useSymbolForGreek);
    colorbars = findall(hFig, 'Type', 'ColorBar');
    oldVisible = cell(numel(colorbars), 1);
    for i = 1:numel(colorbars)
        try
            oldVisible{i} = get(colorbars(i), 'Visible');
            set(colorbars(i), 'Visible', 'off');
        catch
            oldVisible{i} = [];
        end
    end

    try
        drawnow;
        rasterSpecs = local_capture_raster_axes(hFig, bg, resolution);
        if local_has_radical_colorbar(colorbarSpecs)
            rasterSpecs = local_adjust_raster_layers_for_radical_colorbar(rasterSpecs);
        end
    catch ME
        for i = 1:numel(colorbars)
            try
                if ~isempty(oldVisible{i})
                    set(colorbars(i), 'Visible', oldVisible{i});
                end
            catch
            end
        end
        rethrow(ME);
    end

    for i = 1:numel(colorbars)
        try
            if ~isempty(oldVisible{i})
                set(colorbars(i), 'Visible', oldVisible{i});
            end
        catch
        end
    end

    oldFigUnits = get(hFig, 'Units');
    oldFigPos = get(hFig, 'Position');
    compFig = figure( ...
        'Visible', 'off', ...
        'Color', 'white', ...
        'Units', oldFigUnits, ...
        'Position', oldFigPos, ...
        'Renderer', 'painters', ...
        'InvertHardcopy', 'off');
    cleanupFig = onCleanup(@() local_close_if_handle(compFig));

    local_draw_page_background(compFig, bg);

    nonTriadIdx = find(~strcmp({rasterSpecs.LayerType}, 'triad'));
    triadIdx = find(strcmp({rasterSpecs.LayerType}, 'triad'));

    for i = nonTriadIdx(:)'
        local_draw_raster_layer(compFig, rasterSpecs(i));
    end

    for i = 1:numel(colorbarSpecs)
        local_draw_vector_colorbar(compFig, colorbarSpecs(i));
    end

    for i = triadIdx(:)'
        local_draw_raster_layer(compFig, rasterSpecs(i));
    end

    try
        set(compFig, 'Renderer', 'painters');
    catch
        try, set(compFig, 'Renderer', char(rendererName)); catch, end
    end
    exportgraphics(compFig, outFile, ...
        'BackgroundColor', bg, ...
        'ContentType', 'vector');

    clear cleanupFig;
end

function specs = local_capture_raster_axes(hFig, bg, resolution)
%LOCAL_CAPTURE_RASTER_AXES Rasterize non-colorbar axes into layout slots.

    axesList = local_find_raster_axes(hFig);
    specs = repmat(local_empty_raster_spec(), 0, 1);

    if isempty(axesList)
        spec = local_empty_raster_spec();
        spec.Position = [0 0 1 1];
        spec = local_export_raster_target(hFig, spec, bg, resolution);
        specs(end + 1) = spec;
        return;
    end

    positions = zeros(numel(axesList), 4);
    for i = 1:numel(axesList)
        positions(i, :) = local_get_normalized_position(axesList(i));
    end
    areas = positions(:, 3) .* positions(:, 4);
    [~, order] = sort(areas, 'descend');

    for idx = order(:)'
        spec = local_empty_raster_spec();
        spec.Position = positions(idx, :);
        spec.LayerType = local_raster_layer_type(axesList(idx));
        if any(~isfinite(spec.Position)) || spec.Position(3) <= 0 || spec.Position(4) <= 0
            continue;
        end
        spec = local_export_raster_target(axesList(idx), spec, bg, resolution);
        specs(end + 1) = spec; %#ok<AGROW>
    end
end

function axesList = local_find_raster_axes(hFig)
%LOCAL_FIND_RASTER_AXES Return axes that should stay in the raster layer.

    axesListAll = flipud(findall(hFig, 'Type', 'axes'));
    keep = false(numel(axesListAll), 1);

    for i = 1:numel(axesListAll)
        ax = axesListAll(i);
        try
            if strcmpi(get(ax, 'Tag'), 'Colorbar')
                continue;
            end
        catch
        end

        try
            hasSurface = ~isempty(findall(ax, 'Type', 'patch')) || ...
                ~isempty(findall(ax, 'Type', 'surface'));
            hasTriad = strcmpi(get(ax, 'Tag'), 'EA_RAS_TRIAD_AXES');
            hasImage = ~isempty(findall(ax, 'Type', 'image'));
            hasLine = ~isempty(findall(ax, 'Type', 'line'));
            hasText = ~isempty(findall(ax, 'Type', 'text'));
            keep(i) = hasSurface || hasTriad || hasImage || hasLine || hasText;
        catch
            keep(i) = false;
        end
    end

    axesList = axesListAll(keep);
end

function layerType = local_raster_layer_type(ax)
%LOCAL_RASTER_LAYER_TYPE Classify raster axes for mixed PDF composition.

    layerType = 'other';
    try
        if strcmpi(get(ax, 'Tag'), 'EA_RAS_TRIAD_AXES')
            layerType = 'triad';
            return;
        end
    catch
    end

    try
        if ~isempty(findall(ax, 'Type', 'patch')) || ~isempty(findall(ax, 'Type', 'surface'))
            layerType = 'surface';
        end
    catch
    end
end

function pos = local_get_normalized_position(ax)
%LOCAL_GET_NORMALIZED_POSITION Return axes position in normalized units.

    pos = [NaN NaN NaN NaN];
    try
        oldUnits = ax.Units;
        ax.Units = 'normalized';
        pos = ax.Position;
        ax.Units = oldUnits;
    catch
        try, ax.Units = oldUnits; catch, end
    end
end

function spec = local_export_raster_target(target, spec, bg, resolution)
%LOCAL_EXPORT_RASTER_TARGET Export one raster target and load the image.

    tmpPng = [tempname, '.png'];
    cleanupPng = onCleanup(@() local_delete_if_exists(tmpPng));
    exportgraphics(target, tmpPng, ...
        'BackgroundColor', bg, ...
        'Resolution', resolution);

    [spec.Image, ~, spec.Alpha] = imread(tmpPng);
    if isempty(spec.Alpha)
        spec.Alpha = ones(size(spec.Image, 1), size(spec.Image, 2));
    end

    clear cleanupPng;
end

function spec = local_empty_raster_spec()
%LOCAL_EMPTY_RASTER_SPEC Default raster layer values.

    spec = struct();
    spec.Position = [0 0 1 1];
    spec.LayerType = 'other';
    spec.Image = [];
    spec.Alpha = [];
end

function local_draw_page_background(parentFig, bg)
%LOCAL_DRAW_PAGE_BACKGROUND Prevent tight PDF cropping around plotted objects.

    bgRgb = local_background_rgb(bg);
    if isempty(bgRgb)
        return;
    end

    bgAx = axes('Parent', parentFig, ...
        'Units', 'normalized', ...
        'Position', [0 0 1 1], ...
        'Visible', 'off', ...
        'Color', 'none', ...
        'XLim', [0 1], ...
        'YLim', [0 1]);
    patch(bgAx, [0 1 1 0], [0 0 1 1], bgRgb, ...
        'EdgeColor', 'none', ...
        'Clipping', 'off');
    axis(bgAx, 'off');
end

function bgRgb = local_background_rgb(bg)
%LOCAL_BACKGROUND_RGB Convert export background to an RGB page fill.

    bgRgb = [];
    if isnumeric(bg) && numel(bg) == 3
        bgRgb = max(0, min(1, double(bg(:))'));
        return;
    end

    bg = lower(strtrim(char(string(bg))));
    switch bg
        case {'white','w'}
            bgRgb = [1 1 1];
        case {'black','k'}
            bgRgb = [0 0 0];
        case {'none','transparent'}
            bgRgb = [];
        otherwise
            bgRgb = [1 1 1];
    end
end

function local_draw_raster_layer(parentFig, spec)
%LOCAL_DRAW_RASTER_LAYER Draw one raster layer without changing its aspect.

    if isempty(spec.Image)
        return;
    end

    img = spec.Image;
    alpha = spec.Alpha;
    if isempty(alpha)
        alpha = ones(size(img, 1), size(img, 2));
    end

    imgAx = axes('Parent', parentFig, ...
        'Units', 'normalized', ...
        'Position', spec.Position, ...
        'Visible', 'off');
    image(imgAx, img, 'AlphaData', alpha);
    set(imgAx, ...
        'XLim', [0.5, size(img, 2) + 0.5], ...
        'YLim', [0.5, size(img, 1) + 0.5], ...
        'YDir', 'reverse', ...
        'DataAspectRatio', [1 1 1], ...
        'DataAspectRatioMode', 'manual', ...
        'PlotBoxAspectRatio', [size(img, 2) size(img, 1) 1], ...
        'PlotBoxAspectRatioMode', 'manual');
    axis(imgAx, 'off');
end

function specs = local_capture_colorbars(hFig, useSymbolForGreek)
%LOCAL_CAPTURE_COLORBARS Capture colorbar geometry and text for vector redraw.

    if nargin < 2 || isempty(useSymbolForGreek)
        useSymbolForGreek = false;
    end
    colorbars = flipud(findall(hFig, 'Type', 'ColorBar'));
    specs = repmat(local_empty_colorbar_spec(), numel(colorbars), 1);

    for i = 1:numel(colorbars)
        cb = colorbars(i);
        spec = local_empty_colorbar_spec();
        spec.UseSymbolForGreek = logical(useSymbolForGreek);

        try
            oldUnits = cb.Units;
            cb.Units = 'normalized';
            spec.Position = cb.Position;
            cb.Units = oldUnits;
        catch
        end

        try, spec.Orientation = cb.Orientation; catch, end
        if isempty(spec.Orientation)
            if spec.Position(4) >= spec.Position(3)
                spec.Orientation = 'vertical';
            else
                spec.Orientation = 'horizontal';
            end
        end

        try, spec.Limits = cb.Limits; catch, end
        if isempty(spec.Limits) || numel(spec.Limits) ~= 2 || spec.Limits(1) == spec.Limits(2)
            try, spec.Limits = caxis; catch, spec.Limits = [0 1]; end
        end
        if spec.Limits(1) == spec.Limits(2)
            spec.Limits = spec.Limits + [-0.5 0.5];
        end

        try, spec.Ticks = cb.Ticks; catch, spec.Ticks = []; end
        try, spec.TickLabels = local_normalize_tick_labels(cb.TickLabels); catch, end
        try, spec.FontName = cb.FontName; catch, end
        try, spec.FontSize = cb.FontSize; catch, end
        try, spec.Color = cb.Color; catch, end
        try, spec.LineWidth = max(1.0, double(cb.LineWidth)); catch, end
        try, spec.TickLength = max(double(cb.TickLength(:))); catch, end
        try, spec.TickLabelInterpreter = cb.TickLabelInterpreter; catch, end

        try
            spec.LabelString = cb.Label.String;
            spec.LabelFontName = cb.Label.FontName;
            spec.LabelFontSize = cb.Label.FontSize;
            spec.LabelInterpreter = cb.Label.Interpreter;
            spec.LabelColor = cb.Label.Color;
        catch
        end

        spec.Colormap = local_resolve_colorbar_colormap(cb, hFig);

        specs(i) = spec;
    end
end

function cmap = local_resolve_colorbar_colormap(cb, hFig)
%LOCAL_RESOLVE_COLORBAR_COLORMAP Resolve the surface colormap for vector redraw.

    cmap = [];

    try
        if isappdata(cb, 'SurfaceColormap')
            cmap = getappdata(cb, 'SurfaceColormap');
        end
    catch
        cmap = [];
    end

    if isempty(cmap)
        try
            if isappdata(hFig, 'SurfaceColormap')
                cmap = getappdata(hFig, 'SurfaceColormap');
            end
        catch
            cmap = [];
        end
    end

    if isempty(cmap)
        axesList = findall(hFig, 'Type', 'axes');
        for k = 1:numel(axesList)
            ax = axesList(k);
            try
                if strcmpi(get(ax, 'Tag'), 'Colorbar')
                    continue;
                end
            catch
            end
            try
                if ~isempty(findall(ax, 'Type', 'patch'))
                    cmap = colormap(ax);
                    break;
                end
            catch
            end
        end
    end

    if isempty(cmap)
        try, cmap = colormap(hFig); catch, end
    end
    if isempty(cmap)
        cmap = parula(256);
    end

    cmap = double(cmap);
    if size(cmap, 2) ~= 3 || isempty(cmap)
        cmap = parula(256);
    end
    cmap = max(0, min(1, cmap));
end

function spec = local_empty_colorbar_spec()
%LOCAL_EMPTY_COLORBAR_SPEC Default captured colorbar values.

    spec = struct();
    spec.Position = [0.85 0.2 0.03 0.6];
    spec.Orientation = 'vertical';
    spec.Limits = [0 1];
    spec.Ticks = [];
    spec.TickLabels = {};
    spec.FontName = 'Arial';
    spec.FontSize = 10;
    spec.Color = [0 0 0];
    spec.LineWidth = 1.0;
    spec.TickLength = 0.012;
    spec.TickLabelInterpreter = 'tex';
    spec.LabelString = '';
    spec.LabelFontName = 'Arial';
    spec.LabelFontSize = 10;
    spec.LabelInterpreter = 'tex';
    spec.LabelColor = [0 0 0];
    spec.Colormap = parula(256);
    spec.UseSymbolForGreek = false;
end

function tf = local_has_radical_colorbar(colorbarSpecs)
%LOCAL_HAS_RADICAL_COLORBAR Return true when any colorbar label needs radical layout.

    tf = false;
    for i = 1:numel(colorbarSpecs)
        if strcmpi(colorbarSpecs(i).Orientation, 'vertical') && ...
                local_label_has_radical(colorbarSpecs(i).LabelString)
            tf = true;
            return;
        end
    end
end

function specs = local_adjust_raster_layers_for_radical_colorbar(specs)
%LOCAL_ADJUST_RASTER_LAYERS_FOR_RADICAL_COLORBAR Reserve space without stretching.

    maxRasterRight = 0.62;
    for i = 1:numel(specs)
        pos = double(specs(i).Position(:))';
        if numel(pos) ~= 4 || any(~isfinite(pos)) || pos(3) <= 0 || pos(4) <= 0
            continue;
        end
        area = pos(3) * pos(4);
        if area < 0.25
            continue;
        end
        if pos(1) + pos(3) > maxRasterRight
            pos(3) = max(0.10, maxRasterRight - pos(1));
            specs(i).Position = pos;
        end
    end
end

function labels = local_normalize_tick_labels(labelsIn)
%LOCAL_NORMALIZE_TICK_LABELS Convert colorbar tick labels to a cell array.

    if isempty(labelsIn)
        labels = {};
    elseif iscell(labelsIn)
        labels = labelsIn;
    elseif isstring(labelsIn)
        labels = cellstr(labelsIn);
    elseif ischar(labelsIn)
        labels = cellstr(labelsIn);
    else
        labels = {};
    end
end

function local_draw_vector_colorbar(parentFig, spec)
%LOCAL_DRAW_VECTOR_COLORBAR Draw raster colorbar body plus vector text/ticks.

    spec = local_adjust_vector_colorbar_layout(spec);

    local_draw_raster_colorbar_body(parentFig, spec);
    local_draw_vector_colorbar_ticks(parentFig, spec);
    if ~isempty(spec.LabelString)
        local_draw_colorbar_label(parentFig, [], spec, spec.Orientation);
    end
end

function local_draw_raster_colorbar_body(parentFig, spec)
%LOCAL_DRAW_RASTER_COLORBAR_BODY Draw the color strip and outline as an image.

    bodyAx = axes('Parent', parentFig, ...
        'Units', 'normalized', ...
        'Position', spec.Position, ...
        'Visible', 'off', ...
        'Color', 'none', ...
        'XLim', [0 1], ...
        'YLim', [0 1], ...
        'YDir', 'normal');

    img = local_make_colorbar_body_image(spec);
    image(bodyAx, [0 1], [0 1], img);
    set(bodyAx, 'YDir', 'normal');
    axis(bodyAx, 'off');
end

function img = local_make_colorbar_body_image(spec)
%LOCAL_MAKE_COLORBAR_BODY_IMAGE Create a raster colorbar strip with outline.

    cmap = double(spec.Colormap);
    if isempty(cmap) || size(cmap, 2) ~= 3
        cmap = parula(256);
    end
    cmap = max(0, min(1, cmap));
    if size(cmap, 1) == 1
        cmap = [cmap; cmap];
    end

    borderColor = local_colorbar_border_color(spec.Color);
    borderPx = max(3, round(max(1.0, double(spec.LineWidth)) * 3));
    if strcmpi(spec.Orientation, 'horizontal')
        nCols = 1024;
        nRows = 80;
        vals = linspace(0, 1, nCols);
        colors = interp1(linspace(0, 1, size(cmap, 1)), cmap, vals, 'linear');
        img = repmat(reshape(colors, [1 nCols 3]), [nRows 1 1]);
    else
        nRows = 1024;
        nCols = 80;
        vals = linspace(0, 1, nRows);
        colors = interp1(linspace(0, 1, size(cmap, 1)), cmap, vals, 'linear');
        img = repmat(reshape(colors, [nRows 1 3]), [1 nCols 1]);
    end

    rowBlock = repmat(reshape(borderColor, [1 1 3]), [borderPx size(img, 2) 1]);
    colBlock = repmat(reshape(borderColor, [1 1 3]), [size(img, 1) borderPx 1]);
    img(1:borderPx, :, :) = rowBlock;
    img(end - borderPx + 1:end, :, :) = rowBlock;
    img(:, 1:borderPx, :) = colBlock;
    img(:, end - borderPx + 1:end, :) = colBlock;
end

function colorValue = local_colorbar_border_color(colorIn)
%LOCAL_COLORBAR_BORDER_COLOR Normalize the captured colorbar outline color.

    if isnumeric(colorIn) && numel(colorIn) == 3
        colorValue = double(colorIn(:))';
        colorValue = max(0, min(1, colorValue));
    else
        colorValue = [0 0 0];
    end
end

function local_draw_vector_colorbar_ticks(parentFig, spec)
%LOCAL_DRAW_VECTOR_COLORBAR_TICKS Draw tick marks and labels as vector objects.

    ticks = local_resolve_colorbar_ticks(spec);
    if isempty(ticks)
        return;
    end

    labels = local_resolve_colorbar_tick_labels(spec, ticks);
    overlayAx = local_create_page_overlay_axes(parentFig);
    tickLen = local_colorbar_tick_length(spec);
    labelGap = local_colorbar_tick_label_gap(spec.FontSize);
    pos = double(spec.Position(:))';
    lim = double(spec.Limits(:))';
    frac = (double(ticks(:)) - lim(1)) ./ (lim(2) - lim(1));
    frac = max(0, min(1, frac));
    lineWidth = max(1.0, double(spec.LineWidth));

    if strcmpi(spec.Orientation, 'horizontal')
        y0 = pos(2);
        y1 = y0 - tickLen;
        for i = 1:numel(ticks)
            x = pos(1) + frac(i) * pos(3);
            line(overlayAx, [x x], [y0 y1], ...
                'Color', spec.Color, ...
                'LineWidth', lineWidth, ...
                'Clipping', 'off');
            local_draw_mixed_font_text(overlayAx, [x, y1 - labelGap], labels{i}, ...
                spec.FontName, 'Symbol', spec.FontSize, spec.Color, 0, 'center', 'top', ...
                spec.UseSymbolForGreek);
        end
    else
        x0 = pos(1) + pos(3);
        x1 = x0 + tickLen;
        for i = 1:numel(ticks)
            y = pos(2) + frac(i) * pos(4);
            line(overlayAx, [x0 x1], [y y], ...
                'Color', spec.Color, ...
                'LineWidth', lineWidth, ...
                'Clipping', 'off');
            local_draw_mixed_font_text(overlayAx, [x1 + labelGap, y], labels{i}, ...
                spec.FontName, 'Symbol', spec.FontSize, spec.Color, 0, 'left', 'middle', ...
                spec.UseSymbolForGreek);
        end
    end
end

function ticks = local_resolve_colorbar_ticks(spec)
%LOCAL_RESOLVE_COLORBAR_TICKS Return explicit or fallback colorbar ticks.

    ticks = double(spec.Ticks(:));
    ticks = ticks(isfinite(ticks));
    if isempty(ticks)
        ticks = linspace(spec.Limits(1), spec.Limits(2), 5)';
    end
end

function labels = local_resolve_colorbar_tick_labels(spec, ticks)
%LOCAL_RESOLVE_COLORBAR_TICK_LABELS Return labels matching the tick vector.

    labels = spec.TickLabels(:);
    if numel(labels) ~= numel(ticks)
        labels = arrayfun(@(x) sprintf('%g', x), ticks(:), 'UniformOutput', false);
    end
end

function len = local_colorbar_tick_length(spec)
%LOCAL_COLORBAR_TICK_LENGTH Return tick length in normalized page units.

    rawLen = 0.012;
    try
        if ~isempty(spec.TickLength) && isfinite(double(spec.TickLength))
            rawLen = double(spec.TickLength);
        end
    catch
        rawLen = 0.012;
    end
    if rawLen < 0.05
        len = max(0.012, rawLen * max(spec.Position(3), spec.Position(4)) * 2);
    else
        len = rawLen;
    end
    len = min(0.04, max(0.010, len));
end

function gap = local_colorbar_tick_label_gap(fontSize)
%LOCAL_COLORBAR_TICK_LABEL_GAP Return spacing between ticks and labels.

    gap = 0.010 * max(0.8, double(fontSize) / 27);
end

function spec = local_adjust_vector_colorbar_layout(spec)
%LOCAL_ADJUST_VECTOR_COLORBAR_LAYOUT Keep radical labels inside the PDF page.

    if ~strcmpi(spec.Orientation, 'vertical') || ~local_label_has_radical(spec.LabelString)
        return;
    end

    pos = double(spec.Position(:))';
    if numel(pos) ~= 4 || any(~isfinite(pos)) || pos(3) <= 0 || pos(4) <= 0
        return;
    end

    maxColorbarX = 0.68;
    pos(1) = min(pos(1), maxColorbarX);
    pos(1) = max(0.02, pos(1));
    spec.Position = pos;
end

function local_draw_colorbar_label(parentFig, ~, spec, orientation)
%LOCAL_DRAW_COLORBAR_LABEL Draw standard or radical-aware colorbar labels.

    if local_label_has_radical(spec.LabelString)
        local_draw_radical_colorbar_label(parentFig, spec, orientation);
        return;
    end

    local_draw_standard_colorbar_label(parentFig, spec, orientation);
end

function overlayAx = local_create_page_overlay_axes(parentFig)
%LOCAL_CREATE_PAGE_OVERLAY_AXES Create a normalized page-coordinate overlay.

    overlayAx = axes('Parent', parentFig, ...
        'Units', 'normalized', ...
        'Position', [0 0 1 1], ...
        'Visible', 'off', ...
        'Color', 'none', ...
        'XLim', [0 1], ...
        'YLim', [0 1], ...
        'HitTest', 'off');
    hold(overlayAx, 'on');
end

function local_draw_standard_colorbar_label(parentFig, spec, orientation)
%LOCAL_DRAW_STANDARD_COLORBAR_LABEL Draw a non-radical colorbar label manually.

    overlayAx = local_create_page_overlay_axes(parentFig);
    pos = double(spec.Position(:))';
    if strcmpi(orientation, 'horizontal')
        point = [pos(1) + pos(3) / 2, max(0.03, pos(2) - 0.12)];
        rotation = 0;
        horizontalAlignment = 'center';
    else
        tickLen = local_colorbar_tick_length(spec);
        point = [min(0.94, pos(1) + pos(3) + tickLen + 0.13), pos(2) + pos(4) / 2];
        rotation = 90;
        horizontalAlignment = 'center';
    end

    handles = local_draw_mixed_font_text(overlayAx, point, spec.LabelString, ...
        spec.LabelFontName, 'Symbol', spec.LabelFontSize, spec.LabelColor, ...
        rotation, horizontalAlignment, 'middle', spec.UseSymbolForGreek);
    local_shift_label_handles_into_page(handles);
end

function tf = local_label_has_radical(labelString)
%LOCAL_LABEL_HAS_RADICAL Return true for plain labels containing sqrt text.

    tf = contains(char(string(labelString)), '√(');
end

function local_draw_radical_colorbar_label(parentFig, spec, orientation)
%LOCAL_DRAW_RADICAL_COLORBAR_LABEL Draw sqrt labels without LaTeX.

    tokens = local_tokenize_radical_label(spec.LabelString);
    if isempty(tokens)
        return;
    end

    overlayAx = axes('Parent', parentFig, ...
        'Units', 'normalized', ...
        'Position', [0 0 1 1], ...
        'Visible', 'off', ...
        'Color', 'none', ...
        'XLim', [0 1], ...
        'YLim', [0 1], ...
        'HitTest', 'off');
    hold(overlayAx, 'on');

    if strcmpi(orientation, 'horizontal')
        rotation = 0;
        centerPoint = [spec.Position(1) + spec.Position(3) / 2, max(0.03, spec.Position(2) - 0.13)];
        direction = [1 0];
        normal = [0 1];
    else
        rotation = 90;
        centerPoint = [local_vertical_radical_label_x(spec), ...
            spec.Position(2) + spec.Position(4) / 2];
        direction = [0 1];
        normal = [-1 0];
    end

    drawSpec = local_fit_radical_label_font_size(overlayAx, tokens, spec, rotation, orientation);
    metrics = local_measure_radical_tokens(overlayAx, tokens, drawSpec, rotation);
    gap = local_label_gap(drawSpec.LabelFontSize);
    totalLength = sum([metrics.Length]) + gap * max(0, numel(metrics) - 1);
    cursor = -totalLength / 2;
    drawnHandles = {};

    for i = 1:numel(tokens)
        token = tokens(i);
        metric = metrics(i);
        if strcmp(token.Type, 'radical')
            tokenHandles = local_draw_radical_token(overlayAx, centerPoint, direction, normal, cursor, ...
                token.Text, metric, drawSpec, rotation);
            drawnHandles = [drawnHandles, tokenHandles]; %#ok<AGROW>
        else
            textHandles = local_draw_mixed_font_text(overlayAx, centerPoint + direction * cursor, ...
                token.Text, drawSpec.LabelFontName, 'Symbol', drawSpec.LabelFontSize, ...
                drawSpec.LabelColor, rotation, 'left', 'middle', drawSpec.UseSymbolForGreek);
            drawnHandles = [drawnHandles, textHandles]; %#ok<AGROW>
        end
        cursor = cursor + metric.Length + gap;
    end

    local_shift_label_handles_into_page(drawnHandles);
end

function x = local_vertical_radical_label_x(spec)
%LOCAL_VERTICAL_RADICAL_LABEL_X Return a conservative x anchor for rotated labels.

    fontScale = max(0.8, double(spec.LabelFontSize) / 32);
    offset = 0.125 * fontScale;
    x = spec.Position(1) + spec.Position(3) + offset;
    x = min(0.84, x);
    x = max(spec.Position(1) + spec.Position(3) + 0.06, x);
end

function specOut = local_fit_radical_label_font_size(ax, tokens, specIn, rotation, orientation)
%LOCAL_FIT_RADICAL_LABEL_FONT_SIZE Reduce long radical labels to fit the page.

    specOut = specIn;
    if ~strcmpi(orientation, 'vertical')
        return;
    end

    metrics = local_measure_radical_tokens(ax, tokens, specOut, rotation);
    gap = local_label_gap(specOut.LabelFontSize);
    totalLength = sum([metrics.Length]) + gap * max(0, numel(metrics) - 1);
    maxLength = min(0.72, max(0.55, double(specOut.Position(4)) + 0.12));
    if totalLength <= maxLength
        return;
    end

    scale = max(0.45, maxLength / totalLength);
    specOut.LabelFontSize = max(12, double(specOut.LabelFontSize) * scale);
end

function tokens = local_tokenize_radical_label(labelString)
%LOCAL_TOKENIZE_RADICAL_LABEL Split a plain label into text and radical tokens.

    labelString = char(string(labelString));
    starts = strfind(labelString, '√(');
    tokens = repmat(struct('Type', '', 'Text', ''), 0, 1);
    cursor = 1;

    for i = 1:numel(starts)
        startIdx = starts(i);
        if startIdx < cursor
            continue;
        end

        closeIdx = local_find_closing_parenthesis(labelString, startIdx + 1);
        if isempty(closeIdx)
            continue;
        end

        if startIdx > cursor
            tokens(end + 1) = struct('Type', 'text', 'Text', labelString(cursor:startIdx - 1)); %#ok<AGROW>
        end

        radicand = labelString(startIdx + 2:closeIdx - 1);
        tokens(end + 1) = struct('Type', 'radical', 'Text', radicand); %#ok<AGROW>
        cursor = closeIdx + 1;
    end

    if cursor <= numel(labelString)
        tokens(end + 1) = struct('Type', 'text', 'Text', labelString(cursor:end)); %#ok<AGROW>
    end

    keep = true(numel(tokens), 1);
    for i = 1:numel(tokens)
        keep(i) = ~isempty(strtrim(tokens(i).Text));
    end
    tokens = tokens(keep);
end

function closeIdx = local_find_closing_parenthesis(labelString, openIdx)
%LOCAL_FIND_CLOSING_PARENTHESIS Find the matching parenthesis in a label.

    closeIdx = [];
    depth = 0;
    for i = openIdx:numel(labelString)
        if labelString(i) == '('
            depth = depth + 1;
        elseif labelString(i) == ')'
            depth = depth - 1;
            if depth == 0
                closeIdx = i;
                return;
            end
        end
    end
end

function metrics = local_measure_radical_tokens(ax, tokens, spec, rotation)
%LOCAL_MEASURE_RADICAL_TOKENS Measure label token lengths in normalized units.

    metrics = repmat(struct('Length', 0, 'RootLength', 0, 'RadicandLength', 0), numel(tokens), 1);
    for i = 1:numel(tokens)
        if strcmp(tokens(i).Type, 'radical')
            rootLength = local_measure_text_length(ax, '√', local_radical_root_font_name(), ...
                spec.LabelFontSize * 1.08, rotation);
            radLength = local_measure_mixed_text_length(ax, tokens(i).Text, ...
                spec.LabelFontName, 'Symbol', spec.LabelFontSize, rotation, ...
                spec.UseSymbolForGreek);
            metrics(i).RootLength = rootLength;
            metrics(i).RadicandLength = radLength;
            metrics(i).Length = rootLength * 0.70 + radLength;
        else
            metrics(i).Length = local_measure_mixed_text_length(ax, tokens(i).Text, ...
                spec.LabelFontName, 'Symbol', spec.LabelFontSize, rotation, ...
                spec.UseSymbolForGreek);
        end
    end
end

function len = local_measure_mixed_text_length(ax, labelString, baseFontName, greekFontName, fontSize, rotation, useSymbolForGreek)
%LOCAL_MEASURE_MIXED_TEXT_LENGTH Measure mixed-font text along the label direction.

    if nargin < 7 || isempty(useSymbolForGreek)
        useSymbolForGreek = false;
    end
    if ~useSymbolForGreek
        len = local_measure_text_length(ax, labelString, baseFontName, fontSize, rotation, 'none');
        return;
    end

    runs = local_split_greek_runs(labelString);
    len = 0;
    for i = 1:numel(runs)
        [measureText, measureFont, interpreter] = local_mixed_font_run_properties( ...
            runs(i).Text, baseFontName, greekFontName, runs(i).IsGreek);
        len = len + local_measure_text_length(ax, measureText, measureFont, ...
            fontSize, rotation, interpreter);
    end
end

function len = local_measure_text_length(ax, labelString, fontName, fontSize, rotation, interpreter)
%LOCAL_MEASURE_TEXT_LENGTH Measure a text extent along the label direction.

    if nargin < 6 || isempty(interpreter)
        interpreter = 'none';
    end
    hText = text(ax, 0.5, 0.5, labelString, ...
        'FontName', fontName, ...
        'FontSize', fontSize, ...
        'Interpreter', interpreter, ...
        'Rotation', rotation, ...
        'Visible', 'off', ...
        'Units', 'data');
    drawnow;
    try
        ext = hText.Extent;
        if rotation == 0
            len = max(0.001, ext(3));
        else
            len = max(0.001, ext(4));
        end
    catch
        len = 0.012 * max(1, strlength(string(labelString)));
    end
    try, delete(hText); catch, end
end

function gap = local_label_gap(fontSize)
%LOCAL_LABEL_GAP Return token gap in normalized page units.

    gap = 0.004 * max(0.8, double(fontSize) / 24);
end

function handles = local_draw_radical_token(ax, centerPoint, direction, normal, cursor, radicand, metric, spec, rotation)
%LOCAL_DRAW_RADICAL_TOKEN Draw one radical token as glyph, text, and overbar.

    rootPoint = centerPoint + direction * cursor;
    hRoot = local_draw_label_text(ax, rootPoint, '√', local_radical_root_font_name(), ...
        spec.LabelFontSize * 1.08, spec.LabelColor, rotation);

    radStart = cursor + metric.RootLength * 1.0;
    radEnd = radStart + metric.RadicandLength;
    radPoint = centerPoint + direction * radStart;
    radicandHandles = local_draw_mixed_font_text(ax, radPoint, radicand, ...
        spec.LabelFontName, 'Symbol', spec.LabelFontSize, spec.LabelColor, ...
        rotation, 'left', 'middle', spec.UseSymbolForGreek);

    lineOffset = 0.01065 * max(0.8, double(spec.LabelFontSize) / 24);
    linePad = 0.002;
    lineStart = cursor + metric.RootLength * 0.888;
    p1 = centerPoint + direction * (lineStart + linePad) + normal * lineOffset;
    p2 = centerPoint + direction * (radEnd - linePad) + normal * lineOffset;
    overbarLineWidth = max(2.0, double(spec.LineWidth));
    hLine = line(ax, [p1(1) p2(1)], [p1(2) p2(2)], ...
        'Color', spec.LabelColor, ...
        'LineWidth', overbarLineWidth, ...
        'Clipping', 'off');
    handles = [{hRoot}, radicandHandles, {hLine}];
end

function fontName = local_radical_root_font_name()
%LOCAL_RADICAL_ROOT_FONT_NAME Return the dedicated square-root glyph font.

    fontName = 'STIXGeneral';
end

function local_shift_label_handles_into_page(handles)
%LOCAL_SHIFT_LABEL_HANDLES_INTO_PAGE Move radical labels inside the page bounds.

    if isempty(handles)
        return;
    end

    drawnow;
    minX = inf;
    maxX = -inf;
    minY = inf;
    maxY = -inf;
    for i = 1:numel(handles)
        h = handles{i};
        if ~isgraphics(h)
            continue;
        end
        try
            objType = get(h, 'Type');
            if strcmpi(objType, 'text')
                ext = get(h, 'Extent');
                minX = min(minX, ext(1));
                maxX = max(maxX, ext(1) + ext(3));
                minY = min(minY, ext(2));
                maxY = max(maxY, ext(2) + ext(4));
            elseif strcmpi(objType, 'line')
                xData = get(h, 'XData');
                yData = get(h, 'YData');
                minX = min(minX, min(xData));
                maxX = max(maxX, max(xData));
                minY = min(minY, min(yData));
                maxY = max(maxY, max(yData));
            end
        catch
        end
    end

    if ~isfinite(minX) || ~isfinite(maxX)
        return;
    end

    shiftX = 0;
    if maxX > 0.98
        shiftX = shiftX - (maxX - 0.98);
    end
    if minX + shiftX < 0.02
        shiftX = shiftX + (0.02 - (minX + shiftX));
    end
    shiftY = 0;
    if maxY > 0.98
        shiftY = shiftY - (maxY - 0.98);
    end
    if minY + shiftY < 0.02
        shiftY = shiftY + (0.02 - (minY + shiftY));
    end
    if abs(shiftX) < eps && abs(shiftY) < eps
        return;
    end

    for i = 1:numel(handles)
        h = handles{i};
        if ~isgraphics(h)
            continue;
        end
        try
            objType = get(h, 'Type');
            if strcmpi(objType, 'text')
                pos = get(h, 'Position');
                pos(1) = pos(1) + shiftX;
                pos(2) = pos(2) + shiftY;
                set(h, 'Position', pos);
            elseif strcmpi(objType, 'line')
                set(h, 'XData', get(h, 'XData') + shiftX);
                set(h, 'YData', get(h, 'YData') + shiftY);
            end
        catch
        end
    end
end

function hText = local_draw_label_text(ax, point, labelString, fontName, fontSize, colorValue, rotation)
%LOCAL_DRAW_LABEL_TEXT Draw one label text segment.

    hText = text(ax, point(1), point(2), labelString, ...
        'FontName', fontName, ...
        'FontSize', fontSize, ...
        'Interpreter', 'none', ...
        'Rotation', rotation, ...
        'Color', colorValue, ...
        'HorizontalAlignment', 'left', ...
        'VerticalAlignment', 'middle', ...
        'Clipping', 'off');
end

function handles = local_draw_mixed_font_text(ax, point, labelString, baseFontName, greekFontName, fontSize, colorValue, rotation, horizontalAlignment, verticalAlignment, useSymbolForGreek)
%LOCAL_DRAW_MIXED_FONT_TEXT Draw text with Greek runs in Symbol and other runs in Arial.

    labelString = char(string(labelString));
    if isempty(labelString)
        handles = {};
        return;
    end
    if nargin < 11 || isempty(useSymbolForGreek)
        useSymbolForGreek = false;
    end

    if ~useSymbolForGreek
        handles = {text(ax, point(1), point(2), labelString, ...
            'FontName', baseFontName, ...
            'FontSize', fontSize, ...
            'Interpreter', 'none', ...
            'Rotation', rotation, ...
            'Color', colorValue, ...
            'HorizontalAlignment', horizontalAlignment, ...
            'VerticalAlignment', verticalAlignment, ...
            'Clipping', 'off')};
        return;
    end

    runs = local_split_greek_runs(labelString);
    if isempty(runs)
        handles = {};
        return;
    end

    direction = [cosd(double(rotation)), sind(double(rotation))];
    lengths = zeros(1, numel(runs));
    for i = 1:numel(runs)
        [measureText, measureFont, interpreter] = local_mixed_font_run_properties( ...
            runs(i).Text, baseFontName, greekFontName, runs(i).IsGreek);
        lengths(i) = local_measure_text_length(ax, measureText, measureFont, ...
            fontSize, rotation, interpreter);
    end

    totalLength = sum(lengths);
    align = lower(strtrim(char(string(horizontalAlignment))));
    if strcmp(align, 'center')
        cursor = -totalLength / 2;
    elseif strcmp(align, 'right')
        cursor = -totalLength;
    else
        cursor = 0;
    end

    handles = cell(1, numel(runs));
    for i = 1:numel(runs)
        runPoint = point + direction * cursor;
        [drawText, drawFont, interpreter] = local_mixed_font_run_properties( ...
            runs(i).Text, baseFontName, greekFontName, runs(i).IsGreek);
        handles{i} = text(ax, runPoint(1), runPoint(2), drawText, ...
            'FontName', drawFont, ...
            'FontSize', fontSize, ...
            'Interpreter', interpreter, ...
            'Rotation', rotation, ...
            'Color', colorValue, ...
            'HorizontalAlignment', 'left', ...
            'VerticalAlignment', verticalAlignment, ...
            'Clipping', 'off');
        cursor = cursor + lengths(i);
    end
end

function [drawText, fontName, interpreter] = local_mixed_font_run_properties(runText, baseFontName, greekFontName, isGreek)
%LOCAL_MIXED_FONT_RUN_PROPERTIES Return text properties for one mixed-font run.

    if isGreek
        drawText = ['\fontname{' char(string(greekFontName)) '}' char(string(runText))];
        fontName = baseFontName;
        interpreter = 'tex';
    else
        drawText = char(string(runText));
        fontName = baseFontName;
        interpreter = 'none';
    end
end

function runs = local_split_greek_runs(labelString)
%LOCAL_SPLIT_GREEK_RUNS Split text into adjacent Greek and non-Greek runs.

    labelString = char(string(labelString));
    runs = repmat(struct('Text', '', 'IsGreek', false), 0, 1);
    if isempty(labelString)
        return;
    end

    isGreek = local_chars_are_greek(labelString);
    startIdx = 1;
    current = isGreek(1);
    for idx = 2:numel(labelString)
        if isGreek(idx) ~= current
            runs(end + 1) = struct('Text', labelString(startIdx:idx - 1), 'IsGreek', current); %#ok<AGROW>
            startIdx = idx;
            current = isGreek(idx);
        end
    end
    runs(end + 1) = struct('Text', labelString(startIdx:end), 'IsGreek', current);
end

function tf = local_chars_are_greek(labelString)
%LOCAL_CHARS_ARE_GREEK Return true for Unicode Greek code points.

    codes = double(char(string(labelString)));
    tf = (codes >= hex2dec('0370') & codes <= hex2dec('03FF')) | ...
        (codes >= hex2dec('1F00') & codes <= hex2dec('1FFF'));
end

function local_delete_if_exists(filePath)
%LOCAL_DELETE_IF_EXISTS Delete a temporary file if it exists.

    if exist(filePath, 'file') == 2
        try, delete(filePath); catch, end
    end
end

function local_close_if_handle(h)
%LOCAL_CLOSE_IF_HANDLE Close a figure handle if it is still valid.

    if ishandle(h)
        try, close(h); catch, end
    end
end

function tf = local_is_background_spec(x)
%LOCAL_IS_BACKGROUND_SPEC Validate BackgroundColor input.
%
% Accepts:
%   - char or string scalar (e.g., 'white','black','none','k')
%   - numeric 1x3 RGB in [0,1]
    tf = false;

    if ischar(x) || (isstring(x) && isscalar(x))
        tf = true;
        return;
    end

    if isnumeric(x) && numel(x) == 3 && all(isfinite(x(:)))
        x = double(x(:))';
        tf = all(x >= 0) && all(x <= 1);
        return;
    end
end

function bg = local_normalize_background_spec(x)
%LOCAL_NORMALIZE_BACKGROUND_SPEC Normalize background spec to MATLAB form.
%
% Returns:
%   - 'none' as char
%   - color name as char
%   - 1x3 double RGB
    if isstring(x)
        x = char(x);
    end

    if ischar(x)
        s = strtrim(x);
        if isempty(s)
            bg = 'white';
            return;
        end
        bg = s;
        return;
    end

    % Numeric RGB
    bg = double(x(:))';
end
