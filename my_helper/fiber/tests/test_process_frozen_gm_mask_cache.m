function test_process_frozen_gm_mask_cache()
% Verify process-mode task payloads carry a frozen GM mask cache.

repoDir = fileparts(fileparts(fileparts(fileparts(mfilename('fullpath')))));
addpath(genpath(repoDir));

testRoot = tempname;
stubDir = fullfile(testRoot, 'stubs');
subjectRoot = fullfile(testRoot, 'subjects');
processWorkDir = fullfile(testRoot, 'process_tasks');
subjectId = 'sub-TestSubject';
atlasName = 'Custom_Ewert_Zhang_Middlebrooks';
subjectAtlasDir = fullfile(subjectRoot, subjectId, 'atlases', atlasName);
mh_util_make_dir(stubDir);
mh_util_make_dir(subjectAtlasDir);
mh_util_make_dir(processWorkDir);
oldDir = pwd;
cleanup = onCleanup(@() cleanup_test(testRoot, stubDir, oldDir));

subjectMask = fullfile(subjectAtlasDir, 'gm_mask.nii.gz');
write_text(subjectMask, 'subject gm mask');
write_text(fullfile(stubDir, 'ea_ptspecific_atl.m'), [
    "function ea_ptspecific_atl(varargin)" + newline + ...
    "end" + newline]);
addpath(stubDir, '-begin');
cd(testRoot);
rehash;
clear ea_ptspecific_atl mh_vta_run_compute_tasks;

cfg = struct();
cfg.outputDir = fullfile(testRoot, 'outputs');
cfg.vta = struct();
cfg.vta.executionMode = 'process';
cfg.vta.parallelWorkers = 1;
cfg.vta.processDryRun = true;
cfg.vta.processWorkDir = processWorkDir;
cfg.vta.gmAtlas = atlasName;

options = struct();
options.root = [subjectRoot, filesep];
options.patientname = subjectId;
options.atlasset = atlasName;

task = struct();
task.side = 'L';
task.stim_label = 'test_stim';
task.request = struct('gmAtlas', atlasName, 'useAtlas', true);

results = mh_vta_run_compute_tasks(cfg, struct(), options, task);
payloadData = load(results.process_payload, 'payload');
payloadOptions = payloadData.payload.options;

assert(isfield(payloadOptions, 'fixedAtlasGmMaskCache'), ...
    'Process payload does not carry fixedAtlasGmMaskCache.');
cache = payloadOptions.fixedAtlasGmMaskCache;
assert(isequal(string(cache.atlas_names), string(atlasName)), ...
    'Frozen GM mask cache does not record the requested atlas.');
assert(numel(cache.mask_paths) == 1 && isfile(cache.mask_paths{1}), ...
    'Frozen GM mask cache does not point to an existing mask copy.');
assert(startsWith(string(cache.mask_paths{1}), string(processWorkDir)), ...
    'Frozen GM mask copy is not stored under the process work directory.');
assert(~strcmp(cache.mask_paths{1}, subjectMask), ...
    'Frozen GM mask cache points to the mutable subject atlas mask.');
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
if isfolder(testRoot)
    rmdir(testRoot, 's');
end
end
