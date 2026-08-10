% Open the completed PDQ-39 reference direct-voxel model as an interactive scene.
% This example intentionally creates no FIG, image, PDF, or spin export.

exampleRoot = fileparts(mfilename('fullpath'));
vizRoot = fileparts(exampleRoot);
repoRoot = fileparts(fileparts(fileparts(fileparts(vizRoot))));
addpath(genpath(repoRoot));

publicationRoot = '/Volumes/VAL/STNSNr/summary/spot/direct_voxel';
surfaceInput = fullfile( ...
    publicationRoot, 'pdq39_score', 'reference', 'visualization', ...
    'spatial_2d', 'maps', 'display.nii.gz');
finalModel = jsondecode(fileread(fullfile( ...
    publicationRoot, 'pdq39_score', 'reference', 'final_model.json')));

spec = struct();
spec.VoxelSignedNifti = surfaceInput;
spec.VoxelColorbarLabel = ...
    'Benefit-oriented partial Spearman ρ with PDQ39 score';
spec.VoxelSampleDepthMm = 0.25;
spec.AtlasName = 'Custom_STNSNr';
spec.ShowAtlasWireframe = true;
spec.AtlasRoiIndices = 2;
spec.AtlasEdgeAlpha = 0.15;
modelViews = mh_viz_default_model_views();
spec.ViewStruct = modelViews.reference{1};
spec.FigureVisible = 'on';
spec.OutputFig = '';
spec.OutputImage = '';
spec.OutputPdf = '';
spec.OutputSpin = '';
spec.CloseAfterExport = false;
pdq39VoxelScene = mh_viz_make_sweet_sour_scene(spec);

set(pdq39VoxelScene.figure, ...
    'Name', sprintf('PDQ-39 reference voxel | tau %g | Coverage %g', ...
    finalModel.selected_tau_v_per_m, ...
    finalModel.selected_coverage_subjects_min), ...
    'NumberTitle', 'off');
figure(pdq39VoxelScene.figure);
shg;
drawnow;
