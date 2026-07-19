% Open the completed PDQ-39 reference normative-fiber model as an interactive scene.
% This example intentionally creates no FIG, image, PDF, or spin export.

exampleRoot = fileparts(mfilename('fullpath'));
vizRoot = fileparts(exampleRoot);
repoRoot = fileparts(fileparts(fileparts(fileparts(vizRoot))));
addpath(genpath(repoRoot));

publicationRoot = ['/Volumes/VAL/STNSNr/summary/spot/normative_fiber/', ...
    'dual_frequency_four_model_v1'];
pdq39FiberInput = mh_viz_prepare_scene_example_input( ...
    publicationRoot, 'reference_fiber', 'ScaleId', 'pdq39_score');

spec = struct();
spec.FiberScoreMat = pdq39FiberInput.input_path;
spec.FiberColorbarLabel = 'PDQ-39 benefit-oriented fiber weight';
spec.FigureVisible = 'on';
spec.OutputFig = '';
spec.OutputImage = '';
spec.OutputPdf = '';
spec.OutputSpin = '';
spec.CloseAfterExport = false;
pdq39FiberScene = mh_viz_make_sweet_sour_scene(spec);

set(pdq39FiberScene.figure, ...
    'Name', sprintf('PDQ-39 reference fiber | tau %g | Coverage %g', ...
    pdq39FiberInput.selected_tau, pdq39FiberInput.selected_coverage), ...
    'NumberTitle', 'off');
figure(pdq39FiberScene.figure);
shg;
drawnow;
