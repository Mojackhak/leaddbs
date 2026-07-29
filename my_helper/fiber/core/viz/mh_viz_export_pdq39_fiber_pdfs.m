function exports = mh_viz_export_pdq39_fiber_pdfs(outputDirectory, varargin)
% Export categorical PDQ-39 fiber PDFs without visible figures.

parser = inputParser;
parser.FunctionName = mfilename;
addRequired(parser, 'outputDirectory', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'PublicationRoot', ...
    ['/Volumes/VAL/STNSNr/summary/spot/normative_fiber/', ...
    'dual_frequency_four_model_v1'], ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
addParameter(parser, 'ScaleId', 'pdq39_score', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
addParameter(parser, 'Views', mh_viz_default_fiber_views(), ...
    @(value) isstruct(value) && isscalar(value));
addParameter(parser, 'FilePrefix', 'pdq39_fiber', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
addParameter(parser, 'Resolution', 600, ...
    @(value) isnumeric(value) && isscalar(value) && ...
    isfinite(value) && value > 0);
parse(parser, outputDirectory, varargin{:});

outputDirectory = char(string(parser.Results.outputDirectory));
if isempty(strtrim(outputDirectory))
    error('mh_viz_export_pdq39_fiber_pdfs:MissingOutputDirectory', ...
        'outputDirectory must be nonempty.');
end
if isfolder(outputDirectory) || isfile(outputDirectory)
    error('mh_viz_export_pdq39_fiber_pdfs:OutputExists', ...
        'Refusing to replace an existing output path: %s', outputDirectory);
end
[outputParent, ~, ~] = fileparts(outputDirectory);
if isempty(outputParent)
    outputParent = pwd;
end
if ~isfolder(outputParent)
    mkdir(outputParent);
end
stageDirectory = tempname(outputParent);
mkdir(stageDirectory);

publicationRoot = char(string(parser.Results.PublicationRoot));
scaleId = char(string(parser.Results.ScaleId));
views = parser.Results.Views;
filePrefix = char(string(parser.Results.FilePrefix));
resolution = double(parser.Results.Resolution);
roles = {'reference', 'addon'};
modelFamilies = {'reference_fiber', 'addon_fiber'};
atlasRoiIndices = [2, 1];
fiberStyle = mh_viz_default_fiber_scene_spec();
expectedExportCount = local_expected_export_count(views, roles);
exports = repmat(struct('model_role', '', 'view_index', 0, ...
    'view', struct(), 'pdf_path', ''), 0, 1);
roleRecords = repmat(struct( ...
    'role', '', ...
    'model_family', '', ...
    'input_path', '', ...
    'input_request_hash', '', ...
    'selected_tau_v_per_m', [], ...
    'selected_coverage_subjects_min', [], ...
    'candidate_fiber_count', 0, ...
    'unselected_candidate_fiber_count', 0, ...
    'sweet_fiber_count', 0, ...
    'sour_fiber_count', 0, ...
    'rendered_fiber_count', 0), numel(roles), 1);

for roleIndex = 1:numel(roles)
    role = roles{roleIndex};
    prepared = mh_viz_prepare_scene_example_input( ...
        publicationRoot, modelFamilies{roleIndex}, 'ScaleId', scaleId);

    spec = struct();
    spec.FiberCategoricalMat = prepared.input_path;
    spec.AtlasName = 'Custom_STNSNr';
    spec.ShowAtlasWireframe = true;
    spec.AtlasRoiIndices = atlasRoiIndices(roleIndex);
    spec.AtlasEdgeAlpha = 0.15;
    spec.CandidateFiberColor = fiberStyle.CandidateFiberColor;
    spec.CandidateFiberAlpha = fiberStyle.CandidateFiberAlpha;
    spec.CandidateFiberLineWidth = fiberStyle.CandidateFiberLineWidth;
    spec.SweetFiberColor = fiberStyle.SweetFiberColor;
    spec.SourFiberColor = fiberStyle.SourFiberColor;
    spec.SelectedFiberAlpha = fiberStyle.SelectedFiberAlpha;
    spec.SelectedFiberRenderMode = fiberStyle.SelectedFiberRenderMode;
    spec.SelectedFiberLineWidth = fiberStyle.SelectedFiberLineWidth;
    spec.SelectedFiberTubeWidth = 0.20;
    spec.SelectedFiberSampleFactor = 5;
    spec.SelectedFiberReduceFactor = 0.10;
    spec.ShowFiberLegend = true;
    spec.FiberLegendTextColor = fiberStyle.FiberLegendTextColor;
    spec.BackgroundColor = fiberStyle.BackgroundColor;
    spec.AddRASTriad = fiberStyle.AddRASTriad;
    spec.ShowAnatomySlices = fiberStyle.ShowAnatomySlices;
    spec.AnatomyNifti = fiberStyle.AnatomyNifti;
    spec.AnatomySlicePlane = fiberStyle.AnatomySlicePlane;
    spec.AnatomySliceCoordinateMm = fiberStyle.AnatomySliceCoordinateMm;
    spec.AnatomySliceTransparencyPercent = ...
        fiberStyle.AnatomySliceTransparencyPercent;
    spec.AddToolbarToggles = false;
    spec.ViewStruct = views.(role){1};
    spec.FigureVisible = 'off';
    spec.FigureBackend = 'matlab';
    spec.StrictHeadless = true;
    spec.OutputFig = '';
    spec.OutputImage = '';
    spec.OutputPdf = '';
    spec.OutputSpin = '';
    spec.CloseAfterExport = false;

    figuresBefore = findall(groot, 'Type', 'figure');
    scene = mh_viz_make_sweet_sour_scene(spec);
    newFigures = setdiff(findall(groot, 'Type', 'figure'), figuresBefore);
    figureCleanup = onCleanup(@() local_delete_figures(newFigures));
    local_assert_hidden(newFigures);
    local_assert_counts(scene, prepared, role);
    local_assert_render_style(scene, fiberStyle, role);
    local_assert_layer_order(scene, role);
    local_assert_anatomy(scene, fiberStyle, role);
    local_assert_legend(scene, fiberStyle, role);
    local_assert_no_ras(scene, role);

    roleExports = mh_viz_export_scene_views( ...
        scene, stageDirectory, role, ...
        'Views', views, ...
        'FilePrefix', filePrefix, ...
        'BackgroundColor', fiberStyle.BackgroundColor, ...
        'Resolution', resolution, ...
        'IncludeAnatomySlices', true, ...
        'RequireRASLabels', false);
    exports = [exports; roleExports(:)]; %#ok<AGROW>

    metadata = scene.objects.fiberCategoricalMetadata;
    roleRecords(roleIndex).role = role;
    roleRecords(roleIndex).model_family = modelFamilies{roleIndex};
    roleRecords(roleIndex).input_path = prepared.input_path;
    roleRecords(roleIndex).input_request_hash = prepared.request_hash;
    roleRecords(roleIndex).selected_tau_v_per_m = prepared.selected_tau;
    roleRecords(roleIndex).selected_coverage_subjects_min = ...
        prepared.selected_coverage;
    roleRecords(roleIndex).candidate_fiber_count = ...
        metadata.candidate_fiber_count;
    roleRecords(roleIndex).unselected_candidate_fiber_count = ...
        metadata.unselected_candidate_fiber_count;
    roleRecords(roleIndex).sweet_fiber_count = metadata.sweet_fiber_count;
    roleRecords(roleIndex).sour_fiber_count = metadata.sour_fiber_count;
    roleRecords(roleIndex).rendered_fiber_count = ...
        metadata.rendered_fiber_count;

    local_delete_figures(newFigures);
    clear figureCleanup;
end

if numel(exports) ~= expectedExportCount
    error('mh_viz_export_pdq39_fiber_pdfs:IncompleteExport', ...
        ['Strict-headless export produced %d PDFs, but the configured ', ...
        'role views require %d.'], numel(exports), expectedExportCount);
end

outputRecords = repmat(struct( ...
    'model_role', '', 'view_index', 0, 'relative_path', '', ...
    'sha256', '', 'size_bytes', 0, 'view', struct()), numel(exports), 1);
for index = 1:numel(exports)
    [~, name, extension] = fileparts(exports(index).pdf_path);
    relativePath = [name, extension];
    outputRecords(index).model_role = exports(index).model_role;
    outputRecords(index).view_index = exports(index).view_index;
    outputRecords(index).relative_path = relativePath;
    outputRecords(index).sha256 = local_file_sha256(exports(index).pdf_path);
    info = dir(exports(index).pdf_path);
    outputRecords(index).size_bytes = info.bytes;
    outputRecords(index).view = exports(index).view;
end

manifest = struct();
manifest.schema_version = 'pdq39_categorical_fiber_3d_export_v7';
manifest.status = 'complete';
manifest.scale_id = scaleId;
manifest.publication_root = publicationRoot;
manifest.created_at_utc = char(datetime( ...
    'now', 'TimeZone', 'UTC', 'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
manifest.strict_headless = true;
manifest.figure_visible = 'off';
manifest.figure_backend = 'matlab';
manifest.style = struct( ...
    'candidate_color', '#CCCCCC', ...
    'candidate_alpha_hex', 'FF', ...
    'candidate_alpha', fiberStyle.CandidateFiberAlpha, ...
    'sweet_color', '#F2000E', ...
    'sour_color', '#0E6AAF', ...
    'selected_alpha', 1.0, ...
    'selected_render_mode', fiberStyle.SelectedFiberRenderMode, ...
    'candidate_line_width_points', fiberStyle.CandidateFiberLineWidth, ...
    'selected_line_width_points', fiberStyle.SelectedFiberLineWidth, ...
    'scene_alignment', 'single_native_3d_axes', ...
    'axes_sort_method', 'childorder', ...
    'fiber_layer_order', 'candidate_back_sweet_sour_front', ...
    'fiber_pdf_layer', 'same_axes_raster', ...
    'anatomy_atlas_pdf_layer', 'same_axes_raster', ...
    'anatomy_atlas_raster_dpi', resolution, ...
    'legend_pdf_layer', 'vector', ...
    'legend_symbol', 'horizontal_line', ...
    'legend_text_color', '#FFFFFF', ...
    'background_color', '#000000', ...
    'ras_triad_default_enabled', false, ...
    'atlas_edge_alpha', 0.15, ...
    'font_name', 'Arial');
manifest.anatomy = struct( ...
    'source', fiberStyle.AnatomyNifti, ...
    'plane', fiberStyle.AnatomySlicePlane, ...
    'coordinate_mm', fiberStyle.AnatomySliceCoordinateMm, ...
    'transparency_percent', ...
        fiberStyle.AnatomySliceTransparencyPercent, ...
    'face_alpha', fiberStyle.AnatomySliceTransparencyPercent / 100, ...
    'included_in_export', true);
manifest.default_view_count_per_role = 1;
manifest.configured_output_count = expectedExportCount;
manifest.roles = roleRecords;
manifest.outputs = outputRecords;
local_write_json(fullfile(stageDirectory, 'export_manifest.json'), manifest);

[published, message] = movefile(stageDirectory, outputDirectory);
if ~published
    error('mh_viz_export_pdq39_fiber_pdfs:PublishFailed', ...
        'Could not publish the staged export: %s', message);
end
for index = 1:numel(exports)
    [~, name, extension] = fileparts(exports(index).pdf_path);
    exports(index).pdf_path = fullfile(outputDirectory, [name, extension]);
end
end

function expected = local_expected_export_count(views, roles)
expected = 0;
for index = 1:numel(roles)
    role = roles{index};
    if ~isfield(views, role) || ~iscell(views.(role)) || ...
            isempty(views.(role))
        error('mh_viz_export_pdq39_fiber_pdfs:MissingRoleViews', ...
            'Views.%s must be a nonempty cell array.', role);
    end
    expected = expected + numel(views.(role));
end
end

function local_assert_counts(scene, prepared, role)
if ~isfield(scene.objects, 'fiberCategoricalMetadata')
    error('mh_viz_export_pdq39_fiber_pdfs:MissingMetadata', ...
        'The %s scene lacks categorical fiber metadata.', role);
end
metadata = scene.objects.fiberCategoricalMetadata;
expected = prepared.details;
fields = {'candidate_fiber_count', 'unselected_candidate_fiber_count', ...
    'sweet_fiber_count', 'sour_fiber_count'};
for index = 1:numel(fields)
    field = fields{index};
    if ~isfield(metadata, field) || ~isfield(expected, field) || ...
            double(metadata.(field)) ~= double(expected.(field))
        error('mh_viz_export_pdq39_fiber_pdfs:CountMismatch', ...
            'The %s %s differs between prepared input and render.', ...
            role, field);
    end
end
if metadata.rendered_fiber_count ~= metadata.candidate_fiber_count
    error('mh_viz_export_pdq39_fiber_pdfs:IncompleteCandidateRender', ...
        'The %s scene did not represent every candidate fiber.', role);
end
end

function local_assert_anatomy(scene, fiberStyle, role)
if ~isfield(scene.objects, 'anatomySlices')
    error('mh_viz_export_pdq39_fiber_pdfs:MissingAnatomySlice', ...
        'The %s scene lacks anatomy slice metadata.', role);
end
handles = scene.objects.anatomySlices;
handles = handles(isgraphics(handles, 'surface'));
if numel(handles) ~= 1
    error('mh_viz_export_pdq39_fiber_pdfs:BadAnatomySliceCount', ...
        'The %s scene must contain exactly one anatomy slice.', role);
end
handle = handles(1);
source = getappdata(handle, 'mh_viz_anatomy_source');
plane = getappdata(handle, 'mh_viz_anatomy_plane');
coordinate = getappdata(handle, 'mh_viz_anatomy_coordinate_mm');
transparency = getappdata( ...
    handle, 'mh_viz_anatomy_transparency_percent');
if ~strcmp(source, fiberStyle.AnatomyNifti) || ...
        ~strcmp(plane, fiberStyle.AnatomySlicePlane) || ...
        coordinate ~= fiberStyle.AnatomySliceCoordinateMm || ...
        transparency ~= fiberStyle.AnatomySliceTransparencyPercent || ...
        abs(double(get(handle, 'FaceAlpha')) - 1) > 1e-12
    error('mh_viz_export_pdq39_fiber_pdfs:AnatomySliceMismatch', ...
        'The %s anatomy slice does not match the frozen fiber contract.', role);
end
end

function local_assert_render_style(scene, fiberStyle, role)
metadata = scene.objects.fiberCategoricalMetadata;
if ~strcmp(metadata.selected_render_mode, ...
        fiberStyle.SelectedFiberRenderMode) || ...
        metadata.selected_line_width ~= fiberStyle.SelectedFiberLineWidth
    error('mh_viz_export_pdq39_fiber_pdfs:FiberRenderModeMismatch', ...
        'The %s scene does not use the formal continuous-line contract.', role);
end
names = {'fiberCandidate', 'fiberSweet', 'fiberSour'};
colors = [ ...
    fiberStyle.CandidateFiberColor; ...
    fiberStyle.SweetFiberColor; ...
    fiberStyle.SourFiberColor];
widths = [fiberStyle.CandidateFiberLineWidth; ...
    fiberStyle.SelectedFiberLineWidth; ...
    fiberStyle.SelectedFiberLineWidth];
alphas = [fiberStyle.CandidateFiberAlpha; ...
    fiberStyle.SelectedFiberAlpha; ...
    fiberStyle.SelectedFiberAlpha];
for index = 1:numel(names)
    handles = scene.objects.(names{index});
    handles = handles(isgraphics(handles, 'patch'));
    if numel(handles) ~= 1
        error('mh_viz_export_pdq39_fiber_pdfs:FiberPathCountMismatch', ...
            'The %s %s layer must be one path patch.', role, names{index});
    end
    faces = get(handles(1), 'Faces');
    if size(faces, 2) ~= 2 || ...
            ~strcmpi(get(handles(1), 'FaceColor'), 'none') || ...
            ~isequal(double(get(handles(1), 'EdgeColor')), ...
            colors(index, :)) || ...
            abs(double(get(handles(1), 'EdgeAlpha')) - alphas(index)) > ...
            1e-12 || ...
            abs(double(get(handles(1), 'LineWidth')) - widths(index)) > 1e-12
        error('mh_viz_export_pdq39_fiber_pdfs:FiberPathStyleMismatch', ...
            'The %s %s path style does not match the formal contract.', ...
            role, names{index});
    end
end
end

function local_assert_layer_order(scene, role)
if ~strcmpi(get(scene.axes, 'SortMethod'), 'childorder')
    error('mh_viz_export_pdq39_fiber_pdfs:FiberSortMethodMismatch', ...
        'The %s scene must use childorder rendering.', role);
end
candidate = scene.objects.fiberCandidate;
candidate = candidate(isgraphics(candidate, 'patch'));
selected = [scene.objects.fiberSweet(:); scene.objects.fiberSour(:)];
selected = selected(isgraphics(selected, 'patch'));
children = allchild(scene.axes);
candidateIndex = find(children == candidate, 1);
selectedIndices = arrayfun(@(handle) ...
    find(children == handle, 1), selected);
if isempty(candidateIndex) || numel(selectedIndices) ~= 2 || ...
        any(selectedIndices >= candidateIndex)
    error('mh_viz_export_pdq39_fiber_pdfs:FiberLayerOrderMismatch', ...
        ['The %s scene must place sweet and sour fibers in front of ', ...
        'candidate fibers.'], role);
end
end

function local_assert_legend(scene, fiberStyle, role)
if ~isfield(scene.objects, 'fiberLegend') || ...
        ~isgraphics(scene.objects.fiberLegend, 'legend') || ...
        ~strcmp(get(scene.objects.fiberLegend, 'Tag'), ...
        'mh_viz_fiber_legend')
    error('mh_viz_export_pdq39_fiber_pdfs:MissingFiberLegend', ...
        'The %s scene lacks the categorical fiber legend.', role);
end
lineHandles = scene.objects.fiberLegendHandles;
lineHandles = lineHandles(isgraphics(lineHandles, 'line'));
expectedColors = [ ...
    fiberStyle.CandidateFiberColor; ...
    fiberStyle.SweetFiberColor; ...
    fiberStyle.SourFiberColor];
if numel(lineHandles) ~= 3
    error('mh_viz_export_pdq39_fiber_pdfs:IncompleteFiberLegend', ...
        'The %s scene must contain three legend lines.', role);
end
if ~isequal(double(get(scene.objects.fiberLegend, 'TextColor')), ...
        fiberStyle.FiberLegendTextColor)
    error('mh_viz_export_pdq39_fiber_pdfs:FiberLegendTextMismatch', ...
        'The %s legend text must use the frozen white color.', role);
end
for index = 1:3
    if ~isequal(double(get(lineHandles(index), 'Color')), ...
            expectedColors(index, :)) || ...
            ~strcmp(get(lineHandles(index), 'LineStyle'), '-') || ...
            ~strcmp(get(lineHandles(index), 'Marker'), 'none')
        error('mh_viz_export_pdq39_fiber_pdfs:FiberLegendMismatch', ...
            'The %s legend does not match the frozen horizontal-line style.', ...
            role);
    end
end
end

function local_assert_no_ras(scene, role)
if ~isempty(findall(scene.figure, ...
        'Type', 'axes', 'Tag', 'EA_RAS_TRIAD_AXES'))
    error('mh_viz_export_pdq39_fiber_pdfs:UnexpectedRasTriad', ...
        'The %s default fiber export must omit the RAS triad.', role);
end
end

function local_assert_hidden(figures)
figures = figures(isgraphics(figures, 'figure'));
if isempty(figures)
    error('mh_viz_export_pdq39_fiber_pdfs:MissingFigure', ...
        'Scene construction did not create a MATLAB figure.');
end
for index = 1:numel(figures)
    if strcmpi(get(figures(index), 'Visible'), 'on')
        error('mh_viz_export_pdq39_fiber_pdfs:VisibleFigure', ...
            'Strict-headless export created a visible MATLAB figure.');
    end
end
end

function digest = local_file_sha256(pathValue)
command = sprintf('/usr/bin/shasum -a 256 %s', ...
    mh_fiber_shell_quote(char(string(pathValue))));
[status, output] = system(command);
if status ~= 0
    error('mh_viz_export_pdq39_fiber_pdfs:HashFailed', ...
        'Could not compute SHA-256 for %s: %s', pathValue, output);
end
token = regexp(strtrim(output), '^[0-9a-f]{64}', 'match', 'once');
if isempty(token)
    error('mh_viz_export_pdq39_fiber_pdfs:BadHashOutput', ...
        'Could not parse SHA-256 output for %s.', pathValue);
end
digest = token;
end

function local_write_json(pathValue, payload)
encoded = jsonencode(payload, 'PrettyPrint', true);
fileId = fopen(pathValue, 'w');
if fileId < 0
    error('mh_viz_export_pdq39_fiber_pdfs:ManifestOpenFailed', ...
        'Could not open export manifest for writing: %s', pathValue);
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s\n', encoded);
clear cleanup;
end

function local_delete_figures(figures)
figures = figures(isgraphics(figures, 'figure'));
for index = 1:numel(figures)
    delete(figures(index));
end
end
