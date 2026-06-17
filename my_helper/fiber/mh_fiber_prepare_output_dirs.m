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
dirs.seedTarget = struct();
dirs.seedTarget.root = fullfile(dirs.root, 'seed_target');
dirs.seedTarget.native = fullfile(dirs.seedTarget.root, 'native');
dirs.seedTarget.mni = fullfile(dirs.seedTarget.root, 'mni');
dirs.seedTarget.rois = fullfile(dirs.seedTarget.root, 'rois');
dirs.seedTarget.qc = fullfile(dirs.seedTarget.root, 'qc');
dirs.seedTarget.reports = fullfile(dirs.seedTarget.root, 'reports');
dirs.seedTarget.work = fullfile(dirs.seedTarget.root, 'work');
dirs.seedVtaSift2 = struct();
dirs.seedVtaSift2.root = fullfile(dirs.root, 'seed_vta_sift2');
dirs.seedVtaSift2.tracks = fullfile(dirs.seedVtaSift2.root, 'tracks');
dirs.seedVtaSift2.density = fullfile(dirs.seedVtaSift2.root, 'density');
dirs.seedVtaSift2.display = fullfile(dirs.seedVtaSift2.root, 'display');
dirs.seedVtaSift2.figures = fullfile(dirs.seedVtaSift2.root, 'figures');
dirs.seedVtaSift2.reports = fullfile(dirs.seedVtaSift2.root, 'reports');
dirs.seedVtaSift2.work = fullfile(dirs.seedVtaSift2.root, 'work');

fields = fieldnames(dirs);
for i = 1:numel(fields)
    value = dirs.(fields{i});
    if isstruct(value)
        nestedFields = fieldnames(value);
        for j = 1:numel(nestedFields)
            ea_mkdir(value.(nestedFields{j}));
        end
    else
        ea_mkdir(value);
    end
end

end
