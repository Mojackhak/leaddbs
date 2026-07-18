function ea_export_mnifigure_spin(hFig, hAx, outFile, varargin)
%EA_EXPORT_MNIFIGURE_SPIN_SI Export a 360-degree spin video around a user-defined axis.
%
% This rotates the CAMERA POSITION around a fixed world-axis passing through
% CameraTarget. The target stays fixed.
%
% Axis can be specified in two ways:
%   1) As a 3-vector k = [kx ky kz] (will be normalized internally)
%   2) As a 3x3 skew-symmetric matrix K (axis in so(3)), where:
%        K = [  0  -kz   ky
%              kz   0  -kx
%             -ky  kx   0 ]
%      and the rotation is computed with Rodrigues:
%        R(theta) = I + sin(theta)*K + (1-cos(theta))*K^2
%
% RAS convention used here (world coordinates):
%   R = +X,  A = +Y,  S = +Z
%
% Common axis K matrices (RAS):
%   % Spin around S-I axis (+S / +Z):
%   K_SI = [ 0 -1  0;
%            1  0  0;
%            0  0  0 ];
%
%   % Spin around A-P axis (+A / +Y):
%   K_AP = [ 0  0  1;
%            0  0  0;
%           -1  0  0 ];
%
%   % Spin around R-L axis (+R / +X):
%   K_RL = [ 0  0  0;
%            0  0 -1;
%            0  1  0 ];
%
% Inputs
%   hFig    : figure handle (Lead-DBS ea_mnifigure figure)
%   hAx     : main 3D axes handle
%   outFile : output video path, e.g. 'spin.mp4'
%
% Name-Value options
%   'NumFrames'  : number of frames for one full rotation (default 240)
%   'FrameRate'  : frames per second (default 30)
%   'Direction'  : +1 or -1 (default +1)
%   'Axis'       : [] (default = SI axis), OR 3-vector, OR 3x3 skew matrix K
%   'KeepCamUp'  : true/false (default true). If true, CameraUpVector is fixed.
%   'CamUpVector': 1x3 vector (default [0 0 1]) used when KeepCamUp=true
%   'RotateCamUp': true/false (default true). If KeepCamUp=false, rotate the
%                  original CameraUpVector by R(theta) (reduces "rolling").
%   'BgColor'    : [r g b] (default [1 1 1]). Note: mp4 has no alpha.
%
% Notes
%   - MP4 does not support transparent background. Use a solid BgColor.
%   - If you pass a K matrix, it MUST be skew-symmetric.

ip = inputParser;
ip.addParameter('NumFrames', 240, @(x) isnumeric(x) && isscalar(x) && x>=10);
ip.addParameter('FrameRate', 30, @(x) isnumeric(x) && isscalar(x) && x>0);
ip.addParameter('Direction', +1, @(x) isnumeric(x) && isscalar(x) && (x==1 || x==-1));
ip.addParameter('Axis', [], @(x) isempty(x) || (isnumeric(x) && (isvector(x) || isequal(size(x),[3 3]))));
ip.addParameter('KeepCamUp', true, @(x) islogical(x) && isscalar(x));
ip.addParameter('CamUpVector', [0 0 1], @(x) isnumeric(x) && numel(x)==3);
ip.addParameter('RotateCamUp', true, @(x) islogical(x) && isscalar(x));
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
tgt    = get(hAx, 'CameraTarget');      % [x y z]
pos    = get(hAx, 'CameraPosition');    % [x y z]
up0    = get(hAx, 'CameraUpVector');    % [x y z]
camva0 = get(hAx, 'CameraViewAngle');
proj0  = get(hAx, 'Projection');

% Keep projection/view angle consistent
try, set(hAx, 'Projection', proj0); catch, end
try, camva(hAx, camva0); catch, end

% -------------------------------------------------------------------------
% Resolve rotation axis: either vector k or skew matrix K (normalized)
% Default axis is SI (+Z) in RAS: k=[0 0 1].
% -------------------------------------------------------------------------
[K, k] = local_resolve_axis(p.Axis);

% Vector from target to camera
v0 = pos - tgt;

% Warn if the camera vector is almost parallel to the rotation axis
if norm(cross(v0, k)) < 1e-6
    warning('Camera vector is nearly aligned with rotation axis; spin may look static.');
end

% Optionally lock camera up vector
camUpFixed = p.CamUpVector(:);
if norm(camUpFixed) > 0
    camUpFixed = camUpFixed ./ norm(camUpFixed);
else
    camUpFixed = [0;0;1];
end

if p.KeepCamUp
    camup(hAx, camUpFixed.');
end

% Prepare video writer
vw = VideoWriter(outFile, 'MPEG-4');
vw.FrameRate = p.FrameRate;
vw.Quality = 100;
open(vw);

% Render loop
set(hFig, 'Renderer', 'opengl');  % safer for patches/alpha
drawnow;

for kf = 1:p.NumFrames
    theta = p.Direction * 2*pi * (kf-1) / p.NumFrames;

    % Rodrigues rotation: R = I + sinθ K + (1-cosθ) K^2
    R = eye(3) + sin(theta)*K + (1 - cos(theta))*(K*K);

    v = (R * v0(:)).';     % rotate camera vector around axis
    newPos = tgt + v;

    set(hAx, 'CameraPosition', newPos);
    set(hAx, 'CameraTarget', tgt);

    if p.KeepCamUp
        set(hAx, 'CameraUpVector', camUpFixed.');
    else
        if p.RotateCamUp
            up = (R * up0(:)).';
            set(hAx, 'CameraUpVector', up);
        end
    end

    drawnow;
    writeVideo(vw, getframe(hFig));
end

close(vw);
end

% ========================= Helper functions ==============================

function [K, k] = local_resolve_axis(axisInput)
%LOCAL_RESOLVE_AXIS Return normalized skew matrix K and unit axis vector k.

    if isempty(axisInput)
        % Default: SI axis (+Z) in RAS
        k = [0; 0; 1];
        K = local_skew(k);
        return;
    end

    if isvector(axisInput) && numel(axisInput)==3
        k = axisInput(:);
        nk = norm(k);
        if nk < eps
            error('Axis vector must be non-zero.');
        end
        k = k / nk;
        K = local_skew(k);
        return;
    end

    if isequal(size(axisInput), [3 3])
        K = double(axisInput);

        % Check skew-symmetry: K' = -K, diagonal = 0
        if norm(K + K.', 'fro') > 1e-6 || any(abs(diag(K)) > 1e-9)
            error(['Axis matrix must be 3x3 skew-symmetric (so(3)). ', ...
                   'If you intended to pass a vector, use Axis=[kx ky kz].']);
        end

        % Recover axis vector from skew matrix
        % For K = [0 -kz ky; kz 0 -kx; -ky kx 0]
        k = [K(3,2); K(1,3); K(2,1)];
        nk = norm(k);
        if nk < eps
            error('Axis matrix corresponds to a zero axis (all zeros).');
        end

        % Normalize so that K corresponds to a unit axis
        k = k / nk;
        K = K / nk;
        return;
    end

    error('Axis must be empty, a 3-vector, or a 3x3 skew-symmetric matrix.');
end

function K = local_skew(k)
%LOCAL_SKEW Build a skew-symmetric matrix from a 3x1 axis vector k.
    kx = k(1); ky = k(2); kz = k(3);
    K = [  0   -kz   ky;
          kz    0   -kx;
         -ky   kx    0 ];
end
