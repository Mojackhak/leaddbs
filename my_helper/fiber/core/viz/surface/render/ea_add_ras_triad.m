function triad = ea_add_ras_triad(hMainAx, varargin)
%EA_ADD_RAS_TRIAD Add an interactive RAS orientation triad to a 3D axes.
%
%   triad = EA_ADD_RAS_TRIAD(hMainAx)
%   triad = EA_ADD_RAS_TRIAD(hMainAx, 'Name', value, ...)
%
% This function creates a small inset axes in the parent figure that shows
% three orthogonal arrows labeled:
%   R : +X (Right)
%   A : +Y (Anterior)
%   S : +Z (Superior)
%
% The inset triad automatically follows the ORIENTATION of the main axes
% camera, but it does NOT follow zoom (CameraViewAngle / camera distance).
% This keeps the triad size visually stable while the user changes the view.
%
% Inputs
%   hMainAx : handle to a 3D axes (e.g., the axes created by ea_mnifigure).
%
% Name-Value pairs (optional)
%   'Colors'      : 3x3 RGB matrix [R; A; S] or a struct with fields
%                   .R .A .S (each 1x3 RGB). Default:
%                     R = [1 0 0], A = [0 1 0], S = [0 0 1]
%   'Location'    : 'southwest' (default), 'southeast', 'northwest',
%                   'northeast', or a 1x4 normalized position vector.
%   'Size'        : scalar in (0,1). Normalized width/height. Default: 0.18
%   'Padding'     : scalar in [0,0.2). Normalized margin. Default: 0.02
%   'AxesPadding' : internal axes padding as a fraction of Length.
%                   Default: 0.45
%   'Length'      : arrow length in triad axes units. Default: 1
%   'LineWidth'   : arrow line width. Default: 2
%   'HeadSize'    : arrow head size (quiver 'MaxHeadSize'). Default: []
%   'FontSize'    : label font size. Default: 10
%   'FontName'    : label font name. Default: 'Arial'
%   'ShowLabels'  : show the R, A, and S letters. Default: true
%   'LabelOffset' : offset from arrow tip as a fraction of Length.
%                   Default: 0.12
%   'Projection'  : triad projection. Default: 'orthographic'
%   'CameraViewAngle' : fixed triad CameraViewAngle (deg). Default: 10
%   'Box'         : 'on' or 'off'. Default: 'off'
%   'BackgroundColor' : 1x3 RGB. Default: [1 1 1]
%   'BackgroundAlpha' : scalar in [0,1]. Default: 0 (transparent)
%
% Output
%   triad : struct with handles and listener objects:
%       .axes, .qR, .qA, .qS, .tR, .tA, .tS, .listeners, .refresh
%
% Notes
%   - The triad is designed to be non-interactive (it should not intercept
%     rotate/zoom/pan actions on the main axes).
%   - This is a visual orientation marker only; it does not modify data.

    if nargin < 1 || ~ishandle(hMainAx)
        error('EA_ADD_RAS_TRIAD:BadAxes', 'hMainAx must be a valid axes handle.');
    end

    % Parse inputs.
    ip = inputParser;
    ip.FunctionName = mfilename;

    addParameter(ip, 'Colors', [], @(x) isempty(x) || (isnumeric(x) && isequal(size(x), [3 3])) || isstruct(x));
    addParameter(ip, 'Location', 'southwest', @(x) (ischar(x) || (isstring(x) && isscalar(x))) || (isnumeric(x) && numel(x) == 4));
    addParameter(ip, 'Size', 0.18, @(x) isnumeric(x) && isscalar(x) && x > 0 && x < 1);
    addParameter(ip, 'Padding', 0.02, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x < 0.2);
    addParameter(ip, 'AxesPadding', 0.45, @(x) isnumeric(x) && isscalar(x) && x >= 0);

    addParameter(ip, 'Length', 1, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'LineWidth', 2, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'HeadSize', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'FontSize', 10, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'FontName', 'Arial', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'ShowLabels', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'LabelOffset', 0.12, @(x) isnumeric(x) && isscalar(x) && x >= 0);

    addParameter(ip, 'Projection', 'orthographic', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'CameraViewAngle', 10, @(x) isnumeric(x) && isscalar(x) && x > 0);

    addParameter(ip, 'Box', 'off', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'BackgroundColor', [1 1 1], @(x) isnumeric(x) && numel(x) == 3);
    addParameter(ip, 'BackgroundAlpha', 0, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);

    parse(ip, varargin{:});
    p = ip.Results;

    % Resolve colors.
    [colR, colA, colS] = local_parse_colors(p.Colors);

    % Create inset axes.
    hFig = ancestor(hMainAx, 'figure');

    % Preserve current axes so we do not steal focus from the main scene.
    hOldAx = [];
    try
        hOldAx = get(hFig, 'CurrentAxes');
    catch
    end

    pos = local_position_from_location(p.Location, p.Size, p.Padding);

    hTriadAx = axes('Parent', hFig, ...
        'Units', 'normalized', ...
        'Position', pos, ...
        'Color', p.BackgroundColor, ...
        'Visible', 'off', ...
        'HitTest', 'off');

    % Tag the triad axes so it can be found and refreshed programmatically.
    try
        hTriadAx.Tag = 'EA_RAS_TRIAD_AXES';
    catch
    end

    % Make axes background optionally transparent (best effort).
    try
        if p.BackgroundAlpha == 0
            hTriadAx.Color = 'none';
        else
            hTriadAx.Color = p.BackgroundColor;
        end
    catch
    end

    % Ensure it stays out of the interaction stack.
    try
        hTriadAx.PickableParts = 'none';
    catch
    end

    hold(hTriadAx, 'on');

    L = p.Length;
    off = p.LabelOffset * L;

    % Fixed limits so the triad does not autoscale with camera updates.
    pad = double(p.AxesPadding) * L;
    upperPad = max(2 * off, pad);
    try
        set(hTriadAx, ...
            'XLim', [-pad, L + upperPad], 'XLimMode', 'manual', ...
            'YLim', [-pad, L + upperPad], 'YLimMode', 'manual', ...
            'ZLim', [-pad, L + upperPad], 'ZLimMode', 'manual');
    catch
        xlim(hTriadAx, [-pad, L + upperPad]);
        ylim(hTriadAx, [-pad, L + upperPad]);
        zlim(hTriadAx, [-pad, L + upperPad]);
    end

    axis(hTriadAx, 'equal');
    try
        axis(hTriadAx, 'off');
    catch
    end

    % Keep aspect ratios and camera view angle stable.
    try
        hTriadAx.DataAspectRatio = [1 1 1];
        hTriadAx.DataAspectRatioMode = 'manual';
    catch
    end
    try
        hTriadAx.PlotBoxAspectRatio = [1 1 1];
        hTriadAx.PlotBoxAspectRatioMode = 'manual';
    catch
    end
    try
        hTriadAx.CameraViewAngleMode = 'manual';
        hTriadAx.CameraViewAngle = p.CameraViewAngle;
    catch
        try
            camva(hTriadAx, p.CameraViewAngle);
        catch
        end
    end

    % Projection (default: orthographic for stable perceived size).
    try
        camproj(hTriadAx, char(p.Projection));
    catch
    end

    try
        box(hTriadAx, char(p.Box));
    catch
    end

    % Draw R, A, S arrows.
    qR = quiver3(hTriadAx, 0, 0, 0, L, 0, 0, 0, 'Color', colR, 'LineWidth', p.LineWidth);
    qA = quiver3(hTriadAx, 0, 0, 0, 0, L, 0, 0, 'Color', colA, 'LineWidth', p.LineWidth);
    qS = quiver3(hTriadAx, 0, 0, 0, 0, 0, L, 0, 'Color', colS, 'LineWidth', p.LineWidth);
    try, qR.Clipping = 'off'; catch, end
    try, qA.Clipping = 'off'; catch, end
    try, qS.Clipping = 'off'; catch, end

    % Arrow head size (best effort).
    if ~isempty(p.HeadSize)
        try, qR.MaxHeadSize = p.HeadSize; catch, end
        try, qA.MaxHeadSize = p.HeadSize; catch, end
        try, qS.MaxHeadSize = p.HeadSize; catch, end
    end

    % Try to enforce manual scaling.
    local_set_quiver_noscale(qR);
    local_set_quiver_noscale(qA);
    local_set_quiver_noscale(qS);

    fn = char(p.FontName);
    labelVisibility = 'on';
    if ~p.ShowLabels
        labelVisibility = 'off';
    end

    % Labels near arrow tips.
    tR = text(hTriadAx, L + off, 0, 0, 'R', 'Color', colR, 'FontWeight', 'bold', ...
        'FontSize', p.FontSize, 'FontName', fn, 'HorizontalAlignment', 'center', ...
        'VerticalAlignment', 'middle', 'HitTest', 'off', 'Clipping', 'off', ...
        'Visible', labelVisibility, 'Tag', 'EA_RAS_TRIAD_LABEL_R');
    tA = text(hTriadAx, 0, L + off, 0, 'A', 'Color', colA, 'FontWeight', 'bold', ...
        'FontSize', p.FontSize, 'FontName', fn, 'HorizontalAlignment', 'center', ...
        'VerticalAlignment', 'middle', 'HitTest', 'off', 'Clipping', 'off', ...
        'Visible', labelVisibility, 'Tag', 'EA_RAS_TRIAD_LABEL_A');
    tS = text(hTriadAx, 0, 0, L + off, 'S', 'Color', colS, 'FontWeight', 'bold', ...
        'FontSize', p.FontSize, 'FontName', fn, 'HorizontalAlignment', 'center', ...
        'VerticalAlignment', 'middle', 'HitTest', 'off', 'Clipping', 'off', ...
        'Visible', labelVisibility, 'Tag', 'EA_RAS_TRIAD_LABEL_S');
    try
        uistack([tR, tA, tS], 'top');
    catch
    end

    % Sync triad orientation with main axes.
    local_update_view();

    listeners = local_attach_listeners();

    % Package output.
    triad = struct();
    triad.axes = hTriadAx;
    triad.qR = qR;
    triad.qA = qA;
    triad.qS = qS;
    triad.tR = tR;
    triad.tA = tA;
    triad.tS = tS;
    triad.listeners = listeners;
    triad.refresh = @local_update_view;

    % Store references so listeners are not garbage-collected.
    ud = struct();
    ud.listeners = listeners;
    ud.main_axes = hMainAx;
    ud.refresh = @local_update_view;
    set(hTriadAx, 'UserData', ud);

    % Restore the previously active axes (best effort).
    try
        if ~isempty(hOldAx) && ishandle(hOldAx)
            set(hFig, 'CurrentAxes', hOldAx);
        else
            set(hFig, 'CurrentAxes', hMainAx);
        end
    catch
    end

    % ---------------------------------------------------------------------
    % Nested helpers (share workspace)
    % ---------------------------------------------------------------------
    function local_update_view(varargin)
        if ~ishandle(hMainAx) || ~ishandle(hTriadAx)
            return;
        end

        % Synchronize ORIENTATION using camera vectors, but keep triad camera
        % view angle fixed (so the triad does not resize when the main camera
        % zooms).
        try
            cp = get(hMainAx, 'CameraPosition');
            ct = get(hMainAx, 'CameraTarget');
            cu = get(hMainAx, 'CameraUpVector');
        catch
            cp = []; ct = []; cu = [];
        end

        if isempty(cp) || isempty(ct)
            % Fallback: copy View angles.
            try
                set(hTriadAx, 'View', get(hMainAx, 'View'));
            catch
                try
                    view(hTriadAx, get(hMainAx, 'View'));
                catch
                end
            end
            try
                camtarget(hTriadAx, [0 0 0]);
            catch
            end
            return;
        end

        dir = double(cp(:)' - ct(:)');
        if ~all(isfinite(dir)) || norm(dir) == 0
            return;
        end
        dir = dir / norm(dir);

        % Fixed camera distance for the triad.
        dist = 6 * L;

        try
            camtarget(hTriadAx, [0 0 0]);
        catch
        end
        try
            campos(hTriadAx, dir * dist);
        catch
        end

        % Camera up vector (best effort).
        if ~isempty(cu) && all(isfinite(cu))
            try
                camup(hTriadAx, double(cu(:)'));
            catch
            end
        end
    end

    function Ls = local_attach_listeners()
        % Attach one-way listeners from main axes to triad axes.
        Ls = event.listener.empty(0,1);
        try
            Ls(end+1,1) = addlistener(hMainAx, 'CameraUpVector', 'PostSet', @local_update_view);
        catch
        end
        try
            Ls(end+1,1) = addlistener(hMainAx, 'CameraPosition', 'PostSet', @local_update_view);
        catch
        end
        try
            Ls(end+1,1) = addlistener(hMainAx, 'CameraTarget', 'PostSet', @local_update_view);
        catch
        end
        try
            % View changes (rotate3d updates this)
            Ls(end+1,1) = addlistener(hMainAx, 'View', 'PostSet', @local_update_view);
        catch
        end

        % Fallback: if listeners are not supported, try linkprop.
        if isempty(Ls)
            try
                hl = linkprop([hMainAx, hTriadAx], {'View','CameraUpVector'});
                % Store link in UserData to keep it alive.
                ud = get(hTriadAx, 'UserData');
                ud.link = hl;
                set(hTriadAx, 'UserData', ud);
            catch
            end
        end
    end
end

% -------------------------------------------------------------------------
% Local helper functions (file scope)
% -------------------------------------------------------------------------

function [colR, colA, colS] = local_parse_colors(colorsIn)
%LOCAL_PARSE_COLORS Parse color definitions for R, A, S.

    colR = [1 0 0];
    colA = [0 1 0];
    colS = [0 0 1];

    if isempty(colorsIn)
        return;
    end

    if isnumeric(colorsIn) && isequal(size(colorsIn), [3 3])
        colR = colorsIn(1,:);
        colA = colorsIn(2,:);
        colS = colorsIn(3,:);
        return;
    end

    if isstruct(colorsIn)
        if isfield(colorsIn, 'R'), colR = colorsIn.R; end
        if isfield(colorsIn, 'A'), colA = colorsIn.A; end
        if isfield(colorsIn, 'S'), colS = colorsIn.S; end
        return;
    end

    error('EA_ADD_RAS_TRIAD:BadColors', ...
        'Colors must be a 3x3 RGB matrix, a struct with fields R/A/S, or empty.');
end

function pos = local_position_from_location(location, sizeNorm, pad)
%LOCAL_POSITION_FROM_LOCATION Convert a location keyword to a normalized position.

    if isnumeric(location) && numel(location) == 4
        pos = double(location(:))';
        return;
    end

    loc = lower(strtrim(char(location)));

    switch loc
        case 'southwest'
            pos = [pad, pad, sizeNorm, sizeNorm];
        case 'southeast'
            pos = [1 - pad - sizeNorm, pad, sizeNorm, sizeNorm];
        case 'northwest'
            pos = [pad, 1 - pad - sizeNorm, sizeNorm, sizeNorm];
        case 'northeast'
            pos = [1 - pad - sizeNorm, 1 - pad - sizeNorm, sizeNorm, sizeNorm];
        otherwise
            error('EA_ADD_RAS_TRIAD:BadLocation', ...
                'Location must be a corner keyword or a 1x4 position vector.');
    end
end

function local_set_quiver_noscale(hq)
%LOCAL_SET_QUIVER_NOSCALE Best-effort disabling of quiver autoscaling.

    try
        if isprop(hq, 'AutoScale')
            hq.AutoScale = 'off';
        end
    catch
    end
    try
        if isprop(hq, 'AutoScaleFactor')
            hq.AutoScaleFactor = 1;
        end
    catch
    end
end
