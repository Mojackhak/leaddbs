function [fiberHandle, renderedScores] = mh_viz_show_scored_fibers( ...
        fibers, fiberPointCounts, scores, colorLimit, fiberAlpha)
% Render Lead-DBS fibers with one symmetric-vik color per fiber score.

if nargin < 5 || isempty(fiberAlpha)
    fiberAlpha = 0.32;
end
if size(fibers, 1) < size(fibers, 2)
    fibers = fibers';
end
if ~isnumeric(fibers) || size(fibers, 2) < 3
    error('mh_viz_show_scored_fibers:BadFibers', ...
        'fibers must be a numeric point-by-three-or-more matrix.');
end

fiberPointCounts = double(fiberPointCounts(:));
scores = double(scores(:));
if isempty(fiberPointCounts) || numel(scores) ~= numel(fiberPointCounts)
    error('mh_viz_show_scored_fibers:BadScoreAxis', ...
        'scores must contain one value per fiber point-count entry.');
end
if any(~isfinite(fiberPointCounts)) || any(fiberPointCounts < 1) || ...
        any(mod(fiberPointCounts, 1) ~= 0) || ...
        sum(fiberPointCounts) ~= size(fibers, 1)
    error('mh_viz_show_scored_fibers:BadPointCounts', ...
        'fiberPointCounts must be positive integers summing to the point count.');
end
if ~isnumeric(colorLimit) || ~isscalar(colorLimit) || ...
        ~isfinite(colorLimit) || colorLimit <= 0
    error('mh_viz_show_scored_fibers:BadColorLimit', ...
        'colorLimit must be a positive finite symmetric-limit magnitude.');
end
if ~isnumeric(fiberAlpha) || ~isscalar(fiberAlpha) || ...
        ~isfinite(fiberAlpha) || fiberAlpha < 0 || fiberAlpha > 1
    error('mh_viz_show_scored_fibers:BadAlpha', ...
        'fiberAlpha must be within zero and one.');
end

fiberCells = mat2cell(fibers(:, 1:3), fiberPointCounts);
valid = isfinite(scores) & cellfun(@(points) size(points, 1) > 1, fiberCells);
fiberCells = fiberCells(valid);
scores = scores(valid);
if isempty(fiberCells)
    error('mh_viz_show_scored_fibers:NoFiniteFibers', ...
        'No nondegenerate fiber has a finite score.');
end

if exist('ea_getspace', 'file') == 2 && ...
        ismember(ea_getspace, {'Waxholm_Space_Atlas_SD_Rat_Brain'})
    sampleFactor = 1;
    tubeWidth = 0.02;
    reduceFactor = 0;
else
    sampleFactor = 5;
    if exist('ea_prefs', 'file') ~= 2
        error('mh_viz_show_scored_fibers:MissingLeadDBSPrefs', ...
            'ea_prefs was not found. Add Lead-DBS to the MATLAB path.');
    end
    preferences = ea_prefs;
    tubeWidth = preferences.d3.fiberwidth;
    reduceFactor = 0.1;
end

for i = 1:numel(fiberCells)
    pointCount = size(fiberCells{i}, 1);
    sampledCount = max(2, round(pointCount / sampleFactor));
    fiberCells{i} = fiberCells{i}( ...
        round(linspace(1, pointCount, sampledCount)), :);
end

maximumRenderedFibers = 1000;
if numel(fiberCells) > maximumRenderedFibers
    renderedIndices = unique(round(linspace( ...
        1, numel(fiberCells), maximumRenderedFibers)), 'stable');
    fiberCells = fiberCells(renderedIndices);
    scores = scores(renderedIndices);
end

surfaceHandles = streamtube(fiberCells, tubeWidth);
colorMap = ea_colormap_vik(256);
normalized = (max(-colorLimit, min(colorLimit, scores)) + colorLimit) ...
    / (2 * colorLimit);
colorIndices = 1 + round(normalized * (size(colorMap, 1) - 1));
fiberColors = colorMap(colorIndices, :);
for i = 1:numel(surfaceHandles)
    colorData = repmat(fiberColors(i, :), ...
        size(surfaceHandles(i).ZData, 1), 1);
    colorData = repmat(colorData, 1, 1, size(surfaceHandles(i).ZData, 2));
    colorData = permute(colorData, [1, 3, 2]);
    set(surfaceHandles(i), 'CData', colorData, 'CDataMapping', 'direct');
end

if exist('ea_concatfv', 'file') ~= 2
    delete(surfaceHandles);
    error('mh_viz_show_scored_fibers:MissingConcat', ...
        'ea_concatfv was not found. Add Lead-DBS to the MATLAB path.');
end
combined = ea_concatfv(surfaceHandles, 0, reduceFactor);
delete(surfaceHandles);
fiberHandle = patch( ...
    'Faces', combined.faces, ...
    'Vertices', combined.vertices, ...
    'FaceVertexCData', combined.facevertexcdata, ...
    'EdgeColor', 'none', ...
    'FaceAlpha', fiberAlpha, ...
    'CDataMapping', 'direct', ...
    'FaceColor', 'flat');
renderedScores = scores;
setappdata(fiberHandle, 'mh_viz_fiber_scores', scores);
setappdata(fiberHandle, 'mh_viz_fiber_color_limit', colorLimit);
setappdata(fiberHandle, 'mh_viz_fiber_colormap', 'vik');
end
