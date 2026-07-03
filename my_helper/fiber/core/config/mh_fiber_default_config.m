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
repoDir = resolve_repo_dir(thisFile);
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
cfg.vta.parallel = false;
cfg.vta.parallelWorkers = 1;
cfg.vta.executionMode = 'sequential';

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
cfg.paths.dwi = fullfile(subjectDir, 'preprocessing', 'dwi', [patientName, '_ses-preop_acq-iso_dwi.nii']);
cfg.paths.dwiBvec = fullfile(subjectDir, 'preprocessing', 'dwi', [patientName, '_ses-preop_acq-iso_dwi.bvec']);
cfg.paths.dwiBval = fullfile(subjectDir, 'preprocessing', 'dwi', [patientName, '_ses-preop_acq-iso_dwi.bval']);
cfg.paths.dwiB0 = fullfile(subjectDir, 'preprocessing', 'dwi', [patientName, '_ses-preop_acq-iso_dwi_b0.nii']);
cfg.paths.brainMask = fullfile(subjectDir, 'preprocessing', 'dwi', 'brainmask.nii');
cfg.paths.trackingMask = fullfile(subjectDir, 'preprocessing', 'dwi', 'trackingmask.nii');

cfg.paths.reconstruction = fullfile(subjectDir, 'reconstruction', [patientName, '_desc-reconstruction.mat']);

cfg.paths.stimMni = fullfile(subjectDir, 'stimulations', 'MNI152NLin2009bAsym', cfg.stimLabel);
cfg.paths.stimNative = fullfile(subjectDir, 'stimulations', 'native', cfg.stimLabel);
cfg.paths.anchorToDwiTransform = resolve_existing({ ...
    fullfile(subjectDir, 'coregistration', 'dwi', [patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w2', patientName, '_ses-preop_acq-iso_dwi_b0_ants1.mat']), ...
    fullfile(subjectDir, 'coregistration', 'anat', [patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w2', patientName, '_ses-preop_acq-iso_dwi_b0_ants1.mat'])});
cfg.paths.dwiToAnchorTransform = resolve_existing({ ...
    fullfile(subjectDir, 'coregistration', 'dwi', [patientName, '_ses-preop_acq-iso_dwi_b02', patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w_ants1.mat']), ...
    fullfile(subjectDir, 'coregistration', 'anat', [patientName, '_ses-preop_acq-iso_dwi_b02', patientName, '_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w_ants1.mat'])});
cfg.paths.anchorToMniTransform = fullfile(subjectDir, 'normalization', 'transformations', [patientName, '_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz']);

cfg.rois = struct();
cfg.rois.space = 'MNI152NLin2009bAsym';
cfg.rois.atlasName = 'HybraPD Whole Brain (Yu 2021)';
cfg.rois.labelingNii = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'HybraPD Whole Brain (Yu 2021).nii');
cfg.rois.labelingTxt = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'HybraPD Whole Brain (Yu 2021).txt');
cfg.rois.labels = struct('ALIC_R', 217, 'ALIC_L', 218, 'NAc_L', 305, 'NAc_R', 306);
cfg.rois.aal3Name = 'Automated Anatomical Labeling 3 (Rolls 2020)';
cfg.rois.aal3Nii = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'Automated Anatomical Labeling 3 (Rolls 2020).nii');
cfg.rois.aal3Txt = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'Automated Anatomical Labeling 3 (Rolls 2020).txt');
cfg.rois.hammersName = 'Hammers_mith Atlas n30r95 (Hammers 2003 Gousias 2008 Faillenot 2017)';
cfg.rois.hammersNii = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'Hammers_mith Atlas n30r95 (Hammers 2003 Gousias 2008 Faillenot 2017).nii');
cfg.rois.hammersTxt = fullfile(repoDir, 'templates', 'space', 'MNI152NLin2009bAsym', 'labeling', 'Hammers_mith Atlas n30r95 (Hammers 2003 Gousias 2008 Faillenot 2017).txt');

cfg.activation = struct();
cfg.activation.mode = 'vta_intersection_efield_peak';
cfg.activation.efieldThresholdVPerM = 200;

cfg.seedTarget = struct();
cfg.seedTarget.enabled = true;
cfg.seedTarget.backend = 'mrtrix_ifod2';
cfg.seedTarget.force = false;
cfg.seedTarget.resume = true;
cfg.seedTarget.forceFod = false;
cfg.seedTarget.seedVariants = {'exact', 'interface'};
cfg.seedTarget.sides = {'R', 'L'};
cfg.seedTarget.seedNames = {'NAc', 'ALIC'};
cfg.seedTarget.targetNames = {'NAc', 'ALIC', 'mPFC', 'OFC', 'ACC', 'amygdala', 'hippocampus', 'thalamus', 'VTA'};
cfg.seedTarget.skipSelfTargets = true;
cfg.seedTarget.interfaceDilatePasses = 2;
cfg.seedTarget.select = 5000;
cfg.seedTarget.seeds = 500000;
cfg.seedTarget.cutoff = 0.06;
cfg.seedTarget.minLength = 10;
cfg.seedTarget.maxLength = 250;
cfg.seedTarget.parallel = true;
cfg.seedTarget.parallelWorkers = 16;
cfg.seedTarget.threads = 1;
cfg.seedTarget.displayMaxStreamlinesPerBundle = 500;
cfg.seedTarget.displayPointStride = 1;
cfg.seedTarget.writeVtk = true;
cfg.seedTarget.writeDensity = true;
cfg.seedTarget.mrtrixPathPrefix = '/usr/local/bin';
cfg.seedTarget.allowBrainMaskFallbackToTrackingMask = true;

cfg.seedVtaSift2 = struct();
cfg.seedVtaSift2.enabled = true;
cfg.seedVtaSift2.force = false;
cfg.seedVtaSift2.resume = true;
cfg.seedVtaSift2.seedNames = {'NAc', 'ALIC'};
cfg.seedVtaSift2.targetNames = {'mPFC', 'OFC', 'ACC', 'amygdala', 'hippocampus', 'thalamus', 'VTA'};
cfg.seedVtaSift2.sides = {'R', 'L'};
cfg.seedVtaSift2.wholebrainSelect = 5000000;
cfg.seedVtaSift2.displayBudget = 8000;
cfg.seedVtaSift2.displayBudgetMode = 'global';
cfg.seedVtaSift2.randomSeed = 1;
cfg.seedVtaSift2.useAct = true;
cfg.seedVtaSift2.forceWholebrain = false;
cfg.seedVtaSift2.forceSift2 = false;
cfg.seedVtaSift2.forceDownstream = false;
cfg.seedVtaSift2.force5tt = false;
cfg.seedVtaSift2.displayPointStride = 1;
cfg.seedVtaSift2.writeDensity = true;
cfg.seedVtaSift2.writeScene = true;
cfg.seedVtaSift2.seedVtaRoiDefaultVisible = false;
cfg.seedVtaSift2.mrtrixPathPrefix = '/usr/local/bin';

cfg.figure = struct();
cfg.figure.maxFibersPerSide = 1200;
cfg.figure.fiberLineWidth = 0.75;
cfg.figure.fiberAlpha = 0.10;
cfg.figure.roiAlpha = 0.20;
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
cfg.figure.sceneFileSuffix = '';
cfg.figure.electrodeDisplayLengthMm = 200;
cfg.figure.electrodeDisplayRadiusMm = 0.65;
cfg.figure.colors = struct( ...
    'R', [0.90, 0.18, 0.16], ...
    'L', [0.10, 0.42, 0.88], ...
    'NAc', [0.5098, 0.8196, 0.2627], ...
    'ALIC', [0.1882, 0.4392, 0.7176], ...
    'VTA', [0.80, 0.10, 0.10], ...
    'ElectrodeContact', [0.00, 0.00, 0.00], ...
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

function repoDir = resolve_repo_dir(startPath)
repoDir = fileparts(startPath);
while strlength(string(repoDir)) > 0
    if isfolder(fullfile(repoDir, 'templates')) && isfolder(fullfile(repoDir, 'my_helper'))
        return;
    end
    parentDir = fileparts(repoDir);
    if strcmp(parentDir, repoDir)
        break;
    end
    repoDir = parentDir;
end
error('mh_fiber_default_config:RepoRootNotFound', ...
    'Cannot resolve Lead-DBS repo root from: %s', startPath);
end
