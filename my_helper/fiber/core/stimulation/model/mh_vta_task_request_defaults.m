function defaults = mh_vta_task_request_defaults(cfg, stimSpec)
% Return parser defaults shared by VTA task request runners.

if nargin < 1 || isempty(cfg)
    cfg = struct();
end
if nargin < 2 || isempty(stimSpec)
    stimSpec = struct();
end

defaults = struct();
defaults.modelKey = resolve_model_key(cfg, stimSpec);
defaults.force = mh_vta_config_force(cfg);
defaults.outputSpaces = mh_vta_output_spaces_from_config(cfg);
defaults.gmAtlas = resolve_gm_atlas(cfg);
end

function modelKey = resolve_model_key(cfg, stimSpec)
if isstruct(stimSpec) && isfield(stimSpec, 'model') && ...
        strlength(string(stimSpec.model)) > 0
    modelKey = char(string(stimSpec.model));
elseif isstruct(cfg) && isfield(cfg, 'vta') && isfield(cfg.vta, 'modelKey') && ...
        strlength(string(cfg.vta.modelKey)) > 0
    modelKey = char(string(cfg.vta.modelKey));
else
    modelKey = mh_vta_default_model_key();
end
end

function atlas = resolve_gm_atlas(cfg)
if isstruct(cfg) && isfield(cfg, 'vta') && isfield(cfg.vta, 'gmAtlas')
    atlas = cfg.vta.gmAtlas;
else
    atlas = '';
end
end
