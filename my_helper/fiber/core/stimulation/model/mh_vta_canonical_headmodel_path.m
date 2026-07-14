function path = mh_vta_canonical_headmodel_path(subjectDir, subjectId, sideIndex)
% Return the fixed native canonical head-model path.

validateattributes(sideIndex, {'numeric'}, ...
    {'scalar', 'integer', '>=', 1, '<=', 2}, mfilename, 'sideIndex');
id = regexprep(char(string(subjectId)), '^sub-', '');
path = fullfile(char(string(subjectDir)), 'headmodel', 'native', ...
    sprintf('sub-%s_desc-headmodel%d.mat', id, sideIndex));
end
