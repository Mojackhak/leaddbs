function vta = mh_fiber_ensure_vta(cfg, S, options, stimFolders)
% Ensure bilateral native and MNI VTA/e-field files exist for the stimulation.

vta = mh_fiber_vta_paths(cfg, stimFolders);
missingBefore = missing_vta_files(vta);
shouldRecompute = cfg.forceRecomputeVTA || ~isempty(missingBefore);

if shouldRecompute
    if cfg.forceRecomputeVTA
        fprintf('Recomputing VTA because cfg.forceRecomputeVTA is true.\n');
    else
        fprintf('VTA files are incomplete. Missing %d files; recomputing VTA.\n', numel(missingBefore));
    end
    ea_genvat_horn([], S, 1, options, cfg.stimLabel);
    ea_genvat_horn([], S, 2, options, cfg.stimLabel);
else
    fprintf('Reusing existing VTA/e-field files for label: %s\n', cfg.stimLabel);
end

missingAfter = missing_vta_files(vta);
if ~isempty(missingAfter)
    error('mh_fiber_ensure_vta:MissingVTAOutput', ...
        'VTA generation did not produce required file: %s', missingAfter{1});
end

vta.volume = struct();
vta.volume.R = read_vat_volume(vta.native.R.binaryMat);
vta.volume.L = read_vat_volume(vta.native.L.binaryMat);

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
