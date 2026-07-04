function test_fixed_atlas_gm_mask_cache()
% Verify native Atlas Based segmentation can use a frozen GM mask cache.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));

testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
atlasDir = fullfile(testRoot, 'subject', 'atlases');
atlasName = 'Custom_Ewert_Zhang_Middlebrooks';
subjectAtlasDir = fullfile(atlasDir, atlasName);
outputDir = fullfile(testRoot, 'stim');
mh_util_make_dir(stubDir);
mh_util_make_dir(subjectAtlasDir);
mh_util_make_dir(outputDir);
oldDir = pwd;
cleanup = onCleanup(@() cleanup_test(testRoot, stubDir, oldDir));

maskLog = fullfile(testRoot, 'mask_path.txt');
fixedMask = fullfile(testRoot, 'frozen_gm_mask.nii.gz');
write_text(fixedMask, 'fixed mask');
setenv('STNSNR_TEST_MASK_LOG', maskLog);
addpath(stubDir, '-begin');
cd(testRoot);

write_text(fullfile(stubDir, 'ea_ptspecific_atl.m'), [
    "function ea_ptspecific_atl(varargin)" + newline + ...
    "error('test:ea_ptspecific_atl_called', 'ea_ptspecific_atl should not be called when fixed mask cache is available.');" + newline + ...
    "end" + newline]);
write_text(fullfile(stubDir, 'ea_convert_atlas2segmask.m'), [
    "function ea_convert_atlas2segmask(gm_mask, segmask_file, threshold)" + newline + ...
    "fid = fopen(getenv('STNSNR_TEST_MASK_LOG'), 'w');" + newline + ...
    "fprintf(fid, '%s\n%.1f\n', gm_mask, threshold);" + newline + ...
    "fclose(fid);" + newline + ...
    "fid = fopen(segmask_file, 'w');" + newline + ...
    "fprintf(fid, 'segmask');" + newline + ...
    "fclose(fid);" + newline + ...
    "end" + newline]);
rehash;
clear ea_ptspecific_atl ea_convert_atlas2segmask ea_segment_MRI;

options = struct();
options.native = true;
options.atlasset = atlasName;
options.fixedAtlasGmMaskCache = struct( ...
    'atlas_names', {{atlasName}}, ...
    'mask_paths', {{fixedMask}});
options.subj = struct();
options.subj.atlasDir = atlasDir;
options.subj.AnchorModality = 'T2w';
options.subj.preopAnat.T2w.coreg = fullfile(testRoot, 'anchor.nii');
write_text(options.subj.preopAnat.T2w.coreg, 'anchor');

settings = struct();
settings.use_wsl = false;
settings.butenko_segmAlg = 'Atlas Based';
outputPaths = struct('outputDir', outputDir);

ea_segment_MRI(options, settings, outputPaths);

assert(isfile(fullfile(outputDir, 'segmask.nii')), ...
    'Atlas Based segmentation did not copy the generated segmask.');
logText = fileread(maskLog);
assert(contains(logText, fixedMask), ...
    'Atlas Based segmentation did not use the fixed GM mask path.');
assert(contains(logText, '0.5'), ...
    'Atlas Based segmentation did not preserve the GM threshold.');
end

function write_text(path, text)
fid = fopen(path, 'w');
assert(fid > 0, 'Could not open test file for writing: %s', path);
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s', char(text));
end

function cleanup_test(testRoot, stubDir, oldDir)
if isfolder(oldDir)
    cd(oldDir);
end
if isfolder(stubDir)
    rmpath(stubDir);
end
setenv('STNSNR_TEST_MASK_LOG', '');
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
