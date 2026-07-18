function ea_export_mnifigure_spin_SI(hFig, hAx, outFile, varargin)
%EA_EXPORT_MNIFIGURE_SPIN_SI Export a 360-degree spin video around RAS S-I (Z) axis.
%
% This rotates the camera position around the world Z axis (RAS: +Z = S).
% The camera target stays fixed. CameraUpVector is forced to [0 0 1] by default.
%
% Inputs
%   hFig    : figure handle (Lead-DBS ea_mnifigure figure)
%   hAx     : main 3D axes handle
%   outFile : output video path, e.g. 'spin_SI.mp4'
%
% Name-Value options
%   'NumFrames'  : number of frames for one full rotation (default 240)
%   'FrameRate'  : frames per second (default 30)
%   'Direction'  : +1 or -1 (default +1). +1 rotates CCW when looking from +Z.
%   'KeepCamUp'  : true/false (default true). If true, camup=[0 0 1].
%   'BgColor'    : [r g b] (default [1 1 1]). Note: mp4 has no alpha.
%
% Notes
%   - MP4 does not support transparent background. Use a solid BgColor.
%   - For best results, keep camproj/camva consistent before calling.

ip = inputParser;
ip.addParameter('NumFrames', 240, @(x) isnumeric(x) && isscalar(x) && x>=10);
ip.addParameter('FrameRate', 30, @(x) isnumeric(x) && isscalar(x) && x>0);
ip.addParameter('Direction', +1, @(x) isnumeric(x) && isscalar(x) && (x==1 || x==-1));
ip.addParameter('KeepCamUp', true, @(x) islogical(x) && isscalar(x));
ip.addParameter('BgColor', [1 1 1], @(x) isnumeric(x) && numel(x)==3);
ip.parse(varargin{:});
p = ip.Results;

assert(ishandle(hFig) && isgraphics(hFig), 'Invalid figure handle.');
assert(ishandle(hAx)  && isgraphics(hAx),  'Invalid axes handle.');

% Background (MP4 has no transparency)
try
    set(hFig, 'Color', p.BgColor);
    set(hAx,  'Color', 'none');
catch
end

% Capture initial camera settings
tgt = get(hAx, 'CameraTarget');      % [x y z]
pos = get(hAx, 'CameraPosition');    % [x y z]
camva0  = get(hAx, 'CameraViewAngle');
proj0   = get(hAx, 'Projection');

% Force orthographic/perspective consistency
try
    set(hAx, 'Projection', proj0);
catch
end
try
    camva(hAx, camva0);
catch
end

% Use world Z axis (RAS S-I axis)
axisZ = [0 0 1];

% Vector from target to camera
v0 = pos - tgt;

% If v0 is too close to the rotation axis (x=y~0), spinning won't show motion
if norm(cross(v0, axisZ)) < 1e-6
    warning('Camera vector is nearly aligned with Z axis; rotation may look static.');
end

% Optionally lock camera up vector
if p.KeepCamUp
    camup(hAx, [0 0 1]);
end

% Prepare video writer
vw = VideoWriter(outFile, 'MPEG-4');
vw.FrameRate = p.FrameRate;
vw.Quality = 100;
open(vw);

% Render loop
set(hFig, 'Renderer', 'opengl');  % safer for patches/alpha
drawnow;

for k = 1:p.NumFrames
    theta = p.Direction * 2*pi * (k-1) / p.NumFrames;

    % Rotation around Z axis
    c = cos(theta); s = sin(theta);
    Rz = [ c -s  0;
           s  c  0;
           0  0  1];

    v = (Rz * v0(:)).';
    newPos = tgt + v;

    set(hAx, 'CameraPosition', newPos);
    set(hAx, 'CameraTarget', tgt);
    if p.KeepCamUp
        set(hAx, 'CameraUpVector', [0 0 1]);
    end

    drawnow;
    fr = getframe(hFig);
    writeVideo(vw, fr);
end

close(vw);
end
