function [handle, metadata] = mh_viz_show_coefficient_fibers( ...
        hAx, fibers, fiberPointCounts, scores, fiberIds, colorLimit, varargin)
% Render every candidate fiber as a coefficient-colored continuous path.

parser = inputParser;
parser.FunctionName = mfilename;
addRequired(parser, 'hAx', @(value) isgraphics(value, 'axes'));
addRequired(parser, 'fibers', @isnumeric);
addRequired(parser, 'fiberPointCounts', @isnumeric);
addRequired(parser, 'scores', @isnumeric);
addRequired(parser, 'fiberIds', @isnumeric);
addRequired(parser, 'colorLimit', @local_is_positive_scalar);
addParameter(parser, 'Alpha', 1.0, @local_is_unit_scalar);
addParameter(parser, 'LineWidth', 0.25, @local_is_positive_scalar);
parse(parser, hAx, fibers, fiberPointCounts, scores, fiberIds, ...
    colorLimit, varargin{:});

if size(fibers, 1) < size(fibers, 2)
    fibers = fibers';
end
if size(fibers, 2) < 3
    error('mh_viz_show_coefficient_fibers:BadFibers', ...
        'fibers must be a numeric point-by-three-or-more matrix.');
end
fibers = double(fibers(:, 1:3));
fiberPointCounts = double(fiberPointCounts(:));
scores = double(scores(:));
fiberIds = double(fiberIds(:));
fiberCount = numel(fiberPointCounts);
if fiberCount == 0 || numel(scores) ~= fiberCount || ...
        numel(fiberIds) ~= fiberCount
    error('mh_viz_show_coefficient_fibers:BadFiberAxis', ...
        'idx, scores, and fiberIds must be matching nonempty vectors.');
end
if any(~isfinite(fiberPointCounts)) || any(fiberPointCounts < 2) || ...
        any(mod(fiberPointCounts, 1) ~= 0) || ...
        sum(fiberPointCounts) ~= size(fibers, 1)
    error('mh_viz_show_coefficient_fibers:BadPointCounts', ...
        'idx must contain integers of at least two that span all points.');
end
if any(~isfinite(fibers), 'all')
    error('mh_viz_show_coefficient_fibers:NonfiniteGeometry', ...
        'Candidate fiber geometry must be finite.');
end
if any(~isfinite(scores)) || ~any(scores ~= 0)
    error('mh_viz_show_coefficient_fibers:BadScores', ...
        'scores must be finite, aligned, and not uniformly zero.');
end
if any(~isfinite(fiberIds)) || any(mod(fiberIds, 1) ~= 0) || ...
        any(fiberIds < 1) || numel(unique(fiberIds)) ~= fiberCount
    error('mh_viz_show_coefficient_fibers:BadFiberIds', ...
        'fiberIds must contain unique positive integers.');
end

colorMap = ea_colormap_vik(256);
normalized = (max(-colorLimit, min(colorLimit, scores)) + colorLimit) ...
    / (2 * colorLimit);
colorIndices = 1 + round(normalized * (size(colorMap, 1) - 1));
fiberColors = colorMap(colorIndices, :);

pointCount = size(fibers, 1);
segmentCount = pointCount - fiberCount;
faces = zeros(segmentCount, 2);
vertexColors = zeros(pointCount, 3);
pointCursor = 0;
segmentCursor = 0;
for index = 1:fiberCount
    count = fiberPointCounts(index);
    pointRows = pointCursor + (1:count);
    vertexColors(pointRows, :) = repmat(fiberColors(index, :), count, 1);
    segmentRows = segmentCursor + (1:(count - 1));
    firstVertices = pointCursor + (1:(count - 1));
    faces(segmentRows, :) = [firstVertices(:), firstVertices(:) + 1];
    pointCursor = pointCursor + count;
    segmentCursor = segmentCursor + count - 1;
end

handle = patch(hAx, ...
    'Faces', faces, ...
    'Vertices', fibers, ...
    'FaceVertexCData', vertexColors, ...
    'FaceColor', 'none', ...
    'EdgeColor', 'flat', ...
    'EdgeAlpha', parser.Results.Alpha, ...
    'LineWidth', parser.Results.LineWidth, ...
    'CDataMapping', 'direct', ...
    'FaceLighting', 'none', ...
    'EdgeLighting', 'none', ...
    'Tag', 'mh_viz_fiber_coefficient', ...
    'DisplayName', 'Coefficient-colored fibers');

metadata = struct();
metadata.candidate_fiber_count = fiberCount;
metadata.rendered_fiber_count = fiberCount;
metadata.fiber_ids = fiberIds;
metadata.scores = scores;
metadata.score_min = min(scores);
metadata.score_max = max(scores);
metadata.score_color_limit = double(colorLimit);
metadata.alpha = parser.Results.Alpha;
metadata.line_width = parser.Results.LineWidth;
metadata.colormap = 'vik';
setappdata(handle, 'mh_viz_fiber_scores', scores);
setappdata(handle, 'mh_viz_fiber_ids', fiberIds);
setappdata(handle, 'mh_viz_fiber_color_limit', double(colorLimit));
setappdata(handle, 'mh_viz_fiber_colormap', 'vik');
end

function valid = local_is_unit_scalar(value)
valid = isnumeric(value) && isscalar(value) && isfinite(value) && ...
    value >= 0 && value <= 1;
end

function valid = local_is_positive_scalar(value)
valid = isnumeric(value) && isscalar(value) && isfinite(value) && value > 0;
end
