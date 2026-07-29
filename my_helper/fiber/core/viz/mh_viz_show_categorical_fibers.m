function [handles, metadata] = mh_viz_show_categorical_fibers( ...
        hAx, fibers, fiberPointCounts, fiberRoles, fiberIds, varargin)
% Render every candidate fiber with categorical candidate/sweet/sour styling.

parser = inputParser;
parser.FunctionName = mfilename;
addRequired(parser, 'hAx', @(value) isgraphics(value, 'axes'));
addRequired(parser, 'fibers', @isnumeric);
addRequired(parser, 'fiberPointCounts', @isnumeric);
addRequired(parser, 'fiberRoles', @isnumeric);
addRequired(parser, 'fiberIds', @isnumeric);
addParameter(parser, 'CandidateColor', [204, 204, 204] / 255, ...
    @local_is_color);
addParameter(parser, 'CandidateAlpha', 1.0, @local_is_unit_scalar);
addParameter(parser, 'CandidateLineWidth', 0.25, @local_is_positive_scalar);
addParameter(parser, 'SweetColor', [242, 0, 14] / 255, @local_is_color);
addParameter(parser, 'SourColor', [14, 106, 175] / 255, @local_is_color);
addParameter(parser, 'SelectedAlpha', 1.0, @local_is_unit_scalar);
addParameter(parser, 'SelectedRenderMode', 'line', @local_is_render_mode);
addParameter(parser, 'SelectedLineWidth', 0.50, @local_is_positive_scalar);
addParameter(parser, 'SelectedTubeWidth', 0.20, @local_is_positive_scalar);
addParameter(parser, 'SelectedSampleFactor', 5, @local_is_positive_integer);
addParameter(parser, 'SelectedReduceFactor', 0.10, @local_is_unit_scalar);
parse(parser, hAx, fibers, fiberPointCounts, fiberRoles, fiberIds, varargin{:});

if size(fibers, 1) < size(fibers, 2)
    fibers = fibers';
end
if size(fibers, 2) < 3
    error('mh_viz_show_categorical_fibers:BadFibers', ...
        'fibers must be a numeric point-by-three-or-more matrix.');
end
fibers = double(fibers(:, 1:3));
fiberPointCounts = double(fiberPointCounts(:));
fiberRoles = double(fiberRoles(:));
fiberIds = double(fiberIds(:));
fiberCount = numel(fiberPointCounts);
if fiberCount == 0 || numel(fiberRoles) ~= fiberCount || ...
        numel(fiberIds) ~= fiberCount
    error('mh_viz_show_categorical_fibers:BadFiberAxis', ...
        'idx, fiberRoles, and fiberIds must be matching nonempty vectors.');
end
if any(~isfinite(fiberPointCounts)) || any(fiberPointCounts < 2) || ...
        any(mod(fiberPointCounts, 1) ~= 0) || ...
        sum(fiberPointCounts) ~= size(fibers, 1)
    error('mh_viz_show_categorical_fibers:BadPointCounts', ...
        'idx must contain integers of at least two that span all points.');
end
if any(~ismember(fiberRoles, [-1, 0, 1]))
    error('mh_viz_show_categorical_fibers:BadFiberRoles', ...
        'fiberRoles must contain only minus one, zero, or one.');
end
if any(~isfinite(fiberIds)) || any(mod(fiberIds, 1) ~= 0) || ...
        any(fiberIds < 1) || numel(unique(fiberIds)) ~= fiberCount
    error('mh_viz_show_categorical_fibers:BadFiberIds', ...
        'fiberIds must contain unique positive integers.');
end
if any(~isfinite(fibers), 'all')
    error('mh_viz_show_categorical_fibers:NonfiniteGeometry', ...
        'Candidate fiber geometry must be finite.');
end

fiberCells = mat2cell(fibers, fiberPointCounts);
candidateMask = fiberRoles == 0;
sweetMask = fiberRoles == 1;
sourMask = fiberRoles == -1;

handles = struct();
handles.candidate = local_path_patch( ...
    hAx, fiberCells(candidateMask), parser.Results.CandidateColor, ...
    parser.Results.CandidateAlpha, parser.Results.CandidateLineWidth, ...
    'mh_viz_fiber_candidate', 'Candidate fibers');
handles.sweet = local_selected_patch( ...
    hAx, fiberCells(sweetMask), parser.Results.SweetColor, ...
    parser.Results.SelectedAlpha, parser.Results.SelectedRenderMode, ...
    parser.Results.SelectedLineWidth, parser.Results.SelectedTubeWidth, ...
    parser.Results.SelectedSampleFactor, parser.Results.SelectedReduceFactor, ...
    'mh_viz_fiber_sweet', 'Sweet fibers');
handles.sour = local_selected_patch( ...
    hAx, fiberCells(sourMask), parser.Results.SourColor, ...
    parser.Results.SelectedAlpha, parser.Results.SelectedRenderMode, ...
    parser.Results.SelectedLineWidth, parser.Results.SelectedTubeWidth, ...
    parser.Results.SelectedSampleFactor, parser.Results.SelectedReduceFactor, ...
    'mh_viz_fiber_sour', 'Sour fibers');

metadata = struct();
metadata.candidate_fiber_count = fiberCount;
metadata.unselected_candidate_fiber_count = nnz(candidateMask);
metadata.sweet_fiber_count = nnz(sweetMask);
metadata.sour_fiber_count = nnz(sourMask);
metadata.rendered_fiber_count = ...
    metadata.unselected_candidate_fiber_count + ...
    metadata.sweet_fiber_count + metadata.sour_fiber_count;
metadata.fiber_ids = fiberIds;
metadata.fiber_roles = fiberRoles;
metadata.candidate_color = parser.Results.CandidateColor;
metadata.candidate_alpha = parser.Results.CandidateAlpha;
metadata.sweet_color = parser.Results.SweetColor;
metadata.sour_color = parser.Results.SourColor;
metadata.selected_alpha = parser.Results.SelectedAlpha;
metadata.selected_render_mode = lower(char(string( ...
    parser.Results.SelectedRenderMode)));
metadata.selected_line_width = parser.Results.SelectedLineWidth;
if metadata.rendered_fiber_count ~= fiberCount
    error('mh_viz_show_categorical_fibers:IncompleteRender', ...
        'Every candidate fiber must be represented by one categorical layer.');
end
end

function handle = local_selected_patch( ...
        hAx, fiberCells, color, alphaValue, renderMode, lineWidth, ...
        tubeWidth, sampleFactor, reduceFactor, tag, displayName)
if strcmpi(char(string(renderMode)), 'line')
    handle = local_path_patch( ...
        hAx, fiberCells, color, alphaValue, lineWidth, tag, displayName);
else
    handle = local_tube_patch( ...
        hAx, fiberCells, color, alphaValue, tubeWidth, sampleFactor, ...
        reduceFactor, tag, displayName);
end
end

function handle = local_path_patch( ...
        hAx, fiberCells, color, alphaValue, lineWidth, tag, displayName)
handle = gobjects(0, 1);
if isempty(fiberCells)
    return;
end
pointCount = sum(cellfun(@(points) size(points, 1), fiberCells));
segmentCount = sum(cellfun(@(points) size(points, 1) - 1, fiberCells));
vertices = zeros(pointCount, 3);
faces = zeros(segmentCount, 2);
pointCursor = 0;
segmentCursor = 0;
for index = 1:numel(fiberCells)
    points = fiberCells{index};
    count = size(points, 1);
    vertices(pointCursor + (1:count), :) = points;
    segmentRows = segmentCursor + (1:(count - 1));
    firstVertices = pointCursor + (1:(count - 1));
    faces(segmentRows, :) = [firstVertices(:), firstVertices(:) + 1];
    pointCursor = pointCursor + count;
    segmentCursor = segmentCursor + count - 1;
end
handle = patch(hAx, ...
    'Faces', faces, ...
    'Vertices', vertices, ...
    'FaceColor', 'none', ...
    'EdgeColor', color, ...
    'EdgeAlpha', alphaValue, ...
    'LineWidth', lineWidth, ...
    'FaceLighting', 'none', ...
    'EdgeLighting', 'none', ...
    'Tag', tag, ...
    'DisplayName', displayName);
end

function handle = local_tube_patch( ...
        hAx, fiberCells, color, alphaValue, tubeWidth, sampleFactor, ...
        reduceFactor, tag, displayName)
handle = gobjects(0, 1);
if isempty(fiberCells)
    return;
end
for index = 1:numel(fiberCells)
    pointCount = size(fiberCells{index}, 1);
    sampledCount = max(2, round(pointCount / sampleFactor));
    sampleIndices = unique(round(linspace(1, pointCount, sampledCount)), 'stable');
    if numel(sampleIndices) < 2
        sampleIndices = [1, pointCount];
    end
    fiberCells{index} = fiberCells{index}(sampleIndices, :);
end

hFig = ancestor(hAx, 'figure');
set(groot, 'CurrentFigure', hFig);
set(hFig, 'CurrentAxes', hAx);
surfaceHandles = streamtube(fiberCells, tubeWidth);
surfaceCleanup = onCleanup(@() local_delete_graphics(surfaceHandles));
for index = 1:numel(surfaceHandles)
    colorData = repmat(color, size(surfaceHandles(index).ZData, 1), 1);
    colorData = repmat( ...
        colorData, 1, 1, size(surfaceHandles(index).ZData, 2));
    colorData = permute(colorData, [1, 3, 2]);
    set(surfaceHandles(index), ...
        'CData', colorData, ...
        'CDataMapping', 'direct', ...
        'FaceColor', 'flat', ...
        'FaceAlpha', alphaValue, ...
        'EdgeColor', 'none');
end
if exist('ea_concatfv', 'file') ~= 2
    error('mh_viz_show_categorical_fibers:MissingConcat', ...
        'ea_concatfv was not found. Add Lead-DBS to the MATLAB path.');
end
combined = ea_concatfv(surfaceHandles, 0, reduceFactor);
local_delete_graphics(surfaceHandles);
clear surfaceCleanup;
handle = patch(hAx, ...
    'Faces', combined.faces, ...
    'Vertices', combined.vertices, ...
    'FaceVertexCData', combined.facevertexcdata, ...
    'EdgeColor', 'none', ...
    'FaceAlpha', alphaValue, ...
    'CDataMapping', 'direct', ...
    'FaceColor', 'flat', ...
    'FaceLighting', 'gouraud', ...
    'Tag', tag, ...
    'DisplayName', displayName);
end

function local_delete_graphics(handles)
handles = handles(isgraphics(handles));
if ~isempty(handles)
    delete(handles);
end
end

function valid = local_is_color(value)
valid = isnumeric(value) && numel(value) == 3 && ...
    all(isfinite(value), 'all') && all(value >= 0, 'all') && ...
    all(value <= 1, 'all');
end

function valid = local_is_unit_scalar(value)
valid = isnumeric(value) && isscalar(value) && isfinite(value) && ...
    value >= 0 && value <= 1;
end

function valid = local_is_positive_scalar(value)
valid = isnumeric(value) && isscalar(value) && isfinite(value) && value > 0;
end

function valid = local_is_positive_integer(value)
valid = local_is_positive_scalar(value) && mod(value, 1) == 0;
end

function valid = local_is_render_mode(value)
valid = (ischar(value) || (isstring(value) && isscalar(value))) && ...
    ismember(lower(strtrim(char(string(value)))), {'line', 'tube'});
end
