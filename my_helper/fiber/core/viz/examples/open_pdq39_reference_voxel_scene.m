% Open the completed PDQ-39 reference direct-voxel model as an interactive scene.
% This example intentionally creates no FIG, image, PDF, or spin export.

exampleRoot = fileparts(mfilename('fullpath'));
vizRoot = fileparts(exampleRoot);
repoRoot = fileparts(fileparts(fileparts(fileparts(vizRoot))));
addpath(genpath(repoRoot));

runRoot = ['/Volumes/VAL/STNSNr/summary/spot/.runs/', ...
    'stnsnr_frequency_addon/', ...
    'task17-main-v8-tau-grid-formal-20260717'];
pdq39VoxelInput = mh_viz_prepare_scene_example_input( ...
    runRoot, 'reference_voxel', 'ScaleId', 'pdq39_score');

spec = struct();
spec.VoxelSignedNifti = pdq39VoxelInput.input_path;
spec.VoxelColorbarLabel = 'PDQ-39 benefit-oriented voxel weight';
spec.FigureVisible = 'on';
spec.OutputFig = '';
spec.OutputImage = '';
spec.OutputPdf = '';
spec.OutputSpin = '';
spec.CloseAfterExport = false;
pdq39VoxelScene = mh_viz_make_sweet_sour_scene(spec);

set(pdq39VoxelScene.figure, ...
    'Name', sprintf('PDQ-39 reference voxel | tau %g | Coverage %g', ...
    pdq39VoxelInput.selected_tau, pdq39VoxelInput.selected_coverage), ...
    'NumberTitle', 'off');
figure(pdq39VoxelScene.figure);
shg;
drawnow;
