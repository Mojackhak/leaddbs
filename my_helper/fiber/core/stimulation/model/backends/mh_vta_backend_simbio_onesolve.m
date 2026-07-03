function vta = mh_vta_backend_simbio_onesolve(cfg, S, options, request)
% Compute SimBio/Horn VTA outputs using one simultaneous multi-voltage solve.

stimFolders = mh_vta_request_field(request, 'stimFolders', []);
vta = mh_fiber_vta_paths(cfg, stimFolders);
sides = mh_vta_normalize_sides(request);
force = mh_vta_request_field(request, 'force', mh_vta_config_force(cfg));
spaces = mh_vta_request_field(request, 'outputSpaces', mh_vta_output_spaces_from_config());

options.native = 1;
options.orignative = 1;
S = ea_activecontacts(S);

for i = 1:numel(sides)
    side = sides{i};
    missingBefore = mh_vta_missing_files(vta, 'Sides', {side}, 'Spaces', spaces);
    if force || ~isempty(missingBefore)
        sideIdx = mh_util_side_to_index(side);
        headmodelPath = headmodel_path(options, sideIdx);
        fprintf('Preparing Lead-DBS headmodel for one-solve VTA, side %s...\n', side);
        mh_vta_run_horn_with_retry(S, sideIdx, options, cfg.stimLabel, headmodelPath, ...
            'WarningPrefix', 'mh_vta_backend_simbio_onesolve');

        fprintf('Running one-solve multi-voltage VTA, side %s...\n', side);
        solve_one_side(cfg, S, options, sideIdx);
    else
        fprintf('Reusing one-solve VTA/e-field: %s side %s\n', cfg.stimLabel, side);
    end
end

missingAfter = mh_vta_missing_files(vta, 'Sides', sides, 'Spaces', spaces);
if ~isempty(missingAfter)
    error('mh_vta_backend_simbio_onesolve:MissingVTAOutput', ...
        'One-solve VTA generation did not produce required file: %s', missingAfter{1});
end
vta = mh_vta_attach_volumes(vta);
end

function solve_one_side(cfg, S, options, side)
constvol = true;
thresh = options.prefs.machine.vatsettings.horn_ethresh;
thresh = thresh * 1000;
SIfx = 1000;

sideCode = side_to_code(side);
U = contact_voltage_vector(S, side);
if ~any(U)
    error('mh_vta_backend_simbio_onesolve:NoActiveContacts', ...
        'No active contact voltages found for side %s.', sideCode);
end

coords_mm = ea_load_reconstruction(options);
coords = coords_mm{side};
elspec = options.elspec;

headmodelPath = headmodel_path(options, side);
if ~isfile(headmodelPath)
    error('mh_vta_backend_simbio_onesolve:MissingHeadmodel', ...
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
    error('mh_vta_backend_simbio_onesolve:MissingActiveNodes', ...
        'Active vertex index was not found for side %s.', sideCode);
end

potential = mh_vta_fem_apply_dbs(vol, ix, voltix, unipolar, constvol, wmboundary);
gradient = mh_vta_fem_calc_gradient(vol, potential);
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

function path = headmodel_path(options, side)
headmodelDir = fullfile(options.subj.subjDir, 'headmodel', ea_nt(options));
filePrefix = ['sub-', options.subj.subjId, '_desc-'];
path = fullfile(headmodelDir, [filePrefix, 'headmodel', num2str(side), '.mat']);
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
        error('mh_vta_backend_simbio_onesolve:UnsupportedMode', ...
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
            error('mh_vta_backend_simbio_onesolve:ConflictingVoltage', ...
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
    warning('mh_vta_backend_simbio_onesolve:ElectrodeTetFieldSkipped', ...
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
    error('mh_vta_backend_simbio_onesolve:InvalidSide', 'Invalid side index: %d', side);
end
end
