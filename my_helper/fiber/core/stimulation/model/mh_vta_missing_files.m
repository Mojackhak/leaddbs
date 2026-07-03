function missing = mh_vta_missing_files(vta, varargin)
% Return required VTA/e-field files that are absent.

parser = inputParser;
parser.FunctionName = 'mh_vta_missing_files';
parser.addParameter('Sides', {'R', 'L'}, @(x) isnumeric(x) || iscell(x) || ischar(x) || isstring(x));
parser.addParameter('Spaces', {'native', 'mni'}, @(x) iscell(x) || ischar(x) || isstring(x));
parser.addParameter('Kinds', {'binaryMat', 'binaryNii', 'efieldNii'}, ...
    @(x) iscell(x) || ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

sideRequest = struct('sides', opts.Sides);
sides = mh_vta_normalize_sides(sideRequest);
spaces = cellstr(string(opts.Spaces));
kinds = cellstr(string(opts.Kinds));

required = {};
for sp = 1:numel(spaces)
    space = spaces{sp};
    for s = 1:numel(sides)
        side = sides{s};
        for k = 1:numel(kinds)
            kind = kinds{k};
            if isfield(vta, space) && isfield(vta.(space), side) && ...
                    isfield(vta.(space).(side), kind)
                required{end+1} = vta.(space).(side).(kind); %#ok<AGROW>
            end
        end
    end
end

missing = required(~cellfun(@isfile, required));
end
