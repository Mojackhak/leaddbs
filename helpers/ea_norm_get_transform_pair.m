function pair = ea_norm_get_transform_pair(options)
% Return the newest complete normalization transform pair for this subject.

pair = empty_pair;

suffixes = {
    'ants.nii.gz', 'ants'
    'ants.mat',    'ants_affine'
    'fnirt.nii.gz','fnirt'
    'fnirt.nii',   'fnirt'
};

candidates = repmat(empty_pair, 0, 1);

for idx = 1:size(suffixes, 1)
    forward = [options.subj.norm.transform.forwardBaseName, suffixes{idx, 1}];
    inverse = [options.subj.norm.transform.inverseBaseName, suffixes{idx, 1}];

    if ~isfile(forward) || ~isfile(inverse)
        continue;
    end

    forwardInfo = dir(forward);
    inverseInfo = dir(inverse);

    candidate = empty_pair;
    candidate.found = true;
    candidate.forward = forward;
    candidate.inverse = inverse;
    candidate.suffix = suffixes{idx, 1};
    candidate.format = suffixes{idx, 2};
    candidate.modified = max([forwardInfo.datenum, inverseInfo.datenum]);
    candidate.forwardModified = forwardInfo.datenum;
    candidate.inverseModified = inverseInfo.datenum;

    candidates(end+1) = candidate; %#ok<AGROW>
end

if isempty(candidates)
    return;
end

[~, newest] = max([candidates.modified]);
pair = candidates(newest);


function pair = empty_pair

pair = struct( ...
    'found', false, ...
    'forward', '', ...
    'inverse', '', ...
    'suffix', '', ...
    'format', '', ...
    'modified', 0, ...
    'forwardModified', 0, ...
    'inverseModified', 0);
