function ea_apply_view_struct(v, hAx)
%EA_APPLY_VIEW_STRUCT Apply a Lead-DBS-style camera/view struct to a 3D axes.
%
%   EA_APPLY_VIEW_STRUCT(v)
%   EA_APPLY_VIEW_STRUCT(v, hAx)
%
% This helper is compatible with the view structs used by Lead-DBS ea_view().
% If ea_view() is available, it is used for maximum compatibility. Otherwise,
% the camera properties are applied directly to the target axes.
%
% Expected fields (any subset):
%   v.az        : azimuth angle in degrees
%   v.el        : elevation angle in degrees
%   v.camva     : camera view angle in degrees (camva)
%   v.camup     : 1x3 camera up vector
%   v.camproj   : 'orthographic' or 'perspective'
%   v.camtarget : 1x3 camera target (in data units)
%   v.campos    : 1x3 camera position (in data units)
%
% Notes
%   - Lead-DBS typically stores camera parameters in world/mm space (for MNI figures).
%   - Missing fields are ignored.
%   - This function does not change axis limits.
%
% See also: ea_view, view, camproj, camva, campos, camtarget, camup

    if nargin < 1 || isempty(v) || ~isstruct(v)
        error('EA_APPLY_VIEW_STRUCT:BadInput', 'v must be a non-empty struct.');
    end
    if nargin < 2 || isempty(hAx)
        hAx = gca;
    end
    if ~ishandle(hAx)
        error('EA_APPLY_VIEW_STRUCT:BadAxes', 'hAx must be a valid axes handle.');
    end

    % Preserve the Lead-DBS compatibility call when available.
    if exist('ea_view', 'file') == 2
        try
            hFig = ancestor(hAx, 'figure');
            if ~isempty(hFig) && ishandle(hFig)
                set(hFig, 'CurrentAxes', hAx);
            end
            ea_view(v);
        catch
        end
    end

    % Always reapply the complete camera directly to the requested axes. This
    % makes the target handle authoritative even when ea_view selected another
    % current axes or normalized a camera field.
    if isfield(v, 'az') && isfield(v, 'el')
        try
            view(hAx, [double(v.az), double(v.el)]);
        catch
        end
    end

    if isfield(v, 'camproj')
        try
            camproj(hAx, char(v.camproj));
        catch
        end
    end

    if isfield(v, 'camva')
        try
            camva(hAx, double(v.camva));
        catch
        end
    end

    if isfield(v, 'camup')
        try
            camup(hAx, double(v.camup(:))');
        catch
        end
    end

    if isfield(v, 'camtarget')
        try
            camtarget(hAx, double(v.camtarget(:))');
        catch
        end
    end

    if isfield(v, 'campos')
        try
            campos(hAx, double(v.campos(:))');
        catch
        end
    end

    % Force-refresh any RAS triads in the same figure (best effort).
    try
        if exist('ea_refresh_ras_triad', 'file') == 2
            ea_refresh_ras_triad(hAx);
        end
    catch
    end

    % Flush graphics to ensure the update is visible immediately.
    try
        drawnow limitrate;
    catch
        try
            drawnow;
        catch
        end
    end
end
