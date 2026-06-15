function mh_fiber_validate_inputs(cfg, vta)
% Validate required inputs before running the Fiber/VTA visualization pipeline.

must_be_file(cfg.paths.mniFiber, 'MNI fiber file');
must_be_file(cfg.paths.nativeFiber, 'native fiber file');
must_be_file(cfg.paths.mniReference, 'MNI reference image');
must_be_file(cfg.paths.nativeReference, 'native reference image');
must_be_file(cfg.paths.reconstruction, 'Lead-DBS reconstruction file');
must_be_file(cfg.rois.labelingNii, 'HybraPD Whole Brain labeling NIfTI');
must_be_file(cfg.rois.labelingTxt, 'HybraPD Whole Brain label text file');

requiredVta = { ...
    vta.mni.R.binaryMat, vta.mni.R.binaryNii, vta.mni.R.efieldNii, ...
    vta.mni.L.binaryMat, vta.mni.L.binaryNii, vta.mni.L.efieldNii, ...
    vta.native.R.binaryMat, vta.native.R.binaryNii, vta.native.R.efieldNii, ...
    vta.native.L.binaryMat, vta.native.L.binaryNii, vta.native.L.efieldNii};

for i = 1:numel(requiredVta)
    must_be_file(requiredVta{i}, 'Lead-DBS VTA/e-field output');
end

end

function must_be_file(path, label)
if ~isfile(path)
    error('mh_fiber_validate_inputs:MissingFile', '%s is missing: %s', label, path);
end
end
