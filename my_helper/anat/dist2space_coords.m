%--------------------------------------------------------------------------
% dist2space_coords
%
% Convert a set of axial distances (along a DBS lead) into 3-D coordinates
% and save the result to disk.
%
% SIGN CONVENTION
% ───────────────
% The electrode axis is defined by two fiducials:
%       head  →  tail      (positive direction)
%
%   dist{side}(k)   :  distance of the k-th sampling point from HEAD contact (the middle point),
%                      measured along the tail→head vector.
%                      ·  dist  > 0  →  point lies BEHIND the head
%                                       (towards the tail contact)
%                      ·  dist  < 0  →  point lies AHEAD of the head
%                                       (beyond the head along the
%                                       same axis direction)
%
%   offset_d{side}    :  systematic depth shift applied to every dist value
%                      for that side (e.g. planning vs. realised target).
%                      ·  offset  > 0  →  shift the entire set of points
%                                         towards the tail
%                      ·  offset  < 0  →  shift the entire set of points
%                                         beyond the head
%
%   offset_x{side}    :  systematic x-axis (RAS+ convention, i.e. left → right) shift applied to every dist value
%                      for that side (e.g. planning vs. realised target).
%                      ·  offset  > 0  →  shift the entire set of points
%                                         towards the right
%                      ·  offset  < 0  →  shift the entire set of points
%                                         towards the left
%   offset_y{side}    :  systematic y-axis (RAS+ convention, i.e. posterior → anterior) shift applied to every dist value
%                      for that side (e.g. planning vs. realised target).
%                      ·  offset  > 0  →  shift the entire set of points
%                                         towards the anterior
%                      ·  offset  < 0  →  shift the entire set of points
%                                         towards the posterior
%
%   offset{side} = (offset_x, offset_y, offset_d)
%
% Backward compatibility:
%   - scalar offset{side} ⇒ [0 0 offset_d]
%   - [x y] ⇒ [x y 0]
%
% EXAMPLE CALL
% ────────────
%   subjFolder = '...\leaddbs\sub-001';
%   % the entries in the right hemisphere will be in {1}, the ones in the left in the {2} cell. 
%   dist       = {linspace(0,14,8), linspace(0,14,8)}; 
%   offset     = {[0, 0, 0], [0, 0, 0]};
%   fileName   = 'MER_coords.mat';
%   coords     = dist2space_coords(subjFolder, dist, offset, fileName);
%
% Written by Mojack, 2025-05-22
% Updated 2025-08-21
%--------------------------------------------------------------------------


function coords = dist2space_coords(subjFolder, dist, offset, fileName)

    if nargin < 3; offset = []; end
    if nargin < 4 || isempty(fileName); fileName = 0; end % do not save file

    fprintf('[%s] Converting dist → coords ...\n', string(datetime()));

    % 1) Load Lead-DBS options
    opt = ea_getptopts(subjFolder);

    % 2) Normalize/upgrade offset to { [x y d], [x y d], ... }
    offset = upgrade_offset_arg(offset, opt);

    % 3) Reconstruct native coords (apply depth along axis + native RAS+ x/y)
    coords = dist2coord_native(dist, offset, opt);

    % 4) Warp native/scrf → MNI (planar offsets already baked into native)
    coords = native2mni(coords, opt);

    % 5) Save
    if fileName
        savePath = fullfile(opt.subj.reconDir, fileName);
        save(savePath, 'coords');
        fprintf('[%s]   Success\n', string(datetime()));
        fprintf('   ✔ Saved result to: %s\n', savePath);
    else
        fprintf('[%s]   ✔ Success\n', string(datetime()));
    end
end

%==========================================================================
% Upgrade/normalize offset to the new [x y d] cell format
%--------------------------------------------------------------------------
function offCell = upgrade_offset_arg(offset, opt)
    nSides  = max(opt.sides);
    offCell = repmat({[0 0 0]}, 1, nSides);

    if isempty(offset)
        return;
    end

    if ~iscell(offset)
        if isscalar(offset)
            for s = opt.sides
                offCell{s} = [0 0 offset];
            end
            return;
        else
            error('offset must be a cell array per side or a scalar.');
        end
    end

    for s = opt.sides
        if numel(offset) >= s && ~isempty(offset{s})
            v = offset{s};
        else
            v = 0;
        end
        if isscalar(v)
            offCell{s} = [0 0 v];
        else
            v = v(:).';
            if numel(v) < 3, v(end+1:3) = 0; end
            offCell{s} = v(1:3);   % [x y d]
        end
    end
end

%==========================================================================
% Convert distance array to native-space coordinates
% Apply: axial (offset_d) along lead axis + planar native RAS+ [x y]
%--------------------------------------------------------------------------
function coords = dist2coord_native(dist, offset, opt)

    load(opt.subj.recon.recon, 'reco');
    useNative = 'native';

    for side = opt.sides
        head = reco.(useNative).markers(side).head;
        tail = reco.(useNative).markers(side).tail;

        % Unit vector along electrode (head→tail)
        dirUnit = (tail - head) ./ norm(tail - head);

        off     = offset{side};          % [x y d]
        off_x   = off(1);
        off_y   = off(2);
        off_d   = off(3);

        % Axial shift along the lead
        distReal  = dist{side}(:) + off_d;         % N×1
        xyzNative = head + distReal * dirUnit;     % N×3

        % Uniform native RAS+ planar shift
        xyzNative(:,1) = xyzNative(:,1) + off_x;   % x: L→R
        xyzNative(:,2) = xyzNative(:,2) + off_y;   % y: P→A

        coords.native{side} = xyzNative;
        coords.dist{side}   = dist{side}(:);
        coords.offset{side} = off;                 % store [x y d]
    end

    coords.meta.native_axis = 'RAS+';
end

%%========================================================================= 
%  Warp native/scrf coordinates to MNI space
%--------------------------------------------------------------------------
function coords = native2mni(coords, opt)

    %--- SCRF affine (if present) -----------------------------------------
    if isfile(opt.subj.brainshift.transform.scrf)
        d = load(opt.subj.brainshift.transform.scrf);
        for side = opt.sides
            tmp  = d.mat * [coords.native{side}, ones(size(coords.native{side},1),1)]';
            coords.scrf{side} = tmp(1:3,:)';
        end
    else
        coords.scrf = coords.native;  % fallback
    end

    %--- Non-linear warp to MNI ------------------------------------------
    nii = ea_load_nii(opt.subj.coreg.anat.preop.(opt.subj.AnchorModality));
    for side = opt.sides
        coords.mni{side} = local_warpcoord(coords.scrf{side}, nii, opt);
    end
end
%==========================================================================



%%========================================================================= 
%  Apply affine + deformation field (helper wrapper around ea_map_coords)
%--------------------------------------------------------------------------
function cOut = local_warpcoord(cIn, nii, opt)
    vox = (nii(1).mat \ [cIn, ones(size(cIn,1),1)]')';          % mm→vox
    def = ea_map_coords(vox(:,1:3)', ...
                        nii(1).fname, ...
                        fullfile(opt.subj.subjDir, 'inverseTransform'), ...
                        '');
    cOut = def';                                                 % [N×3]
end
%==========================================================================



function distances = calculate_distances(points)
    % CALCULATE_DISTANCES Calculate distances between adjacent 3D points
    %
    % Input:
    %   points - n×3 matrix where each row is [x, y, z] coordinates
    %
    % Output:
    %   distances - (n-1)×1 vector of distances between adjacent points
    %
    % Example:
    %   points = [1, 2, 3; 4, 6, 7; 0, 1, 5];
    %   distances = calculate_distances(points);
    
    % Check input
    if size(points, 2) ~= 3
        error('Input must be an n×3 matrix');
    end
    
    if size(points, 1) < 2
        error('At least 2 points are required');
    end
    
    % Calculate distances between adjacent points
    distances = vecnorm(diff(points), 2, 2);
end