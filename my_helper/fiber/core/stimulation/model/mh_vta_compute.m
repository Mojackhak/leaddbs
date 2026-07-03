function vta = mh_vta_compute(cfg, S, options, request)
% Compute or reuse VTA/e-field outputs through a model backend facade.

if nargin < 4 || isempty(request)
    request = struct();
end

if ~isfield(request, 'modelKey') || strlength(string(request.modelKey)) == 0
    if isfield(cfg, 'vta') && isfield(cfg.vta, 'modelKey')
        request.modelKey = cfg.vta.modelKey;
    else
        request.modelKey = 'simbio';
    end
end
entry = mh_vta_model_registry(request.modelKey);

cfg.vta.modelKey = entry.key;
cfg.vta.model = entry.modelName;
if isfield(request, 'gmAtlas') && strlength(string(request.gmAtlas)) > 0
    cfg.vta.gmAtlas = char(string(request.gmAtlas));
end

[options, settings] = mh_vta_apply_settings(options, cfg, request);
request.settings = settings;
request.modelEntry = entry;

backend = str2func(entry.backend);
vta = backend(cfg, S, options, request);
end
