function v = ea_capture_view_struct(hAx)
%EA_CAPTURE_VIEW_STRUCT Capture the current camera/view parameters from a 3D axes.
%
%   v = EA_CAPTURE_VIEW_STRUCT()
%   v = EA_CAPTURE_VIEW_STRUCT(hAx)
%
% This function extracts camera parameters from a MATLAB 3D axes and returns
% a struct compatible with Lead-DBS ea_view(v).
%
% Output fields (Lead-DBS style)
%   v.az        : azimuth angle (deg)
%   v.el        : elevation angle (deg)
%   v.camva     : camera view angle (deg)
%   v.camup     : 1x3 camera up vector
%   v.camproj   : 'orthographic' or 'perspective'
%   v.camtarget : 1x3 camera target
%   v.campos    : 1x3 camera position
%
% Notes
%   - This captures what MATLAB currently uses for rendering; it does not
%     attempt to infer or store additional Lead-DBS state.
%   - Use EA_APPLY_VIEW_STRUCT(v, hAx) to re-apply later.
%
% See also: ea_view, ea_apply_view_struct, view, campos, camtarget, camup, camva

    if nargin < 1 || isempty(hAx)
        hAx = gca;
    end
    if ~ishandle(hAx) || ~strcmp(get(hAx, 'Type'), 'axes')
        error('EA_CAPTURE_VIEW_STRUCT:BadAxes', 'hAx must be a valid axes handle.');
    end

    v = struct();

    % View angles
    try
        ang = view(hAx);
        v.az = double(ang(1));
        v.el = double(ang(2));
    catch
        v.az = NaN;
        v.el = NaN;
    end

    % Camera properties
    try
        v.camva = double(get(hAx, 'CameraViewAngle'));
    catch
        try
            v.camva = double(camva(hAx));
        catch
            v.camva = NaN;
        end
    end

    try
        v.camup = double(get(hAx, 'CameraUpVector'));
    catch
        try
            v.camup = double(camup(hAx));
        catch
            v.camup = [NaN NaN NaN];
        end
    end

    try
        v.camproj = char(get(hAx, 'Projection'));
    catch
        v.camproj = '';
    end

    try
        v.camtarget = double(get(hAx, 'CameraTarget'));
    catch
        try
            v.camtarget = double(camtarget(hAx));
        catch
            v.camtarget = [NaN NaN NaN];
        end
    end

    try
        v.campos = double(get(hAx, 'CameraPosition'));
    catch
        try
            v.campos = double(campos(hAx));
        catch
            v.campos = [NaN NaN NaN];
        end
    end
end
