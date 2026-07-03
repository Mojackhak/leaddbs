function mh_coverage_require_output_files(outputDir, requiredFiles, varargin)
% Require a list of coverage output files relative to one output directory.

parser = inputParser;
parser.FunctionName = 'mh_coverage_require_output_files';
parser.addParameter('DescriptionPrefix', '', @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

outputDir = char(string(outputDir));
requiredFiles = cellstr(string(requiredFiles));
descriptionPrefix = char(string(opts.DescriptionPrefix));

for i = 1:numel(requiredFiles)
    description = [descriptionPrefix, requiredFiles{i}];
    mh_util_must_be_file(fullfile(outputDir, requiredFiles{i}), description);
end
end
