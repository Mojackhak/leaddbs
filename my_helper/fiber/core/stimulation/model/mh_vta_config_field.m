function value = mh_vta_config_field(cfg, fieldName, fallback)
% Return an optional cfg.vta field value or an explicit fallback.

if isstruct(cfg) && isfield(cfg, 'vta') && isstruct(cfg.vta) && ...
        isfield(cfg.vta, fieldName)
    value = cfg.vta.(fieldName);
else
    value = fallback;
end
end
