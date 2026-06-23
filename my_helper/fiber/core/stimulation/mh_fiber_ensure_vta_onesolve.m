function vta = mh_fiber_ensure_vta_onesolve(cfg, S, options, stimFolders)
% Generate VTA/e-field using one simultaneous multi-voltage FEM solve.

vta = mh_fiber_vta_paths(cfg, stimFolders);

options.native = 1;
options.orignative = 1;
options.atlasset = cfg.vta.gmAtlas;
S = ea_activecontacts(S);

for side = 1:2
    fprintf('Preparing Lead-DBS headmodel for one-solve VTA, side %d...\n', side);
    ea_genvat_horn([], S, side, options, cfg.stimLabel);

    fprintf('Running one-solve multi-voltage VTA, side %d...\n', side);
    solve_one_side(cfg, S, options, side);
end

missingAfter = missing_vta_files(vta);
if ~isempty(missingAfter)
    error('mh_fiber_ensure_vta_onesolve:MissingVTAOutput', ...
        'One-solve VTA generation did not produce required file: %s', missingAfter{1});
end

vta.volume = struct();
vta.volume.R = read_vat_volume(vta.native.R.binaryMat);
vta.volume.L = read_vat_volume(vta.native.L.binaryMat);
end

function solve_one_side(cfg, S, options, side)
constvol = true;
thresh = options.prefs.machine.vatsettings.horn_ethresh;
thresh = thresh * 1000;
SIfx = 1000;

sideCode = side_to_code(side);
U = contact_voltage_vector(S, side);
if ~any(U)
    error('mh_fiber_ensure_vta_onesolve:NoActiveContacts', ...
        'No active contact voltages found for side %s.', sideCode);
end

[coords_mm] = ea_load_reconstruction(options);
coords = coords_mm{side};
elspec = options.elspec;

headmodelDir = fullfile(options.subj.subjDir, 'headmodel', ea_nt(options));
filePrefix = ['sub-', options.subj.subjId, '_desc-'];
headmodelPath = fullfile(headmodelDir, [filePrefix, 'headmodel', num2str(side), '.mat']);
if ~isfile(headmodelPath)
    error('mh_fiber_ensure_vta_onesolve:MissingHeadmodel', ...
        'Headmodel file is missing after ea_genvat_horn call: %s', headmodelPath);
end

hm = load(headmodelPath, 'vol', 'mesh', 'centroids', 'wmboundary', 'elfv', 'meshregions');
vol = hm.vol;
mesh = hm.mesh;
centroids = hm.centroids;
wmboundary = hm.wmboundary;
elfv = hm.elfv;
meshregions = hm.meshregions;

indexS = make_single_source_index_s(S, side, U);
activeidx = ea_getactiveidx(indexS, side, centroids, mesh, elfv, elspec, meshregions);

actInd = find(U);
actContact = coords(actInd, :);
volts = U(U ~= 0);
if any(volts > 0)
    unipolar = 0;
    U = U / 2;
else
    unipolar = 1;
end

ix = [];
voltix = [];
groupIdx = 1;
for ac = actInd
    contactNodes = activeidx(1).con(ac).ix;
    ix = [ix; contactNodes]; %#ok<AGROW>
    voltix = [voltix; repmat(U(ac), numel(contactNodes), 1), ...
        repmat(groupIdx, numel(contactNodes), 1)]; %#ok<AGROW>
    groupIdx = groupIdx + 1;
end

if isempty(ix)
    error('mh_fiber_ensure_vta_onesolve:MissingActiveNodes', ...
        'Active vertex index was not found for side %s.', sideCode);
end

potential = mh_fiber_apply_dbs(vol, ix, voltix, unipolar, constvol, wmboundary);
gradient = mh_fiber_calc_gradient(vol, potential);
gradient = set_electrode_tets_to_high_field(mesh, gradient, ix);

vol.pos = vol.pos * SIfx;
midpts = mean(cat(3, ...
    vol.pos(vol.tet(:, 1), :), ...
    vol.pos(vol.tet(:, 2), :), ...
    vol.pos(vol.tet(:, 3), :), ...
    vol.pos(vol.tet(:, 4), :)), 3);

indices = jittered_indices(size(midpts, 1), 10);
voltValues = voltix(:, 1);

nativeOptions = options;
nativeOptions.native = 1;
nativeOptions.orignative = 1;
ea_write_vta_nii(S, cfg.stimLabel, midpts, indices, elspec, actContact, ...
    voltValues, constvol, thresh, mesh, gradient, side, '', nativeOptions);

anchor = options.subj.preopAnat.(options.subj.AnchorModality).coreg;
ptsvx_native = ea_mm2vox([midpts; actContact], anchor)';
ptsmm_mni = ea_map_coords(ptsvx_native, anchor, ...
    [options.subj.subjDir, filesep, 'inverseTransform'], '')';
midpts_mni = ptsmm_mni(1:size(midpts, 1), :);
actContact_mni = ptsmm_mni(size(midpts, 1)+1:end, :);

mniOptions = options;
mniOptions.native = 0;
mniOptions.orignative = 1;
ea_write_vta_nii(S, cfg.stimLabel, midpts_mni, indices, elspec, actContact_mni, ...
    voltValues, constvol, thresh, mesh, gradient, side, '', mniOptions);
end

function U = contact_voltage_vector(S, side)
sideCode = side_to_code(side);
U = zeros(1, S.numContacts);
for source = 1:4
    sourceField = [sideCode, 's', num2str(source)];
    if ~isfield(S, sourceField)
        continue;
    end
    stimSource = S.(sourceField);
    if stimSource.amp <= 0
        continue;
    end
    if stimSource.va ~= 1
        error('mh_fiber_ensure_vta_onesolve:UnsupportedMode', ...
            'One-solve helper currently supports voltage mode only.');
    end
    for contact = 1:S.numContacts
        contactField = ['k', num2str(contact)];
        contactStim = stimSource.(contactField);
        if contactStim.perc <= 0
            continue;
        end
        value = stimSource.amp;
        if contactStim.pol == 1
            value = -value;
        elseif contactStim.pol ~= 2
            continue;
        end
        if U(contact) ~= 0 && abs(U(contact) - value) > 1e-9
            error('mh_fiber_ensure_vta_onesolve:ConflictingVoltage', ...
                'Contact %d has conflicting voltages in multiple sources.', contact);
        end
        U(contact) = value;
    end
end
end

function indexS = make_single_source_index_s(S, side, U)
indexS = S;
sideCode = side_to_code(side);
for source = 1:4
    sourceField = [sideCode, 's', num2str(source)];
    indexS.(sourceField).amp = 0;
    for contact = 1:S.numContacts
        contactField = ['k', num2str(contact)];
        indexS.(sourceField).(contactField).perc = 0;
        indexS.(sourceField).(contactField).pol = 0;
    end
end

sourceField = [sideCode, 's1'];
indexS.(sourceField).amp = max(abs(U));
indexS.(sourceField).va = 1;
indexS.(sourceField).case.perc = 100;
indexS.(sourceField).case.pol = 2;
for contact = find(U)
    contactField = ['k', num2str(contact)];
    indexS.(sourceField).(contactField).perc = 100;
    if U(contact) < 0
        indexS.(sourceField).(contactField).pol = 1;
    else
        indexS.(sourceField).(contactField).pol = 2;
    end
end
indexS = ea_activecontacts(indexS);
end

function gradient = set_electrode_tets_to_high_field(mesh, gradient, ix)
try
    elecTetIx = sub2ind(size(mesh.pnt), ...
        vertcat(ix, ix, ix), ...
        vertcat(ones(numel(ix), 1), ones(numel(ix), 1).*2, ones(numel(ix), 1).*3));
    elecTetIx = find(sum(ismember(mesh.tet, elecTetIx), 2) == 4);
    if ~isempty(elecTetIx)
        tmp = sort(abs(gradient), 'descend');
        gradient(elecTetIx, :) = repmat(mean(tmp(1:ceil(size(tmp, 1)*0.001), :)), ...
            numel(elecTetIx), 1);
    end
catch ME
    warning('mh_fiber_ensure_vta_onesolve:ElectrodeTetFieldSkipped', ...
        'Could not assign high e-field values to electrode tetrahedra: %s', ME.message);
end
end

function indices = jittered_indices(nPoints, reduction)
indices = zeros(numel(1:reduction:nPoints), 1);
counter = 1;
for idx = 1:reduction:nPoints
    indices(counter) = idx + round(randn(1) * (reduction / 3));
    counter = counter + 1;
end
indices = unique(indices(2:end-1));
indices(indices == 0) = [];
indices(indices > nPoints) = [];
end

function code = side_to_code(side)
if side == 1
    code = 'R';
elseif side == 2
    code = 'L';
else
    error('mh_fiber_ensure_vta_onesolve:InvalidSide', 'Invalid side index: %d', side);
end
end

function missing = missing_vta_files(vta)
required = { ...
    vta.native.R.binaryMat, vta.native.R.binaryNii, vta.native.R.efieldNii, ...
    vta.native.L.binaryMat, vta.native.L.binaryNii, vta.native.L.efieldNii, ...
    vta.mni.R.binaryMat, vta.mni.R.binaryNii, vta.mni.R.efieldNii, ...
    vta.mni.L.binaryMat, vta.mni.L.binaryNii, vta.mni.L.efieldNii};
missing = required(~cellfun(@isfile, required));
end

function volume = read_vat_volume(matPath)
data = load(matPath, 'vatvolume');
if isfield(data, 'vatvolume')
    volume = data.vatvolume;
else
    volume = NaN;
end
end

function potential = mh_fiber_apply_dbs(vol, elec, val, unipolar, constvol, boundarynodes)
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
        elecCenterId = mh_fiber_find_elec_center(elec, vol.pos);
        rhs(elecCenterId) = val(1, 1);
    else
        for v = 1:numel(uvals)
            elecCenterId = mh_fiber_find_elec_center(elec(val(:, 2) == uvals(v)), vol.pos);
            thesevals = val(val(:, 2) == uvals(v), 1);
            rhs(elecCenterId) = thesevals(1);
        end
    end
end

[stiff, rhs] = mh_fiber_dbs_matrix(vol.stiff, rhs, dirinodes, dirival);
potential = mh_fiber_sb_solve(stiff, rhs);
end

function centerId = mh_fiber_find_elec_center(elec, pos)
center = mean(pos(elec, :));
distCenter = sqrt(sum((pos(elec, :) - repmat(center, numel(elec), 1)).^2, 2));
[~, elecId] = min(distCenter);
centerId = elec(elecId);
end

function [stiff, rhs] = mh_fiber_dbs_matrix(stiff, rhs, dirinodes, dirival)
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

function x = mh_fiber_sb_solve(sysmat, vecb)
try
    L = ichol(sysmat);
catch
    alpha = max(sum(abs(sysmat), 2) ./ diag(sysmat)) - 2;
    L = ichol(sysmat, struct('type', 'ict', 'droptol', 1e-3, 'diagcomp', alpha));
end
[~, x] = evalc('pcg(sysmat, vecb, 10e-10, 5000, L, L'', vecb)');
end

function gradient = mh_fiber_calc_gradient(vol, potential)
normal = cross(vol.pos(vol.tet(:,4),:) - vol.pos(vol.tet(:,3),:), ...
    vol.pos(vol.tet(:,3),:) - vol.pos(vol.tet(:,2),:));
gradient = repmat(potential(vol.tet(:,1)) ./ sum(normal .* ...
    (vol.pos(vol.tet(:,1),:) - (vol.pos(vol.tet(:,2),:) + vol.pos(vol.tet(:,3),:) + vol.pos(vol.tet(:,4),:)) / 3), 2), 1, 3) .* normal;

normal = cross(vol.pos(vol.tet(:,1),:) - vol.pos(vol.tet(:,4),:), ...
    vol.pos(vol.tet(:,4),:) - vol.pos(vol.tet(:,3),:));
gradient = gradient + repmat(potential(vol.tet(:,2)) ./ sum(normal .* ...
    (vol.pos(vol.tet(:,2),:) - (vol.pos(vol.tet(:,3),:) + vol.pos(vol.tet(:,4),:) + vol.pos(vol.tet(:,1),:)) / 3), 2), 1, 3) .* normal;

normal = cross(vol.pos(vol.tet(:,2),:) - vol.pos(vol.tet(:,1),:), ...
    vol.pos(vol.tet(:,1),:) - vol.pos(vol.tet(:,4),:));
gradient = gradient + repmat(potential(vol.tet(:,3)) ./ sum(normal .* ...
    (vol.pos(vol.tet(:,3),:) - (vol.pos(vol.tet(:,4),:) + vol.pos(vol.tet(:,1),:) + vol.pos(vol.tet(:,2),:)) / 3), 2), 1, 3) .* normal;

normal = cross(vol.pos(vol.tet(:,3),:) - vol.pos(vol.tet(:,2),:), ...
    vol.pos(vol.tet(:,2),:) - vol.pos(vol.tet(:,1),:));
gradient = gradient + repmat(potential(vol.tet(:,4)) ./ sum(normal .* ...
    (vol.pos(vol.tet(:,4),:) - (vol.pos(vol.tet(:,1),:) + vol.pos(vol.tet(:,2),:) + vol.pos(vol.tet(:,3),:)) / 3), 2), 1, 3) .* normal;
end
