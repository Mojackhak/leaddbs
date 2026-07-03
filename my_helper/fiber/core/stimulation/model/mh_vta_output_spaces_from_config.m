function spaces = mh_vta_output_spaces_from_config(cfg)
% Return default VTA request output spaces from a config struct.

if nargin < 1 || isempty(cfg)
    spaces = {'native', 'mni'};
    return;
end

if ~isfield(cfg, 'vta') || ~isfield(cfg.vta, 'space') || ...
        strlength(string(cfg.vta.space)) == 0
    spaces = {'mni'};
    return;
end

if strcmp(char(string(cfg.vta.space)), mh_vta_default_config_space())
    spaces = {'native', 'mni'};
else
    spaces = {'mni'};
end
end
