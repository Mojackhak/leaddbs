function vta = mh_vta_backend_simbio_twosource(cfg, S, options, request)
% Compute SimBio/Horn VTA outputs using the standard Lead-DBS source handling.

stimFolders = mh_vta_request_field(request, 'stimFolders', []);
vta = mh_fiber_vta_paths(cfg, stimFolders);
sides = mh_vta_normalize_sides(request);
force = mh_vta_request_field(request, 'force', mh_vta_config_force(cfg));
spaces = mh_vta_request_field(request, 'outputSpaces', mh_vta_output_spaces_from_config());

for i = 1:numel(sides)
    side = sides{i};
    missingBefore = mh_vta_missing_files(vta, 'Sides', {side}, 'Spaces', spaces);
    efieldPath = vta.mni.(side).efieldNii;
    if force || ~isempty(missingBefore)
        fprintf('Generating VTA/e-field: %s side %s\n', cfg.stimLabel, side);
        mh_vta_run_horn_with_retry(S, mh_util_side_to_index(side), options, ...
            cfg.stimLabel, efieldPath, 'WarningPrefix', 'mh_vta_backend_simbio_twosource');
    else
        fprintf('Reusing VTA/e-field: %s side %s\n', cfg.stimLabel, side);
    end
end

missingAfter = mh_vta_missing_files(vta, 'Sides', sides, 'Spaces', spaces);
if ~isempty(missingAfter)
    error('mh_vta_backend_simbio_twosource:MissingVTAOutput', ...
        'VTA generation did not produce required file: %s', missingAfter{1});
end
vta = mh_vta_attach_volumes(vta);
end
