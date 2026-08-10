function exports = mh_viz_export_pdq39_voxel_pdfs(outputDirectory, varargin)
% Export four PDQ-39 voxel PDFs with the MyLFP strict-headless contract.

parser = inputParser;
parser.FunctionName = mfilename;
addRequired(parser, 'outputDirectory', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'PublicationRoot', ...
    '/Volumes/VAL/STNSNr/summary/spot/direct_voxel', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
addParameter(parser, 'ScaleId', 'pdq39_score', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
addParameter(parser, 'Views', mh_viz_default_model_views(), ...
    @(value) isstruct(value) && isscalar(value));
addParameter(parser, 'FilePrefix', 'pdq39_voxel', ...
    @(value) ischar(value) || (isstring(value) && isscalar(value)));
addParameter(parser, 'Resolution', 450, ...
    @(value) isnumeric(value) && isscalar(value) && ...
    isfinite(value) && value > 0);
parse(parser, outputDirectory, varargin{:});

outputDirectory = char(string(parser.Results.outputDirectory));
if isempty(strtrim(outputDirectory))
    error('mh_viz_export_pdq39_voxel_pdfs:MissingOutputDirectory', ...
        'outputDirectory must be nonempty.');
end
if ~isfolder(outputDirectory)
    mkdir(outputDirectory);
end

publicationRoot = char(string(parser.Results.PublicationRoot));
scaleId = char(string(parser.Results.ScaleId));
views = parser.Results.Views;
filePrefix = char(string(parser.Results.FilePrefix));
resolution = double(parser.Results.Resolution);

oldDefaultFigureVisible = get(groot, 'DefaultFigureVisible');
set(groot, 'DefaultFigureVisible', 'off');
visibilityCleanup = onCleanup(@() set( ...
    groot, 'DefaultFigureVisible', oldDefaultFigureVisible)); %#ok<NASGU>

roles = {'reference', 'addon'};
atlasRoiIndices = [2, 1];
exports = repmat(struct('model_role', '', 'view_index', 0, ...
    'view', struct(), 'pdf_path', ''), 0, 1);

for roleIndex = 1:numel(roles)
    role = roles{roleIndex};
    surfaceInput = fullfile( ...
        publicationRoot, scaleId, role, 'visualization', 'spatial_2d', ...
        'maps', 'display.nii.gz');
    if ~isfile(surfaceInput)
        error('mh_viz_export_pdq39_voxel_pdfs:MissingSurfaceInput', ...
            'Retained 0.1 mm surface input does not exist: %s', surfaceInput);
    end

    spec = struct();
    spec.VoxelSignedNifti = surfaceInput;
    spec.VoxelColorbarLabel = ...
        'Benefit-oriented partial Spearman ρ with PDQ39 score';
    spec.VoxelSampleDepthMm = 0.25;
    spec.AtlasName = 'Custom_STNSNr';
    spec.ShowAtlasWireframe = true;
    spec.AtlasRoiIndices = atlasRoiIndices(roleIndex);
    spec.AtlasEdgeAlpha = 0.15;
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

    roleExports = mh_viz_export_scene_views( ...
        scene, outputDirectory, role, ...
        'Views', views, ...
        'FilePrefix', filePrefix, ...
        'Resolution', resolution);
    exports = [exports; roleExports(:)]; %#ok<AGROW>
    local_assert_hidden(newFigures);

    local_delete_figures(newFigures);
    clear figureCleanup;
end

if numel(exports) ~= 4
    error('mh_viz_export_pdq39_voxel_pdfs:IncompleteExport', ...
        'Strict-headless export must produce exactly four PDFs.');
end
end

function local_assert_hidden(figures)
figures = figures(isgraphics(figures, 'figure'));
if isempty(figures)
    error('mh_viz_export_pdq39_voxel_pdfs:MissingFigure', ...
        'Scene construction did not create a MATLAB figure.');
end
for index = 1:numel(figures)
    if strcmpi(get(figures(index), 'Visible'), 'on')
        error('mh_viz_export_pdq39_voxel_pdfs:VisibleFigure', ...
            'Strict-headless export created a visible MATLAB figure.');
    end
end
end

function local_delete_figures(figures)
figures = figures(isgraphics(figures, 'figure'));
for index = 1:numel(figures)
    delete(figures(index));
end
end
