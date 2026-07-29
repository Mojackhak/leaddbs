function views = mh_viz_default_fiber_views()
% Return the default single camera view for categorical fiber exports.

fiberView = struct();
fiberView.az = 0;
fiberView.el = 0;
fiberView.camva = 3.8000;
fiberView.camup = [0 0 1];
fiberView.camproj = 'orthographic';
fiberView.camtarget = [9.8538 -48.8761 9.6955];
fiberView.campos = [1.8846e+03 -48.8761 9.6955];

views = struct();
views.reference = {fiberView};
views.addon = {fiberView};
end
