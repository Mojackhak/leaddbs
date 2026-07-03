function vta = mh_fiber_ensure_vta(cfg, S, options, stimFolders)
% Ensure bilateral native and MNI VTA/e-field files through the VTA facade.

request = struct();
request.modelKey = 'simbio';
request.stimFolders = stimFolders;
request.force = cfg.forceRecomputeVTA;
request.sides = {'R', 'L'};
request.outputSpaces = {'native', 'mni'};

vta = mh_vta_compute(cfg, S, options, request);
end
