% Open the PDQ-39 reference fiber coefficients as an interactive 3D scene.
% This example intentionally creates no FIG, image, PDF, or spin export.

exampleRoot = fileparts(mfilename('fullpath'));
vizRoot = fileparts(exampleRoot);
repoRoot = fileparts(fileparts(fileparts(fileparts(vizRoot))));
addpath(genpath(repoRoot));

publicationRoot = ['/Volumes/VAL/STNSNr/summary/spot/normative_fiber/', ...
    'dual_frequency_four_model_v1'];
pdq39FiberInput = mh_viz_prepare_scene_example_input( ...
    publicationRoot, 'reference_fiber', 'ScaleId', 'pdq39_score');

fiberStyle = mh_viz_default_fiber_scene_spec();
spec = struct();
spec.FiberCoefficientMat = pdq39FiberInput.input_path;
spec.FiberColorbarLabel = sprintf( ...
    'Benefit-oriented partial Spearman ρ with %s', ...
    pdq39FiberInput.scale_display_name);
spec.AtlasName = 'Custom_STNSNr';
spec.ShowAtlasWireframe = true;
spec.AtlasRoiIndices = 2;
spec.AtlasEdgeAlpha = 0.15;
spec.CoefficientFiberAlpha = fiberStyle.CoefficientFiberAlpha;
spec.CoefficientFiberLineWidth = fiberStyle.CoefficientFiberLineWidth;
spec.FiberColorbarTextColor = fiberStyle.FiberColorbarTextColor;
spec.ShowFiberLegend = false;
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
pdq39FiberCoefficientScene = mh_viz_make_sweet_sour_scene(spec);

set(pdq39FiberCoefficientScene.figure, ...
    'Name', sprintf( ...
    'PDQ-39 reference fiber coefficients | tau %g | Coverage %g', ...
    pdq39FiberInput.selected_tau, pdq39FiberInput.selected_coverage), ...
    'NumberTitle', 'off');
figure(pdq39FiberCoefficientScene.figure);
shg;
drawnow;
