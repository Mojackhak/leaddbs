function names = mh_vta_expected_artifact_names(thresholdsVPerM)
% Return canonical E-field and threshold artifact names in output order.

validateattributes(thresholdsVPerM, {'numeric'}, ...
    {'real', 'finite', 'vector', 'positive'}, mfilename, 'thresholdsVPerM');
thresholdsVPerM = double(thresholdsVPerM(:));
names = strings(numel(thresholdsVPerM) + 1, 1);
names(1) = "efield.nii.gz";
for thresholdIndex = 1:numel(thresholdsVPerM)
    token = strrep(sprintf('%.2f', ...
        thresholdsVPerM(thresholdIndex) / 1000), '.', 'p');
    names(thresholdIndex + 1) = ...
        "vta_threshold-" + token + "Vpermm.nii.gz";
end
end
