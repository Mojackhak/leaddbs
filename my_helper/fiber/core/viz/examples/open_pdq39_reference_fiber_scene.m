% Open the completed PDQ-39 reference normative-fiber model as an interactive scene.
% This example intentionally creates no FIG, image, PDF, or spin export.

exampleRoot = fileparts(mfilename('fullpath'));
vizRoot = fileparts(exampleRoot);
repoRoot = fileparts(fileparts(fileparts(fileparts(vizRoot))));
addpath(genpath(repoRoot));

publicationRoot = '/Volumes/VAL/STNSNr/summary/spot/normative_fiber';
pdq39FiberInput = mh_viz_prepare_scene_example_input( ...
    publicationRoot, 'reference_fiber', 'ScaleId', 'pdq39_score');

spec = struct();
spec.FiberCategoricalMat = pdq39FiberInput.input_path;
spec.AtlasName = 'Custom_STNSNr';
spec.ShowAtlasWireframe = true;
spec.AtlasRoiIndices = 2;
spec.AtlasEdgeAlpha = 0.15;
fiberStyle = mh_viz_default_fiber_scene_spec();
spec.CandidateFiberColor = fiberStyle.CandidateFiberColor;
spec.CandidateFiberAlpha = fiberStyle.CandidateFiberAlpha;
spec.SweetFiberColor = fiberStyle.SweetFiberColor;
spec.SourFiberColor = fiberStyle.SourFiberColor;
spec.SelectedFiberRenderMode = fiberStyle.SelectedFiberRenderMode;
spec.SelectedFiberLineWidth = fiberStyle.SelectedFiberLineWidth;
spec.FiberLegendTextColor = fiberStyle.FiberLegendTextColor;
spec.BackgroundColor = fiberStyle.BackgroundColor;
spec.AddRASTriad = fiberStyle.AddRASTriad;
spec.ShowAnatomySlices = fiberStyle.ShowAnatomySlices;
spec.AnatomyNifti = fiberStyle.AnatomyNifti;
spec.AnatomySlicePlane = fiberStyle.AnatomySlicePlane;
spec.AnatomySliceCoordinateMm = fiberStyle.AnatomySliceCoordinateMm;
spec.AnatomySliceTransparencyPercent = ...
    fiberStyle.AnatomySliceTransparencyPercent;
fiberViews = mh_viz_default_fiber_views();
spec.ViewStruct = fiberViews.reference{1};
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
