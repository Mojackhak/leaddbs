% Static regression check for EasyReg transform-field loading.

repoDir = fileparts(fileparts(fileparts(mfilename('fullpath'))));
sourcePath = fullfile(repoDir, 'ext_libs', 'EasyReg', 'ea_easyreg.m');
sourceText = fileread(sourcePath);

requiredSnippets = { ...
    'n = load_untouch_nii(warp_file_in);', ...
    'ea_get_affine(warp_file_in)', ...
    'ea_itk_grid_fixed_parameters(warp_file_in)'};

for i = 1:numel(requiredSnippets)
    assert(contains(sourceText, requiredSnippets{i}), ...
        'Missing EasyReg warp-field conversion snippet: %s', requiredSnippets{i});
end

forbiddenSnippets = { ...
    'n = load_nii(warp_file_in);'};

for i = 1:numel(forbiddenSnippets)
    assert(~contains(sourceText, forbiddenSnippets{i}), ...
        'EasyReg warp-field conversion should not use snippet: %s', forbiddenSnippets{i});
end

fprintf('EasyReg warp-field untouch loader static check passed.\n');
