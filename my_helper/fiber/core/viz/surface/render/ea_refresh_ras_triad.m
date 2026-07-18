function ea_refresh_ras_triad(h)
%EA_REFRESH_RAS_TRIAD Force-refresh RAS triads in a figure/axes.
%
%   EA_REFRESH_RAS_TRIAD(h)
%
% This helper searches for inset RAS triad axes created by EA_ADD_RAS_TRIAD
% (Tag == 'EA_RAS_TRIAD_AXES') and forces them to update their orientation.
% This is useful after programmatically setting camera parameters, where
% graphics updates/listeners may not fire immediately on some systems.
%
% Input
%   h : figure or axes handle. If omitted, uses gcf.
%
% Notes
%   - The triad axes store a function handle in their UserData (.refresh)
%     that is called to sync to the main axes.

    if nargin < 1 || isempty(h) || ~ishandle(h)
        hFig = gcf;
    else
        if ishghandle(h, 'figure')
            hFig = h;
        else
            hFig = ancestor(h, 'figure');
            if isempty(hFig) || ~ishandle(hFig)
                hFig = gcf;
            end
        end
    end

    try
        triadAxes = findall(hFig, 'Type', 'axes', 'Tag', 'EA_RAS_TRIAD_AXES');
    catch
        triadAxes = [];
    end

    for k = 1:numel(triadAxes)
        axT = triadAxes(k);
        if ~ishandle(axT)
            continue;
        end
        try
            ud = get(axT, 'UserData');
        catch
            ud = [];
        end

        % Preferred: call the stored refresh callback.
        if isstruct(ud) && isfield(ud, 'refresh') && isa(ud.refresh, 'function_handle')
            try
                ud.refresh();
                continue;
            catch
                % Fall back below.
            end
        end

        % Fallback: attempt a minimal sync if main axes handle is known.
        if isstruct(ud) && isfield(ud, 'main_axes') && ishandle(ud.main_axes)
            try
                set(axT, 'View', get(ud.main_axes, 'View'));
                set(axT, 'CameraUpVector', get(ud.main_axes, 'CameraUpVector'));
                camtarget(axT, [0 0 0]);
            catch
            end
        end
    end

    % Flush graphics.
    try
        drawnow limitrate;
    catch
        try
            drawnow;
        catch
        end
    end
end
