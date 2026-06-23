function suffix = mh_fiber_scene_file_suffix(cfg)
% Return optional filename suffix for helper-generated scene files.

suffix = '';
if isfield(cfg, 'figure') && isfield(cfg.figure, 'sceneFileSuffix')
    suffix = char(string(cfg.figure.sceneFileSuffix));
end
end
