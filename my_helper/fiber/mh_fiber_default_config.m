function cfg = mh_fiber_default_config(subjectDir, stimLabel)
% Create the default configuration for patient-specific Fiber/VTA visualization.

if nargin < 1 || strlength(string(subjectDir)) == 0
    error('mh_fiber_default_config:MissingSubjectDir', 'subjectDir is required.');
end
if nargin < 2 || strlength(string(stimLabel)) == 0
    stimLabel = 'clinical_L4R4_5V_L2R2_3V';
end

subjectDir = char(string(subjectDir));
if ~isfolder(subjectDir)
    error('mh_fiber_default_config:MissingSubjectDir', 'Subject directory does not exist: %s', subjectDir);
end

thisFile = mfilename('fullpath');
repoDir = fileparts(fileparts(fileparts(thisFile)));
[~, patientName] = fileparts(subjectDir);
subjectId = regexprep(patientName, '^sub-', '');

cfg = struct();
cfg.subjectDir = subjectDir;
cfg.patientName = patientName;
cfg.subjectId = subjectId;
cfg.repoDir = repoDir;
cfg.stimLabel = char(string(stimLabel));

cfg.outputRoot = fullfile(subjectDir, 'connectomics', 'fiber_vis');
cfg.outputDir = fullfile(cfg.outputRoot, cfg.stimLabel);
cfg.maxSourcesPerSide = 4;
cfg.forceRecomputeVTA = false;
cfg.forceRefilterFibers = false;
cfg.forceRegenerateFigures = false;
cfg.overwriteOutputs = false;

cfg.vta = struct();
cfg.vta.modelKey = 'simbio';
cfg.vta.model = 'SimBio/FieldTrip (see Horn 2017)';
cfg.vta.space = 'native_and_mni';
cfg.vta.gmAtlas = 'DISTAL Nano (Ewert 2017)';

cfg.paths = struct();
cfg.paths.mniFiber = fullfile(subjectDir, 'connectomics', 'dMRI', 'FTR_normalized.mat');
cfg.paths.nativeFiber = resolve_existing({ ...
    fullfile(subjectDir, 'connectomics', 'dMRI', 'FTR_anat.mat'), ...
    fullfile(subjectDir, 'connectomics', 'dMRI', 'FTR.mat')});
cfg.paths.mniReference = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 't1.nii');
cfg.paths.nativeReference = resolve_existing({ ...
    fullfile(subjectDir, 'coregistration', 'anat', [patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w.nii']), ...
    fullfile(subjectDir, 'preprocessing', 'anat', [patientName, '_ses-preop_desc-preproc_acq-iso_T1w.nii']), ...
    fullfile(subjectDir, 'preprocessing', 'anat', [patientName, '_ses-preop_acq-iso_T1w.nii'])});

cfg.paths.reconstruction = fullfile(subjectDir, 'reconstruction', [patientName, '_desc-reconstruction.mat']);

cfg.paths.stimMni = fullfile(subjectDir, 'stimulations', 'MNI152NLin2009bAsym', cfg.stimLabel);
cfg.paths.stimNative = fullfile(subjectDir, 'stimulations', 'native', cfg.stimLabel);

cfg.rois = struct();
cfg.rois.space = 'MNI152NLin2009bAsym';
cfg.rois.atlasName = 'HybraPD Whole Brain (Yu 2021)';
cfg.rois.labelingNii = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'HybraPD Whole Brain (Yu 2021).nii');
cfg.rois.labelingTxt = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'HybraPD Whole Brain (Yu 2021).txt');
cfg.rois.labels = struct('ALIC_R', 217, 'ALIC_L', 218, 'NAc_L', 305, 'NAc_R', 306);

cfg.activation = struct();
cfg.activation.mode = 'vta_intersection_efield_peak';
cfg.activation.efieldThresholdVPerM = 200;

cfg.figure = struct();
cfg.figure.maxFibersPerSide = 1200;
cfg.figure.fiberLineWidth = 0.75;
cfg.figure.roiAlpha = 0.14;
cfg.figure.vtaAlpha = 0.35;
cfg.figure.openAfterRun = true;
cfg.figure.openAnatomyControl = true;
cfg.figure.closeAfterSave = false;
cfg.figure.defaultBackdrop = 'MNI152NLin2009bAsym T1 (Fonov 2011)';
cfg.figure.defaultSliceTransparency = [100, 100, 100];
cfg.figure.showVisualizationAtlas = true;
cfg.figure.visualizationAtlas = 'NAc_ALIC (Yu 2021 and Ewert 2017)';
cfg.figure.plotExtractedRois = true;
cfg.figure.showRegionLabels = false;
cfg.figure.colors = struct( ...
    'R', [0.90, 0.18, 0.16], ...
    'L', [0.10, 0.42, 0.88], ...
    'NAc', [0.95, 0.74, 0.12], ...
    'ALIC', [0.05, 0.68, 0.42], ...
    'VTA', [0.80, 0.10, 0.10], ...
    'ElectrodeInsulation', [0.92, 0.92, 0.88]);

cfg.stimSpec = struct();

end

function path = resolve_existing(candidates)
path = candidates{1};
for i = 1:numel(candidates)
    if isfile(candidates{i})
        path = candidates{i};
        return;
    end
end
end
