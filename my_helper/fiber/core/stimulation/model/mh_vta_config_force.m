function force = mh_vta_config_force(cfg)
% Return the VTA force-recompute flag from a config struct.

if isstruct(cfg) && isfield(cfg, 'forceRecomputeVTA')
    force = logical(cfg.forceRecomputeVTA);
else
    force = false;
end
end
