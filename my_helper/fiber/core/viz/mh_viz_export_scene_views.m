function exports = mh_viz_export_scene_views(scene, outputDirectory, modelRole, varargin)
% Export configured reference or add-on scene views as PDF files.

parser = inputParser;
parser.FunctionName = mfilename;
addRequired(parser, 'scene', @(value) isstruct(value) && isscalar(value));
addRequired(parser, 'outputDirectory', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addRequired(parser, 'modelRole', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'Views', mh_viz_default_model_views(), ...
    @(value) isstruct(value) && isscalar(value));
addParameter(parser, 'FilePrefix', 'scene', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'BackgroundColor', [1 1 1], ...
    @(value) isnumeric(value) && numel(value) == 3 && ...
    all(isfinite(value)) && all(value >= 0) && all(value <= 1));
addParameter(parser, 'Resolution', 450, ...
    @(value) isnumeric(value) && isscalar(value) && ...
    isfinite(value) && value > 0);
addParameter(parser, 'Renderer', 'painters', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'ContentType', 'mixed', @(value) ischar(value) || ...
    (isstring(value) && isscalar(value)));
addParameter(parser, 'UseSymbolForGreek', false, ...
    @(value) islogical(value) && isscalar(value));
addParameter(parser, 'IncludeAnatomySlices', false, ...
    @(value) islogical(value) && isscalar(value));
addParameter(parser, 'RequireRASLabels', true, ...
    @(value) islogical(value) && isscalar(value));
parse(parser, scene, outputDirectory, modelRole, varargin{:});

[hFig, hAx] = local_scene_handles(parser.Results.scene);
role = validatestring(lower(strtrim(char(string(parser.Results.modelRole)))), ...
    {'reference', 'addon'}, mfilename, 'modelRole');
views = parser.Results.Views;
if ~isfield(views, role)
    error('mh_viz_export_scene_views:MissingRoleViews', ...
        'Views must contain a %s field.', role);
end
roleViews = views.(role);
if ~iscell(roleViews) || isempty(roleViews)
    error('mh_viz_export_scene_views:BadRoleViews', ...
        'Views.%s must be a nonempty cell array.', role);
end
for viewIndex = 1:numel(roleViews)
    local_validate_view(roleViews{viewIndex}, role, viewIndex);
end

outputDirectory = char(string(parser.Results.outputDirectory));
if isempty(strtrim(outputDirectory))
    error('mh_viz_export_scene_views:MissingOutputDirectory', ...
        'outputDirectory must be nonempty.');
end
if ~isfolder(outputDirectory)
    mkdir(outputDirectory);
end
filePrefix = strtrim(char(string(parser.Results.FilePrefix)));
if isempty(filePrefix) || contains(filePrefix, '/') || contains(filePrefix, '\')
    error('mh_viz_export_scene_views:BadFilePrefix', ...
        'FilePrefix must be nonempty and must not contain path separators.');
end

outputPaths = cell(numel(roleViews), 1);
for viewIndex = 1:numel(roleViews)
    filename = sprintf('%s_%s_view%02d.pdf', filePrefix, role, viewIndex);
    outputPaths{viewIndex} = fullfile(outputDirectory, filename);
    if isfile(outputPaths{viewIndex})
        error('mh_viz_export_scene_views:OutputExists', ...
            'Refusing to replace an existing PDF: %s', outputPaths{viewIndex});
    end
end

if exist('ea_capture_view_struct', 'file') ~= 2 || ...
        exist('ea_apply_view_struct', 'file') ~= 2 || ...
        exist('ea_export_figure_transparent', 'file') ~= 2
    error('mh_viz_export_scene_views:MissingSurfaceHelper', ...
        'Required migrated view or PDF export helpers are unavailable.');
end
originalView = ea_capture_view_struct(hAx);
[anatomyHandles, anatomyVisibility] = local_anatomy_state( ...
    parser.Results.scene);
if ~parser.Results.IncludeAnatomySlices && ~isempty(anatomyHandles)
    set(anatomyHandles, 'Visible', 'off');
end
[atlasHandles, atlasVisibility] = local_atlas_state(parser.Results.scene);
local_apply_role_roi_visibility(atlasHandles, role);
restoreCleanup = onCleanup(@() local_restore_scene( ...
    originalView, hAx, hFig, anatomyHandles, anatomyVisibility, ...
    atlasHandles, atlasVisibility));

exports = repmat(struct('model_role', role, 'view_index', 0, ...
    'view', struct(), 'pdf_path', ''), numel(roleViews), 1);
for viewIndex = 1:numel(roleViews)
    viewSpec = roleViews{viewIndex};
    ea_apply_view_struct(viewSpec, hAx);
    local_assert_camera(hAx, viewSpec, role, viewIndex);
    local_apply_camera_lighting(hAx);
    local_restore_ras_labels( ...
        parser.Results.scene, hFig, parser.Results.RequireRASLabels);
    drawnow;

    temporaryPdf = [tempname(outputDirectory), '.pdf'];
    temporaryCleanup = onCleanup(@() local_delete_temporary(temporaryPdf));
    ea_export_figure_transparent(hFig, temporaryPdf, ...
        'Transparent', false, ...
        'BackgroundColor', double(parser.Results.BackgroundColor(:))', ...
        'Resolution', parser.Results.Resolution, ...
        'Renderer', char(string(parser.Results.Renderer)), ...
        'ContentType', char(string(parser.Results.ContentType)), ...
        'UseSymbolForGreek', parser.Results.UseSymbolForGreek);
    if ~isfile(temporaryPdf) || dir(temporaryPdf).bytes == 0
        error('mh_viz_export_scene_views:IncompletePdf', ...
            'PDF export did not produce a nonempty file for view %d.', viewIndex);
    end
    [moved, message] = movefile(temporaryPdf, outputPaths{viewIndex});
    if ~moved
        error('mh_viz_export_scene_views:PublishFailed', ...
            'Could not publish PDF view %d: %s', viewIndex, message);
    end
    clear temporaryCleanup;

    exports(viewIndex).view_index = viewIndex;
    exports(viewIndex).view = viewSpec;
    exports(viewIndex).pdf_path = outputPaths{viewIndex};
end

local_restore_scene( ...
    originalView, hAx, hFig, anatomyHandles, anatomyVisibility, ...
    atlasHandles, atlasVisibility);
clear restoreCleanup;
end

function [hFig, hAx] = local_scene_handles(scene)
requiredFields = {'figure', 'axes'};
for index = 1:numel(requiredFields)
    if ~isfield(scene, requiredFields{index})
        error('mh_viz_export_scene_views:BadScene', ...
            'scene must contain %s.', requiredFields{index});
    end
end
hFig = scene.figure;
hAx = scene.axes;
if ~isgraphics(hFig, 'figure') || ~isgraphics(hAx, 'axes') || ...
        ~isequal(ancestor(hAx, 'figure'), hFig)
    error('mh_viz_export_scene_views:BadSceneHandles', ...
        'scene figure and axes must be valid and aligned.');
end
end

function local_validate_view(viewSpec, role, viewIndex)
if ~isstruct(viewSpec) || ~isscalar(viewSpec)
    error('mh_viz_export_scene_views:BadView', ...
        'Views.%s{%d} must be a scalar struct.', role, viewIndex);
end
scalarFields = {'az', 'el', 'camva'};
for index = 1:numel(scalarFields)
    field = scalarFields{index};
    if ~isfield(viewSpec, field) || ~isnumeric(viewSpec.(field)) || ...
            ~isscalar(viewSpec.(field)) || ~isfinite(viewSpec.(field))
        error('mh_viz_export_scene_views:BadViewScalar', ...
            'Views.%s{%d}.%s must be a finite numeric scalar.', ...
            role, viewIndex, field);
    end
end
vectorFields = {'camup', 'camtarget', 'campos'};
for index = 1:numel(vectorFields)
    field = vectorFields{index};
    if ~isfield(viewSpec, field) || ~isnumeric(viewSpec.(field)) || ...
            numel(viewSpec.(field)) ~= 3 || ...
            ~all(isfinite(viewSpec.(field)), 'all')
        error('mh_viz_export_scene_views:BadViewVector', ...
            'Views.%s{%d}.%s must contain three finite values.', ...
            role, viewIndex, field);
    end
end
if ~isfield(viewSpec, 'camproj') || ...
        ~(ischar(viewSpec.camproj) || ...
        (isstring(viewSpec.camproj) && isscalar(viewSpec.camproj))) || ...
        ~ismember(lower(strtrim(char(string(viewSpec.camproj)))), ...
        {'orthographic', 'perspective'})
    error('mh_viz_export_scene_views:BadProjection', ...
        'Views.%s{%d}.camproj must be orthographic or perspective.', ...
        role, viewIndex);
end
end

function local_restore_ras_labels(scene, hFig, required)
textHandles = gobjects(0, 1);
if isfield(scene, 'objects') && isstruct(scene.objects) && ...
        isfield(scene.objects, 'rasTriad') && isstruct(scene.objects.rasTriad)
    triad = scene.objects.rasTriad;
    if isfield(triad, 'refresh') && isa(triad.refresh, 'function_handle')
        triad.refresh();
    end
    for field = {'tR', 'tA', 'tS'}
        if isfield(triad, field{1}) && isgraphics(triad.(field{1}), 'text')
            textHandles(end + 1, 1) = triad.(field{1}); %#ok<AGROW>
        end
    end
end
tagged = findall(hFig, '-regexp', 'Tag', '^EA_RAS_TRIAD_LABEL_[RAS]$');
textHandles = unique([textHandles; tagged(:)]);
if isempty(textHandles)
    if required
        error('mh_viz_export_scene_views:MissingRasLabels', ...
            'The scene does not contain visible RAS letter handles.');
    end
    return;
end
set(textHandles, 'Visible', 'on', 'Clipping', 'off');
try
    uistack(textHandles, 'top');
catch
end
end

function [handles, visibility] = local_anatomy_state(scene)
handles = gobjects(0, 1);
visibility = cell(0, 1);
if ~isfield(scene, 'objects') || ~isstruct(scene.objects) || ...
        ~isfield(scene.objects, 'anatomySlices')
    return;
end
candidate = scene.objects.anatomySlices;
candidate = candidate(isgraphics(candidate));
handles = candidate(:);
visibility = cell(numel(handles), 1);
for index = 1:numel(handles)
    visibility{index} = get(handles(index), 'Visible');
end
end

function [handles, visibility] = local_atlas_state(scene)
handles = gobjects(0, 1);
visibility = cell(0, 1);
if ~isfield(scene, 'objects') || ~isstruct(scene.objects) || ...
        ~isfield(scene.objects, 'atlasWireframes')
    return;
end
candidate = scene.objects.atlasWireframes;
candidate = candidate(isgraphics(candidate));
handles = candidate(:);
visibility = cell(numel(handles), 1);
for index = 1:numel(handles)
    visibility{index} = get(handles(index), 'Visible');
end
end

function local_apply_role_roi_visibility(handles, role)
requiredRoiIndex = 2;
if strcmp(role, 'addon')
    requiredRoiIndex = 1;
end
matched = false(size(handles));
for index = 1:numel(handles)
    userData = get(handles(index), 'UserData');
    if isstruct(userData) && isfield(userData, 'atlas_name') && ...
            strcmp(char(string(userData.atlas_name)), 'Custom_STNSNr') && ...
            isfield(userData, 'roi_index') && ...
            isequal(double(userData.roi_index), requiredRoiIndex)
        matched(index) = true;
    end
end
if ~any(matched)
    error('mh_viz_export_scene_views:MissingRoleRoi', ...
        'The %s scene requires Custom_STNSNr ROI %d.', ...
        role, requiredRoiIndex);
end
set(handles(~matched), 'Visible', 'off');
set(handles(matched), 'Visible', 'on');
end

function local_assert_camera(hAx, expected, role, viewIndex)
actual = ea_capture_view_struct(hAx);
if ~strcmpi(char(string(actual.camproj)), char(string(expected.camproj)))
    error('mh_viz_export_scene_views:CameraMismatch', ...
        'The %s view %d projection differs after application.', role, viewIndex);
end
local_assert_camera_values(actual.camva, expected.camva, 1e-10, ...
    role, viewIndex, 'camva');
local_assert_camera_values(actual.camup, expected.camup, 1e-10, ...
    role, viewIndex, 'camup');
local_assert_camera_values(actual.camtarget, expected.camtarget, 1e-8, ...
    role, viewIndex, 'camtarget');
local_assert_camera_values(actual.campos, expected.campos, 1e-8, ...
    role, viewIndex, 'campos');
end

function local_assert_camera_values(actual, expected, tolerance, ...
        role, viewIndex, field)
actual = double(actual(:));
expected = double(expected(:));
if ~isequal(size(actual), size(expected)) || ...
        any(abs(actual - expected) > tolerance)
    error('mh_viz_export_scene_views:CameraMismatch', ...
        'The %s view %d %s differs after application.', ...
        role, viewIndex, field);
end
end

function local_restore_scene( ...
        viewSpec, hAx, hFig, anatomyHandles, anatomyVisibility, ...
        atlasHandles, atlasVisibility)
for index = 1:numel(anatomyHandles)
    if isgraphics(anatomyHandles(index))
        try
            set(anatomyHandles(index), 'Visible', anatomyVisibility{index});
        catch
        end
    end
end
for index = 1:numel(atlasHandles)
    if isgraphics(atlasHandles(index))
        try
            set(atlasHandles(index), 'Visible', atlasVisibility{index});
        catch
        end
    end
end
if isgraphics(hAx, 'axes')
    try
        ea_apply_view_struct(viewSpec, hAx);
        local_apply_camera_lighting(hAx);
    catch
    end
end
if isgraphics(hFig, 'figure')
    try
        drawnow;
    catch
    end
end
end

function local_apply_camera_lighting(hAx)
if exist('mh_viz_apply_soft_camera_lighting', 'file') ~= 2
    error('mh_viz_export_scene_views:MissingLightingHelper', ...
        'The soft camera-lighting helper is unavailable.');
end
mh_viz_apply_soft_camera_lighting(hAx);
end

function local_delete_temporary(path)
if isfile(path)
    delete(path);
end
end
