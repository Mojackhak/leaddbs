function result = build_snr_connected_regions_atlas(varargin)
% Build the SNr-connected regions binary atlas.

addpath(genpath('/Users/mojackhu/Github/leaddbs/my_helper/atlas'));
specPath = '/Users/mojackhu/Github/leaddbs/my_helper/atlas/specs/snr_connected_regions.json';
result = mh_atlas_build_binary_atlas(specPath, varargin{:});
end
