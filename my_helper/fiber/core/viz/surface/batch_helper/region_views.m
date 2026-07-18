function v = region_views()
%DBSLFP_REGION_VIEWS Return per-region view configurations.
%
% The returned struct fields are region keys (e.g., 'STN', 'SNr').
% Each field is a cell array of ViewStructs compatible with Lead-DBS
% ea_plot_patch_leaddbs.
%
% Notes:
% - The values below are copied from the original monolithic script.
% - camup is forced to [0 0 1] to keep orientation consistent.

    % SNr view 1
    vSNr1 = struct();
    vSNr1.az        = 0.8823;
    vSNr1.el        = 0.1224;
    vSNr1.camva     = 0.2886;
    vSNr1.camup     = [0 0 1];
    vSNr1.camproj   = 'orthographic';
    vSNr1.camtarget = [10.0692 -16.3838 -11.3000];
    vSNr1.campos    = [-841.9042 -1.6136e+03 476.1112];

    % SNr view 2
    vSNr2 = struct();
    vSNr2.az        = -0.8227;
    vSNr2.el        = -0.1286;
    vSNr2.camva     = 0.2886;
    vSNr2.camup     = [0 0 1];
    vSNr2.camproj   = 'orthographic';
    vSNr2.camtarget = [9.1244 -16.2821 -12.1207];
    vSNr2.campos    = [1.0473e+03 1.4861e+03 411.8152];

    % STN view 1
    vSTN1 = struct();
    vSTN1.az        = 0.8823;
    vSTN1.el        = 0.1224;
    vSTN1.camva     = 0.2886;
    vSTN1.camup     = [0 0 1];
    vSTN1.camproj   = 'orthographic';
    vSTN1.camtarget = [10.7114 -15.2873 -6.5844];
    vSTN1.campos    = [-841.2620 -1.6125e+03 480.8268];

    % STN view 2
    vSTN2 = struct();
    vSTN2.az        = -0.8227;
    vSTN2.el        = -0.1286;
    vSTN2.camva     = 0.2886;
    vSTN2.camup     = [0 0 1];
    vSTN2.camproj   = 'orthographic';
    vSTN2.camtarget = [8.5895 -16.9006 -8.6190];
    vSTN2.campos    = [1.0468e+03 1.4855e+03 415.3169];

    v = struct();
    v.STN = {vSTN1, vSTN2};
    v.SNr = {vSNr1, vSNr2};
end
