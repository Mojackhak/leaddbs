function mh_viz_export_individualized_target_fiber_pdfs( ...
        geometryMatPath, taskJsonPath)
% Export one worker's individualized target-derived fiber PDFs headlessly.

geometryMatPath = char(string(geometryMatPath));
taskJsonPath = char(string(taskJsonPath));
if ~isfile(geometryMatPath)
    error([mfilename, ':MissingGeometry'], ...
        'Geometry MAT does not exist: %s', geometryMatPath);
end
if ~isfile(taskJsonPath)
    error([mfilename, ':MissingTasks'], ...
        'Task JSON does not exist: %s', taskJsonPath);
end
data = load(geometryMatPath, ...
    'fibers', 'idx', 'fiber_ids', 'score_matrix');
required = {'fibers', 'idx', 'fiber_ids', 'score_matrix'};
for index = 1:numel(required)
    if ~isfield(data, required{index})
        error([mfilename, ':BadGeometry'], ...
            'Geometry MAT lacks %s.', required{index});
    end
end
tasks = jsondecode(fileread(taskJsonPath));
if isempty(tasks) || ~isstruct(tasks)
    error([mfilename, ':BadTasks'], ...
        'Task JSON must contain a nonempty object array.');
end
tasks = tasks(:);
oldDefaultFigureVisible = get(groot, 'DefaultFigureVisible');
set(groot, 'DefaultFigureVisible', 'off');
visibilityCleanup = onCleanup(@() set( ...
    groot, 'DefaultFigureVisible', oldDefaultFigureVisible));

for taskIndex = 1:numel(tasks)
    task = tasks(taskIndex);
    role = validatestring(lower(strtrim(char(string(task.model_role)))), ...
        {'reference', 'addon'}, mfilename, 'model_role');
    scoreColumn = double(task.score_column);
    if ~isscalar(scoreColumn) || ~isfinite(scoreColumn) || ...
            scoreColumn < 1 || mod(scoreColumn, 1) ~= 0 || ...
            scoreColumn > size(data.score_matrix, 2)
        error([mfilename, ':BadScoreColumn'], ...
            'score_column is outside score_matrix.');
    end
    scores = double(data.score_matrix(:, scoreColumn));
    selected = isfinite(scores);
    if ~any(selected)
        error([mfilename, ':NoScoredFibers'], ...
            'The task has no finite target-derived fiber scores.');
    end
    coefficientData = local_select_geometry(data, selected, scores);
    colorLimit = double(task.color_limit);
    if ~isscalar(colorLimit) || ~isfinite(colorLimit) || colorLimit <= 0
        error([mfilename, ':BadColorLimit'], ...
            'color_limit must be positive and finite.');
    end

    outputDirectory = char(string(task.output_directory));
    if ~isfolder(outputDirectory)
        mkdir(outputDirectory);
    end
    filePrefix = [char(string(task.scale_id)), '_fiber_coefficient'];
    views = mh_viz_default_fiber_views();
    roleViews = views.(role);
    allExist = true;
    for viewIndex = 1:numel(roleViews)
        outputPath = fullfile(outputDirectory, sprintf( ...
            '%s_%s_view%02d.pdf', filePrefix, role, viewIndex));
        allExist = allExist && isfile(outputPath);
    end
    if allExist
        continue;
    end

    fiberStyle = mh_viz_default_fiber_scene_spec();
    spec = struct();
    spec.FiberCoefficientData = coefficientData;
    spec.FiberColorLimit = colorLimit;
    spec.FiberColorbarLabel = char(string(task.colorbar_label));
    spec.AtlasName = 'Custom_STNSNr';
    spec.ShowAtlasWireframe = true;
    if strcmp(role, 'reference')
        spec.AtlasRoiIndices = 2;
    else
        spec.AtlasRoiIndices = 1;
    end
    spec.AtlasEdgeAlpha = 0.15;
    spec.CoefficientFiberAlpha = fiberStyle.CoefficientFiberAlpha;
    spec.CoefficientFiberLineWidth = fiberStyle.CoefficientFiberLineWidth;
    spec.FiberColorbarTextColor = fiberStyle.FiberColorbarTextColor;
    spec.ShowFiberLegend = false;
    spec.BackgroundColor = fiberStyle.BackgroundColor;
    spec.AddRASTriad = fiberStyle.AddRASTriad;
    spec.ShowAnatomySlices = fiberStyle.ShowAnatomySlices;
    spec.AnatomyNifti = fiberStyle.AnatomyNifti;
    spec.AnatomySlicePlane = fiberStyle.AnatomySlicePlane;
    spec.AnatomySliceCoordinateMm = fiberStyle.AnatomySliceCoordinateMm;
    spec.AnatomySliceTransparencyPercent = ...
        fiberStyle.AnatomySliceTransparencyPercent;
    spec.AddToolbarToggles = false;
    spec.ViewStruct = roleViews{1};
    spec.FigureVisible = 'off';
    spec.FigureBackend = 'matlab';
    spec.StrictHeadless = true;
    spec.CloseAfterExport = false;

    figuresBefore = findall(groot, 'Type', 'figure');
    scene = mh_viz_make_sweet_sour_scene(spec);
    newFigures = setdiff(findall(groot, 'Type', 'figure'), figuresBefore);
    figureCleanup = onCleanup(@() local_delete_figures(newFigures));
    local_assert_hidden(newFigures);
    mh_viz_export_scene_views( ...
        scene, outputDirectory, role, ...
        'Views', views, ...
        'FilePrefix', filePrefix, ...
        'BackgroundColor', fiberStyle.BackgroundColor, ...
        'Resolution', 600, ...
        'IncludeAnatomySlices', true, ...
        'RequireRASLabels', false);
    local_assert_hidden(newFigures);
    local_delete_figures(newFigures);
    clear figureCleanup;
end
end

function selected = local_select_geometry(data, selectedFiberMask, scores)
pointCounts = double(data.idx(:));
fiberIds = double(data.fiber_ids(:));
if numel(pointCounts) ~= numel(fiberIds) || ...
        numel(scores) ~= numel(fiberIds) || ...
        sum(pointCounts) ~= size(data.fibers, 1)
    error('mh_viz_export_individualized_target_fiber_pdfs:BadAxes', ...
        'Geometry, fiber IDs, and score matrix are not aligned.');
end
selectedCounts = pointCounts(selectedFiberMask);
selectedPoints = zeros(sum(selectedCounts), 3, 'like', data.fibers);
sourceOffsets = [0; cumsum(pointCounts)];
destinationCursor = 0;
selectedIndices = find(selectedFiberMask);
for index = 1:numel(selectedIndices)
    fiberIndex = selectedIndices(index);
    sourceRows = (sourceOffsets(fiberIndex) + 1): ...
        sourceOffsets(fiberIndex + 1);
    destinationRows = destinationCursor + (1:pointCounts(fiberIndex));
    selectedPoints(destinationRows, :) = data.fibers(sourceRows, 1:3);
    destinationCursor = destinationCursor + pointCounts(fiberIndex);
end
selected = struct();
selected.fibers = selectedPoints;
selected.idx = selectedCounts;
selected.scores = scores(selectedFiberMask);
selected.fiber_ids = fiberIds(selectedFiberMask);
end

function local_assert_hidden(figures)
figures = figures(isgraphics(figures, 'figure'));
if isempty(figures)
    error('mh_viz_export_individualized_target_fiber_pdfs:MissingFigure', ...
        'Scene construction did not create a figure.');
end
for index = 1:numel(figures)
    if strcmpi(get(figures(index), 'Visible'), 'on')
        error('mh_viz_export_individualized_target_fiber_pdfs:VisibleFigure', ...
            'Strict-headless export created a visible figure.');
    end
end
end

function local_delete_figures(figures)
figures = figures(isgraphics(figures, 'figure'));
if ~isempty(figures)
    delete(figures);
end
end
