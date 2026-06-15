function T = reformat_coords_table(M)
% Convert all subjects in a Lead-DBS group dataset M.elstruct(:)
% into a single long table with one row per contact.
%
% Columns:
%   Name | Side | Contact | contactNum | MNI_x | MNI_y | MNI_z | elmodel | color_r | color_g | color_b

    if isfield(M, "elstruct")
        E = M.elstruct;          % array of subject structures
    else
        error("Input M must contain field 'elstruct'.");
    end

    T = table();
    for s = 1:numel(E)
        subj_table = leadgroup_to_long_single(E(s));
        T = [T; subj_table];     %#ok<AGROW>  % simple & fine for modest sizes
    end
end


function T = leadgroup_to_long_single(R)
% Convert one subject’s elstruct into long table rows (one row per contact).

    nm  = string(getfield(R, 'name'));
    mdl = string(getfield(R, 'elmodel'));
    gi  = getfield(R, 'group');
    if numel(gi) == 1, gi = [gi gi]; end
    GCOL = getfield(R, 'groupcolors');
    C    = getfield(R, 'coords_mm');

    % Left / Right coordinates (each is n×3)
    CL = C{1};
    CR = C{2};

    % Clamp group indices to palette
    giL = max(1, min(size(GCOL,1), gi(1)));
    giR = max(1, min(size(GCOL,1), gi(2)));
    cL  = GCOL(giL, :);
    cR  = GCOL(giR, :);

    % Counts per side
    nL = size(CL,1);
    nR = size(CR,1);

    % LEFT side rows
    TL = table();
    if nL > 0
        TL = table( ...
            repmat(nm,  nL, 1), ...
            repmat("L", nL, 1), ...
            (1:nL)', ...
            repmat(nL,  nL, 1), ...     % contactNum = total contacts on this side
            CL(:,1), CL(:,2), CL(:,3), ...
            repmat(mdl, nL, 1), ...
            repmat(cL(1), nL, 1), repmat(cL(2), nL, 1), repmat(cL(3), nL, 1), ...
            'VariableNames', {'Name','Side','Contact','contactNum','MNI_x','MNI_y','MNI_z','elmodel','color_r','color_g','color_b'} ...
        );
    end

    % RIGHT side rows
    TR = table();
    if nR > 0
        TR = table( ...
            repmat(nm,  nR, 1), ...
            repmat("R", nR, 1), ...
            (1:nR)', ...
            repmat(nR,  nR, 1), ...     % contactNum = total contacts on this side
            CR(:,1), CR(:,2), CR(:,3), ...
            repmat(mdl, nR, 1), ...
            repmat(cR(1), nR, 1), repmat(cR(2), nR, 1), repmat(cR(3), nR, 1), ...
            'VariableNames', {'Name','Side','Contact','contactNum','MNI_x','MNI_y','MNI_z','elmodel','color_r','color_g','color_b'} ...
        );
    end

    T = [TL; TR];
    if ~isempty(T)
        T.Side = categorical(T.Side, {'L','R'});
    end
end