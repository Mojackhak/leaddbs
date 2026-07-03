function paths = mh_coverage_write_standard_masks(ref, outputDir, baseLabel, vtaMask, categoryImg, overlapMask, varargin)
% Write standard VTA, category, and program-overlap masks on a reference grid.

parser = inputParser;
parser.FunctionName = 'mh_coverage_write_standard_masks';
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('VtaDescription', 'thresholded vta', @(x) ischar(x) || isstring(x));
parser.addParameter('CategoryDescription', 'vta category', @(x) ischar(x) || isstring(x));
parser.addParameter('OverlapDescription', 'program overlap', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

baseLabel = char(string(baseLabel));
paths = struct();
paths.vta = fullfile(outputDir, [baseLabel, '_desc-vta.nii']);
paths.category = fullfile(outputDir, [baseLabel, '_desc-vtaCategory.nii']);
paths.overlap = fullfile(outputDir, [baseLabel, '_desc-vtaProgramOverlap.nii']);

if logical(opts.Force) || ~isfile(paths.vta)
    mh_coverage_write_ref_nii(ref, double(vtaMask), paths.vta, 2, char(string(opts.VtaDescription)));
end
if logical(opts.Force) || ~isfile(paths.category)
    mh_coverage_write_ref_nii(ref, categoryImg, paths.category, 2, char(string(opts.CategoryDescription)));
end
if logical(opts.Force) || ~isfile(paths.overlap)
    mh_coverage_write_ref_nii(ref, double(overlapMask), paths.overlap, 2, char(string(opts.OverlapDescription)));
end
end
