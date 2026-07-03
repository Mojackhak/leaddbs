function vta = mh_fiber_vta_paths(cfg, stimFolders)
% Build expected Lead-DBS VTA/e-field paths for a stimulation label.

if nargin < 2 || isempty(stimFolders)
    stimFolders = struct();
    stimFolders.native = cfg.paths.stimNative;
    stimFolders.mni = cfg.paths.stimMni;
end

modelLabel = model_label_from_config(cfg);

vta = struct();
vta.native = side_paths(stimFolders.native, cfg.patientName, modelLabel);
vta.mni = side_paths(stimFolders.mni, cfg.patientName, modelLabel);

end

function modelLabel = model_label_from_config(cfg)
modelLabel = 'simbio';
if ~isfield(cfg, 'vta')
    return;
end

if isfield(cfg.vta, 'modelKey') && strlength(string(cfg.vta.modelKey)) > 0
    entry = mh_vta_model_registry(cfg.vta.modelKey);
    modelLabel = entry.modelLabel;
    return;
end

if isfield(cfg.vta, 'model') && strlength(string(cfg.vta.model)) > 0
    modelLabel = model_label_from_legacy_model(cfg.vta.model);
end
end

function modelLabel = model_label_from_legacy_model(modelName)
try
    entry = mh_vta_model_registry(modelName);
    modelLabel = entry.modelLabel;
catch
    try
        modelLabel = ea_simModel2Label(modelName);
    catch
        modelLabel = 'simbio';
    end
end
end

function paths = side_paths(stimDir, patientName, modelLabel)
paths = struct();
paths.R = one_side(stimDir, patientName, modelLabel, 'R');
paths.L = one_side(stimDir, patientName, modelLabel, 'L');
end

function side = one_side(stimDir, patientName, modelLabel, hemi)
prefix = [patientName, '_sim-'];
side = struct();
side.binaryMat = fullfile(stimDir, [prefix, 'binary_model-', modelLabel, '_hemi-', hemi, '.mat']);
side.binaryNii = fullfile(stimDir, [prefix, 'binary_model-', modelLabel, '_hemi-', hemi, '.nii']);
side.efieldNii = fullfile(stimDir, [prefix, 'efield_model-', modelLabel, '_hemi-', hemi, '.nii']);
side.efieldGaussNii = fullfile(stimDir, [prefix, 'efieldgauss_model-', modelLabel, '_hemi-', hemi, '.nii']);
end
