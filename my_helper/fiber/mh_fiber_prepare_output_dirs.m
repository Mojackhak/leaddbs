function dirs = mh_fiber_prepare_output_dirs(cfg)
% Create the output directory tree for one stimulation label.

dirs = struct();
dirs.root = cfg.outputDir;
dirs.rois = fullfile(dirs.root, 'rois');
dirs.fibersMni = fullfile(dirs.root, 'fibers_mni');
dirs.fibersNative = fullfile(dirs.root, 'fibers_native');
dirs.activation = fullfile(dirs.root, 'activation');
dirs.figures = fullfile(dirs.root, 'figures');
dirs.reports = fullfile(dirs.root, 'reports');

fields = fieldnames(dirs);
for i = 1:numel(fields)
    ea_mkdir(dirs.(fields{i}));
end

end
