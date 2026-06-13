function pairs = ea_norm_get_transform_pair(options)
% Return complete normalization transform pairs for this subject/template.

pairs = repmat(empty_pair, 0, 1);

suffixes = {
    'ants.nii.gz',  'ants',        'ANTs-compatible'
    'ants.mat',     'ants_affine', 'ANTs affine / Three-step'
    'fnirt.nii.gz', 'fnirt',       'FNIRT'
    'fnirt.nii',    'fnirt',       'FNIRT'
};

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
    candidate.method = suffixes{idx, 2};
    candidate.label = suffixes{idx, 3};
    candidate.modified = max([forwardInfo.datenum, inverseInfo.datenum]);
    candidate.forwardModified = forwardInfo.datenum;
    candidate.inverseModified = inverseInfo.datenum;

    if ~any(strcmp({pairs.method}, candidate.method))
        pairs(end+1) = candidate; %#ok<AGROW>
    end
end


function pair = empty_pair

pair = struct( ...
    'found', false, ...
    'forward', '', ...
    'inverse', '', ...
    'suffix', '', ...
    'format', '', ...
    'method', '', ...
    'label', '', ...
    'modified', 0, ...
    'forwardModified', 0, ...
    'inverseModified', 0);
