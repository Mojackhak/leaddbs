function result = build_stn_connected_regions_atlas(varargin)
% Build the STN-connected regions binary atlas.

addpath(genpath('/Users/mojackhu/Github/leaddbs/my_helper/atlas'));
specPath = '/Users/mojackhu/Github/leaddbs/my_helper/atlas/specs/stn_connected_regions.json';
result = mh_atlas_build_binary_atlas(specPath, varargin{:});
end
