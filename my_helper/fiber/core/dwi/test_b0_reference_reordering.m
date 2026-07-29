% Validate last-b0 selection, eddy ordering, and source-order restoration.

repoDir = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
addpath(genpath(repoDir));

testDir = tempname;
mkdir(testDir);
cleanupObj = onCleanup(@() rmdir(testDir, 's')); %#ok<NASGU>

dwiPath = fullfile(testDir, 'source.nii');
bvalPath = fullfile(testDir, 'source.bval');
bvecPath = fullfile(testDir, 'source.bvec');
data = zeros(5, 4, 3, 4, 'single');
for volume = 1:4
    data(:, :, :, volume) = volume;
end
niftiwrite(data, dwiPath);
write_text(bvalPath, '0 1000 0 1000\n');
write_text(bvecPath, sprintf('0 1 0 0\n0 0 0 1\n0 0 0 0\n'));

prepared = mh_fiber_prepare_eddy_b0_reference(dwiPath, bvalPath, ...
    bvecPath, fullfile(testDir, 'work'), 'last', 10, true);
assert(prepared.selected_source_index_one_based == 3, ...
    'The final b0 source volume should be selected.');
assert(isequal(prepared.eddy_to_source_one_based, [3 1 2 4]), ...
    'The selected b0 should be first in eddy order.');
assert(isequal(prepared.source_to_eddy_one_based, [2 3 1 4]), ...
    'The inverse eddy mapping is incorrect.');
assert(all(spm_read_vols(spm_vol(prepared.referenceB0)) == 3, 'all'), ...
    'The selected b0 image does not contain source volume 3.');
assert(isequal(mh_fiber_load_bval(prepared.inputBval), [0 0 1000 1000]), ...
    'b-values were not reordered with the DWI.');

restoredDwi = fullfile(testDir, 'restored.nii');
restoredBval = fullfile(testDir, 'restored.bval');
restoredBvec = fullfile(testDir, 'restored.bvec');
mh_fiber_reorder_dwi_series(prepared.inputDwi, prepared.inputBval, ...
    prepared.inputBvec, restoredDwi, restoredBval, restoredBvec, ...
    prepared.source_to_eddy_one_based, true);
restored = spm_read_vols(spm_vol(restoredDwi));
for volume = 1:4
    assert(all(restored(:, :, :, volume) == volume, 'all'), ...
        'Restored DWI volume %d does not match source order.', volume);
end
assert(isequal(mh_fiber_load_bval(restoredBval), [0 1000 0 1000]), ...
    'Restored b-values do not match source order.');
assert(max(abs(load(restoredBvec) - load(bvecPath)), [], 'all') < 1e-12, ...
    'Restored b-vectors do not match source order.');

fprintf('Last-b0 reference reordering test passed.\n');

function write_text(path, content)
fid = fopen(path, 'w');
assert(fid >= 0, 'Could not create test file: %s', path);
cleanup = onCleanup(@() fclose(fid)); %#ok<NASGU>
fprintf(fid, '%s', content);
end
