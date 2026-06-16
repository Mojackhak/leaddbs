function mh_fiber_validate_inputs(cfg, vta)
% Validate required inputs before running the Fiber/VTA visualization pipeline.

must_be_file(cfg.paths.mniFiber, 'MNI fiber file');
must_be_file(cfg.paths.nativeFiber, 'native fiber file');
must_be_file(cfg.paths.mniReference, 'MNI reference image');
must_be_file(cfg.paths.nativeReference, 'native reference image');
must_be_file(cfg.paths.reconstruction, 'Lead-DBS reconstruction file');
must_be_file(cfg.rois.labelingNii, 'HybraPD Whole Brain labeling NIfTI');
must_be_file(cfg.rois.labelingTxt, 'HybraPD Whole Brain label text file');
if isfield(cfg.rois, 'aal3Nii')
    must_be_file(cfg.rois.aal3Nii, 'AAL3 labeling NIfTI');
end
if isfield(cfg.rois, 'aal3Txt')
    must_be_file(cfg.rois.aal3Txt, 'AAL3 label text file');
end
if isfield(cfg.rois, 'hammersNii')
    must_be_file(cfg.rois.hammersNii, 'Hammers label NIfTI');
end
if isfield(cfg.rois, 'hammersTxt')
    must_be_file(cfg.rois.hammersTxt, 'Hammers label text file');
end

requiredVta = { ...
    vta.mni.R.binaryMat, vta.mni.R.binaryNii, vta.mni.R.efieldNii, ...
    vta.mni.L.binaryMat, vta.mni.L.binaryNii, vta.mni.L.efieldNii, ...
    vta.native.R.binaryMat, vta.native.R.binaryNii, vta.native.R.efieldNii, ...
    vta.native.L.binaryMat, vta.native.L.binaryNii, vta.native.L.efieldNii};

for i = 1:numel(requiredVta)
    must_be_file(requiredVta{i}, 'Lead-DBS VTA/e-field output');
end

if isfield(cfg, 'seedTarget') && isfield(cfg.seedTarget, 'enabled') && cfg.seedTarget.enabled
    must_be_file(cfg.paths.dwi, 'DWI image');
    must_be_file(cfg.paths.dwiBvec, 'DWI bvec file');
    must_be_file(cfg.paths.dwiBval, 'DWI bval file');
    must_be_file(cfg.paths.dwiB0, 'DWI b0 reference image');
    must_be_file(cfg.paths.brainMask, 'DWI brain mask');
    must_be_file(cfg.paths.trackingMask, 'DWI tracking mask');
    must_be_file(cfg.paths.anchorToDwiTransform, 'anchorNative-to-DWI ANTs transform');
    must_be_file(cfg.paths.dwiToAnchorTransform, 'DWI-to-anchorNative ANTs transform');
    must_be_file(cfg.paths.anchorToMniTransform, 'anchorNative-to-MNI ANTs transform');
    must_have_command('mrconvert');
    must_have_command('dwi2response');
    must_have_command('dwi2fod');
    must_have_command('tckgen');
    must_have_command('tckedit');
    must_have_command('tckmap');
    must_have_command('tckstats');
    must_have_command('tckconvert');
    must_have_command('maskfilter');
    must_have_command('mrcalc');
    must_have_command('mrstats');
end

end

function must_be_file(path, label)
if ~isfile(path)
    error('mh_fiber_validate_inputs:MissingFile', '%s is missing: %s', label, path);
end
end

function must_have_command(commandName)
[status, resolved] = system(sprintf('command -v %s', commandName));
if status ~= 0 || strlength(strtrim(string(resolved))) == 0
    error('mh_fiber_validate_inputs:MissingCommand', ...
        'Required MRtrix3 command is not available on PATH: %s', commandName);
end
end
