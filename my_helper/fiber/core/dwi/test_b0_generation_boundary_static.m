function test_b0_generation_boundary_static
% Verify that routine option resolution does not regenerate staged b0 images.

repoDir = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
getPtOptsPath = fullfile(repoDir, 'helpers', 'ea_getptopts.m');
prepareDwiPath = fullfile(repoDir, 'connectomics', 'ea_prepare_dti_bids.m');

getPtOptsText = fileread(getPtOptsPath);
prepareDwiText = fileread(prepareDwiPath);

assert(~contains(getPtOptsText, 'ea_ensure_b0_from_dwi('), ...
    'ea_getptopts must not generate or overwrite staged b0 images.');
assert(contains(getPtOptsText, 'if isfile(b0Path)'), ...
    'ea_getptopts must refresh BIDS fields only when the staged b0 exists.');

requiredPreparationSnippets = { ...
    'dwiStaged = false;', ...
    'dwiStaged = true;', ...
    'if dwiStaged || ~isfile(targetB0)', ...
    'ea_ensure_b0_from_dwi(options, ''Force'', dwiStaged);'};
for index = 1:numel(requiredPreparationSnippets)
    assert(contains(prepareDwiText, requiredPreparationSnippets{index}), ...
        'Missing DWI preparation boundary: %s', ...
        requiredPreparationSnippets{index});
end

fprintf('B0 generation boundary static test passed.\n');
end
