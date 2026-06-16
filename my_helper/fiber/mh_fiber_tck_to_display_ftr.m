function display = mh_fiber_tck_to_display_ftr(cfg, tckPath, nativeMatPath, mniMatPath)
% Convert a DWI-space TCK bundle to Lead-DBS-display MAT files.

maxStreamlines = get_seed_option(cfg, 'displayMaxStreamlinesPerBundle', 500);
pointStride = get_seed_option(cfg, 'displayPointStride', 1);
tck = mh_fiber_load_tck(tckPath, maxStreamlines, pointStride);

display = struct();
display.sourceTck = tckPath;
display.streamlineCount = tck.streamlineCount;
display.nativeMat = nativeMatPath;
display.mniMat = mniMatPath;

if isempty(tck.idx)
    save_empty_ftr(nativeMatPath, tckPath);
    save_empty_ftr(mniMatPath, tckPath);
    return;
end

pointsDwiMm = tck.fibers(:, 1:3);
dwiVox = ea_mm2vox(pointsDwiMm, cfg.paths.dwiB0)';
[anchorMm, anchorVox] = ea_map_coords(dwiVox, cfg.paths.dwiB0, ...
    cfg.paths.dwiToAnchorTransform, cfg.paths.nativeReference, 'ANTS');
[mniMm, ~] = ea_map_coords(anchorVox, cfg.paths.nativeReference, ...
    cfg.paths.anchorToMniTransform, cfg.paths.mniReference, 'ANTS', 0);

nativeFibers = [anchorMm', tck.fibers(:, 4)];
mniFibers = [mniMm', tck.fibers(:, 4)];

save_ftr(nativeMatPath, nativeFibers, tck.idx, tckPath, cfg.paths.nativeReference);
save_ftr(mniMatPath, mniFibers, tck.idx, tckPath, cfg.paths.mniReference);
end

function value = get_seed_option(cfg, fieldName, defaultValue)
if isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, fieldName)
    value = cfg.seedTarget.(fieldName);
else
    value = defaultValue;
end
end

function save_empty_ftr(outputPath, sourceTck)
ea_mkdir(fileparts(outputPath));
ea_fibformat = '1.1';
fourindex = 1;
voxmm = 'mm';
source_tck = sourceTck;
fibers = zeros(0, 4);
idx = zeros(0, 1);
vals = zeros(0, 1);
save(outputPath, 'ea_fibformat', 'fourindex', 'voxmm', 'source_tck', 'fibers', 'idx', 'vals', '-v7.3');
end

function save_ftr(outputPath, fibers, idx, sourceTck, referenceNii)
ea_mkdir(fileparts(outputPath));
ea_fibformat = '1.1';
fourindex = 1;
voxmm = 'mm';
source_tck = sourceTck;
vals = ones(numel(idx), 1);
save(outputPath, 'ea_fibformat', 'fourindex', 'voxmm', 'source_tck', 'fibers', 'idx', 'vals', '-v7.3');
if ~isempty(idx) && isfile(referenceNii)
    try
        ea_ftr2trk(outputPath, referenceNii, 0);
    catch ME
        warning('mh_fiber_tck_to_display_ftr:TrkExportFailed', ...
            'Could not export TRK for %s: %s', outputPath, ME.message);
    end
end
end
