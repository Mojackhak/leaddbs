%--------------------------------------------------------------------------
% dist2space_coords
%
% Convert a set of axial distances (along a DBS lead) into 3-D coordinates
% and save the result to disk.
%
% SIGN CONVENTION
% ───────────────
% The electrode axis is defined by two fiducials:
%       tail  →  head      (positive direction)
%
%   dist{side}(k)   :  distance of the k-th sampling point from HEAD,
%                      measured along the tail→head vector.
%                      ·  dist  > 0  →  point lies BEHIND the head
%                                       (towards the tail contact)
%                      ·  dist  < 0  →  point lies AHEAD of the head
%                                       (beyond the head along the
%                                       same axis direction)
%
%   offset{side}    :  systematic shift applied to every dist value
%                      for that side (e.g. planning vs. realised target).
%                      ·  offset  > 0  →  shift the entire set of points
%                                         towards the tail
%                      ·  offset  < 0  →  shift the entire set of points
%                                         beyond the head
%
% EXAMPLE CALL
% ────────────
%   subjFolder = '...\leaddbs\sub-001';
%   dist       = {linspace(0,14,8), linspace(0,14,8)};
%   offset     = {0, 0};
%   fileName   = 'MER_coords.mat';
%   coords     = dist2space_coords(subjFolder, dist, offset, fileName);
%
% Written by Mojack, 2025-05-22
%--------------------------------------------------------------------------


function coords = dist2space_coords(subjFolder, dist, offset, fileName)

    if nargin < 3 || isempty(offset);  offset  = {0, 0};   end
    if nargin < 4 || isempty(fileName); fileName = 'MER_coords.mat'; end

    fprintf('[%s] Converting dist → coords ...\n', datetime());

    %----------------------------------------------------------------------
    % 1. Load Lead-DBS options & reconstruct coords in native space
    %----------------------------------------------------------------------
    opt    = ea_getptopts(subjFolder);
    coords = dist2coord(dist, offset, opt);

    %----------------------------------------------------------------------
    % 2. Warp native/scrf → MNI
    %----------------------------------------------------------------------
    coords = native2mni(coords, opt);

    %----------------------------------------------------------------------
    % 3. Save & report
    %----------------------------------------------------------------------
    savePath = fullfile(opt.subj.reconDir, fileName);
    save(savePath, 'coords');

    fprintf('   ✔ Saved result to: %s\n', savePath);
end
%==========================================================================



%%========================================================================= 
%  Convert distance array to native-space coordinates
%--------------------------------------------------------------------------
function coords = dist2coord(dist, offset, opt)

    load(opt.subj.recon.recon, 'reco');
    useNative = 'native';             

    for side = opt.sides
        head = reco.(useNative).markers(side).head;
        tail = reco.(useNative).markers(side).tail;

        % Unit vector along electrode (tail→head)
        dirUnit   = (tail - head) ./ norm(tail - head);
        distReal  = dist{side}(:) + offset{side};

        coords.native{side} = head + distReal * dirUnit;
        coords.dist{side}   = dist{side}(:);
        coords.offset{side} = offset{side};
    end
end
%==========================================================================



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