function settings = mh_oss_map_left_coordinates_to_right( ...
        settings, transformPath, pointMapper)
% Map left template-space OSS electrode geometry into the right slot.
%
% SETTINGS contains Lead-DBS OSS reconstruction geometry. TRANSFORMPATH is
% the exact configured inverse nonlinear field for point coordinates.
%
% The function mirrors x, maps RAS coordinates through the locked ANTs point
% binary using only the supplied inverse field, and copies mapped left contact,
% implantation, second, head, and y-marker geometry into the right slot.

if nargin < 2 || nargin > 3 || ~isstruct(settings) || ~isscalar(settings)
    error('mh_oss:InvalidGeometry', ...
        'Coordinate mapping requires one scalar settings struct and a transform.');
end
transformPath = absolute_file(transformPath, 'transformPath');
if nargin < 3
    pointMapper = @apply_inverse_transform;
elseif ~isa(pointMapper, 'function_handle')
    error('mh_oss:InvalidGeometry', ...
        'pointMapper must be a function handle when supplied for testing.');
end

if ~isfield(settings, 'contactLocation') || ...
        ~iscell(settings.contactLocation) || numel(settings.contactLocation) < 2
    error('mh_oss:InvalidGeometry', ...
        'settings.contactLocation must contain right and left geometry.');
end
leftContacts = coordinate_matrix(settings.contactLocation{2}, ...
    'settings.contactLocation{2}', false);
fieldNames = {'Implantation_coordinate', 'Second_coordinate', ...
    'headMNI', 'yMarkerMNI'};
leftRows = cell(1, numel(fieldNames));
for fieldIndex = 1:numel(fieldNames)
    name = fieldNames{fieldIndex};
    if ~isfield(settings, name)
        error('mh_oss:InvalidGeometry', ...
            'settings.%s is required for template-space mapping.', name);
    end
    matrix = coordinate_matrix(settings.(name), ['settings.' name], true);
    if size(matrix, 1) < 2
        error('mh_oss:InvalidGeometry', ...
            'settings.%s must contain a left row.', name);
    end
    leftRows{fieldIndex} = matrix(2, :);
end

points = [leftContacts; vertcat(leftRows{:})];
mirrored = points;
mirrored(:, 1) = -mirrored(:, 1);
try
    mapped = pointMapper(mirrored, transformPath);
catch ME
    wrapped = MException('mh_oss:CoordinateMappingFailed', ...
        'Could not map left geometry with the configured transform: %s', ...
        transformPath);
    wrapped = addCause(wrapped, ME);
    throw(wrapped);
end

function mappedRas = apply_inverse_transform(pointsRas, transformPath)
pointsLps = pointsRas;
pointsLps(:, 1:2) = -pointsLps(:, 1:2);

stem = tempname;
inputPath = [stem '_input.csv'];
outputPath = [stem '_output.csv'];
cleanup = onCleanup(@() cleanup_files(inputPath, outputPath));
write_points(inputPath, pointsLps);

binaryPath = ants_point_binary();
transformArgument = ['[' transformPath ',0]'];
command = strjoin({shell_quote(binaryPath), ...
    '--dimensionality', '3', '--precision', '0', ...
    '--input', shell_quote(inputPath), ...
    '--output', shell_quote(outputPath), ...
    '--transform', shell_quote(transformArgument)}, ' ');
[status, output] = system(command);
if status ~= 0 || ~isfile(outputPath)
    error('mh_oss:CoordinateMappingFailed', ...
        'ANTs point transform failed with status %d: %s', status, output);
end
mappedLps = read_points(outputPath);
if ~isequal(size(mappedLps), size(pointsLps))
    error('mh_oss:CoordinateMappingFailed', ...
        'ANTs point transform returned an unexpected point count.');
end
mappedRas = mappedLps;
mappedRas(:, 1:2) = -mappedRas(:, 1:2);
clear cleanup;
end

function path = ants_point_binary()
root = fileparts(mfilename('fullpath'));
for level = 1:5
    root = fileparts(root);
end
switch computer
    case 'MACA64'
        suffixes = {'maca64'};
    case 'MACI64'
        suffixes = {'maci64'};
    case 'GLNXA64'
        suffixes = {'glnxa64'};
    case 'PCWIN64'
        suffixes = {'exe'};
    otherwise
        error('mh_oss:CoordinateMappingFailed', ...
            'No locked ANTs point binary is defined for %s.', computer);
end
for index = 1:numel(suffixes)
    candidate = fullfile(root, 'ext_libs', 'ANTs', ...
        ['antsApplyTransformsToPoints.' suffixes{index}]);
    if isfile(candidate)
        path = candidate;
        return
    end
end
error('mh_oss:CoordinateMappingFailed', ...
    'The locked ANTs point-transform binary is unavailable.');
end

function write_points(path, points)
[fileId, message] = fopen(path, 'w');
if fileId < 0
    error('mh_oss:CoordinateMappingFailed', ...
        'Could not create ANTs point input: %s', message);
end
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, 'x,y,z,t\n');
fprintf(fileId, '%.17g,%.17g,%.17g,0\n', points');
clear cleanup;
end

function points = read_points(path)
[fileId, message] = fopen(path, 'r');
if fileId < 0
    error('mh_oss:CoordinateMappingFailed', ...
        'Could not read ANTs point output: %s', message);
end
cleanup = onCleanup(@() fclose(fileId));
values = textscan(fileId, '%f%f%f%f', 'Delimiter', ',', ...
    'HeaderLines', 1, 'CollectOutput', true);
points = values{1}(:, 1:3);
clear cleanup;
end

function value = shell_quote(raw)
raw = char(raw);
if ispc
    quote = char(34);
    value = [quote strrep(raw, quote, [quote quote]) quote];
else
    quote = char(39);
    embedded = [quote char(34) quote char(34) quote];
    value = [quote strrep(raw, quote, embedded) quote];
end
end

function cleanup_files(varargin)
for index = 1:numel(varargin)
    if isfile(varargin{index})
        delete(varargin{index});
    end
end
end
if ~isequal(size(mapped), size(points)) || any(~isfinite(mapped), 'all')
    error('mh_oss:CoordinateMappingFailed', ...
        'Configured transform returned invalid mapped geometry.');
end

contactCount = size(leftContacts, 1);
settings.contactLocation{1} = mapped(1:contactCount, :);
cursor = contactCount;
for fieldIndex = 1:numel(fieldNames)
    cursor = cursor + 1;
    name = fieldNames{fieldIndex};
    settings.(name)(1, :) = mapped(cursor, :);
end
end

function path = absolute_file(raw, label)
if ischar(raw) && isrow(raw)
    path = raw;
elseif isstring(raw) && isscalar(raw) && ~ismissing(raw)
    path = char(raw);
else
    error('mh_oss:InvalidGeometry', '%s must be a text scalar.', label);
end
if isempty(path) || ~is_absolute_path(path)
    error('mh_oss:InvalidGeometry', '%s must be an absolute path.', label);
end
if ~isfile(path)
    error('mh_oss:InvalidGeometry', '%s does not exist: %s', label, path);
end
end

function value = coordinate_matrix(raw, label, allowMultipleRows)
if ~isnumeric(raw) || ~ismatrix(raw) || size(raw, 2) ~= 3 || isempty(raw)
    error('mh_oss:InvalidGeometry', '%s must be a nonempty N-by-3 matrix.', label);
end
value = double(raw);
if ~allowMultipleRows && size(value, 1) < 1
    error('mh_oss:InvalidGeometry', '%s must contain coordinates.', label);
end
if any(~isfinite(value), 'all')
    error('mh_oss:InvalidGeometry', '%s must contain only finite values.', label);
end
end

function tf = is_absolute_path(path)
if ispc
    tf = ~isempty(regexp(path, '^[A-Za-z]:[\\/]', 'once')) || ...
        startsWith(path, '\\');
else
    tf = startsWith(path, filesep);
end
end
