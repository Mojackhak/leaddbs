% Static regression check for checkreg percentile indexing.

repoDir = fileparts(mfilename('fullpath'));
sourcePath = fullfile(repoDir, 'ea_gencheckregpair.m');
sourceText = fileread(sourcePath);

requiredSnippets = { ...
    'ea_checkreg_percentile_index(numel(SIX), options.lbound)', ...
    'ea_checkreg_percentile_index(numel(SIX), options.ubound)', ...
    'idx = max(1, min(nValues, idx));', ...
    'if isempty(SIX)'};

for i = 1:numel(requiredSnippets)
    assert(contains(sourceText, requiredSnippets{i}), ...
        'Missing checkreg percentile indexing snippet: %s', requiredSnippets{i});
end

forbiddenSnippets = { ...
    'SIX(round(length(SIX)*options.lbound/100))', ...
    'SIX(round(length(SIX)*options.ubound/100))'};

for i = 1:numel(forbiddenSnippets)
    assert(~contains(sourceText, forbiddenSnippets{i}), ...
        'Checkreg percentile indexing should not use snippet: %s', forbiddenSnippets{i});
end

fprintf('Checkreg percentile indexing static check passed.\n');
