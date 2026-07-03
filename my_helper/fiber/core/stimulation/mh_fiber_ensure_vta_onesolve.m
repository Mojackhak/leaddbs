function vta = mh_fiber_ensure_vta_onesolve(cfg, S, options, stimFolders)
% Ensure one-solve multi-voltage VTA/e-field files through the VTA facade.

request = struct();
request.modelKey = 'simbio_onesolve';
request.stimFolders = stimFolders;
request.force = cfg.forceRecomputeVTA;
request.sides = {'R', 'L'};
request.outputSpaces = mh_vta_output_spaces_from_config();

vta = mh_vta_compute(cfg, S, options, request);
end
