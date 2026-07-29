function spec = mh_viz_default_fiber_scene_spec()
% Return categorical fiber-only scene defaults.

spec = struct();
spec.CandidateFiberColor = [204, 204, 204] / 255;
spec.CandidateFiberAlpha = 1.0;
spec.CandidateFiberLineWidth = 0.25;
spec.CoefficientFiberAlpha = 1.0;
spec.CoefficientFiberLineWidth = 0.25;
spec.SweetFiberColor = [242, 0, 14] / 255;
spec.SourFiberColor = [14, 106, 175] / 255;
spec.SelectedFiberAlpha = 1.0;
spec.SelectedFiberRenderMode = 'line';
spec.SelectedFiberLineWidth = 0.50;
spec.FiberLegendTextColor = [1, 1, 1];
spec.FiberColorbarTextColor = [1, 1, 1];
spec.BackgroundColor = [0, 0, 0];
spec.AddRASTriad = false;
spec.ShowAnatomySlices = true;
spec.AnatomySliceAlpha = 1.0;
spec.AnatomyNifti = [ ...
    '/Users/mojackhu/Github/leaddbs/templates/space/', ...
    'MNI152NLin2009bAsym/backdrops/7T_100um_Edlow_2019.nii'];
spec.AnatomySlicePlane = 'x';
spec.AnatomySliceCoordinateMm = 5;
spec.AnatomySliceTransparencyPercent = 100;
end
