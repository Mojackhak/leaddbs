function views = mh_viz_default_model_views()
% Return the frozen reference and add-on camera views for 3D exports.

reference1 = struct();
reference1.az = 0.8823;
reference1.el = 0.1224;
reference1.camva = 0.3500;
reference1.camup = [0 0 1];
reference1.camproj = 'orthographic';
reference1.camtarget = [9.8725 -14.8273 -6.5437];
reference1.campos = [-841.1497 -1.6125e+03 481.0182];

reference2 = struct();
reference2.az = -0.8227;
reference2.el = -0.1286;
reference2.camva = 0.3500;
reference2.camup = [0 0 1];
reference2.camproj = 'orthographic';
reference2.camtarget = [8.5895 -16.9006 -8.6190];
reference2.campos = [1.0468e+03 1.4855e+03 415.3169];

addon1 = struct();
addon1.az = 0.8823;
addon1.el = 0.1224;
addon1.camva = 0.5000;
addon1.camup = [0 0 1];
addon1.camproj = 'orthographic';
addon1.camtarget = [9.6266 -16.6089 -12.8113];
addon1.campos = [-842.3468 -1.6138e+03 474.5999];

addon2 = struct();
addon2.az = -0.8227;
addon2.el = -0.1286;
addon2.camva = 0.5000;
addon2.camup = [0 0 1];
addon2.camproj = 'orthographic';
addon2.camtarget = [9.1244 -16.2821 -12.1207];
addon2.campos = [1.0473e+03 1.4861e+03 411.8152];

views = struct();
views.reference = {reference1, reference2};
views.addon = {addon1, addon2};
end
