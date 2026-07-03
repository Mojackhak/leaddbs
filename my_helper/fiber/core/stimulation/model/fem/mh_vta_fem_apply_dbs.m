function potential = mh_vta_fem_apply_dbs(vol, elec, val, unipolar, constvol, boundarynodes)
% Apply DBS boundary conditions and solve the FEM system.

if constvol
    if unipolar
        dirinodes = [boundarynodes, elec'];
    else
        dirinodes = elec;
    end
    rhs = zeros(length(vol.pos), 1);
    dirival = zeros(size(vol.pos, 1), 1);
    dirival(elec) = val(:, 1);
else
    if unipolar
        dirinodes = boundarynodes;
    else
        dirinodes = 1;
    end
    dirival = zeros(size(vol.pos, 1), 1);
    rhs = zeros(size(vol.pos, 1), 1);
    uvals = unique(val(:, 2));
    if unipolar && numel(uvals) == 1
        elecCenterId = find_elec_center(elec, vol.pos);
        rhs(elecCenterId) = val(1, 1);
    else
        for v = 1:numel(uvals)
            elecCenterId = find_elec_center(elec(val(:, 2) == uvals(v)), vol.pos);
            thesevals = val(val(:, 2) == uvals(v), 1);
            rhs(elecCenterId) = thesevals(1);
        end
    end
end

[stiff, rhs] = dbs_matrix(vol.stiff, rhs, dirinodes, dirival);
potential = sb_solve(stiff, rhs);
end

function centerId = find_elec_center(elec, pos)
center = mean(pos(elec, :));
distCenter = sqrt(sum((pos(elec, :) - repmat(center, numel(elec), 1)).^2, 2));
[~, elecId] = min(distCenter);
centerId = elec(elecId);
end

function [stiff, rhs] = dbs_matrix(stiff, rhs, dirinodes, dirival)
diagonal = diag(stiff);
stiff = stiff + stiff';
rhs = rhs - stiff * dirival;
stiff(dirinodes, :) = 0.0;
stiff(:, dirinodes) = 0.0;
diagonal = -diagonal;
diagonal(dirinodes) = 1.0;
stiff = stiff + spdiags(diagonal(:), 0, length(diagonal), length(diagonal));
rhs(dirinodes) = dirival(dirinodes);
end

function x = sb_solve(sysmat, vecb)
try
    L = ichol(sysmat);
catch
    alpha = max(sum(abs(sysmat), 2) ./ diag(sysmat)) - 2;
    L = ichol(sysmat, struct('type', 'ict', 'droptol', 1e-3, 'diagcomp', alpha));
end
[~, x] = evalc('pcg(sysmat, vecb, 10e-10, 5000, L, L'', vecb)');
end
