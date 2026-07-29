function summary = mh_fiber_reconstruct_mosaic_dwi_batch(inputs, varargin)
% Reconstruct multiple independent Siemens SaveBySlc mosaic DWI inputs.

parser = inputParser;
parser.FunctionName = 'mh_fiber_reconstruct_mosaic_dwi_batch';
parser.addRequired('inputs', @(x) istable(x) || isstruct(x));
parser.addParameter('TileOrder', 'row_major_right_to_left', @(x) ischar(x) || isstring(x));
parser.addParameter('SkipPaddingTiles', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.parse(inputs, varargin{:});
opts = parser.Results;
opts.TileOrder = validatestring(char(string(opts.TileOrder)), ...
    {'row_major_right_to_left', 'row_major_left_to_right', ...
    'bottom_to_top_left_to_right'}, ...
    'mh_fiber_reconstruct_mosaic_dwi_batch', 'TileOrder');
opts.SkipPaddingTiles = logical(opts.SkipPaddingTiles);
opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
opts.Force = logical(opts.Force);
opts.DryRun = logical(opts.DryRun);

inputTable = normalize_inputs(inputs);
validate_input_columns(inputTable);

nRows = height(inputTable);
rows = mh_fiber_run_item_batch(nRows, ...
    @(rowIndex, useVolumeParallel, ~) reconstruct_row(inputTable, rowIndex, opts, useVolumeParallel), ...
    empty_row(), ...
    'Parallel', opts.Parallel, ...
    'ParallelWorkers', opts.ParallelWorkers);

summary = struct2table(rows, 'AsArray', true);
end

function inputTable = normalize_inputs(inputs)
if istable(inputs)
    inputTable = inputs;
else
    inputTable = struct2table(inputs);
end
end

function validate_input_columns(inputTable)
required = {'Subject', 'SourceNifti', 'SourceJson', 'SourceBval', ...
    'SourceBvec', 'OutputDir', 'OutputBase'};
for i = 1:numel(required)
    if ~ismember(required{i}, inputTable.Properties.VariableNames)
        error('mh_fiber_reconstruct_mosaic_dwi_batch:MissingColumn', ...
            'Input table is missing required column: %s', required{i});
    end
end
end

function row = reconstruct_row(inputTable, rowIndex, opts, useVolumeParallel)
row = empty_row();
row.Subject = row_value(inputTable, rowIndex, 'Subject');
row.SourceNifti = row_value(inputTable, rowIndex, 'SourceNifti');
row.SourceJson = row_value(inputTable, rowIndex, 'SourceJson');
row.SourceBval = row_value(inputTable, rowIndex, 'SourceBval');
row.SourceBvec = row_value(inputTable, rowIndex, 'SourceBvec');
row.DicomDir = optional_row_value(inputTable, rowIndex, 'DicomDir');
row.ReferenceNifti = optional_row_value(inputTable, rowIndex, 'ReferenceNifti');
row.OutputDir = row_value(inputTable, rowIndex, 'OutputDir');
row.OutputBase = row_value(inputTable, rowIndex, 'OutputBase');
row.TileOrder = optional_row_value(inputTable, rowIndex, 'TileOrder', opts.TileOrder);
row.SkipPaddingTiles = optional_logical_row_value(inputTable, rowIndex, ...
    'SkipPaddingTiles', opts.SkipPaddingTiles);
row.Status = 'started';

try
    result = mh_fiber_reconstruct_mosaic_dwi( ...
        'SourceNifti', row.SourceNifti, ...
        'SourceJson', row.SourceJson, ...
        'SourceBval', row.SourceBval, ...
        'SourceBvec', row.SourceBvec, ...
        'OutputDir', row.OutputDir, ...
        'OutputBase', row.OutputBase, ...
        'DicomDir', row.DicomDir, ...
        'ReferenceNifti', row.ReferenceNifti, ...
        'TileSize', optional_numeric_row_value(inputTable, rowIndex, 'TileSize'), ...
        'TileGrid', optional_numeric_row_value(inputTable, rowIndex, 'TileGrid'), ...
        'SliceCount', optional_numeric_row_value(inputTable, rowIndex, 'SliceCount'), ...
        'TileOrder', row.TileOrder, ...
        'SkipPaddingTiles', row.SkipPaddingTiles, ...
        'Parallel', useVolumeParallel, ...
        'ParallelWorkers', opts.ParallelWorkers, ...
        'Force', opts.Force, ...
        'DryRun', opts.DryRun);
    row.Status = result.Status;
    row.Message = result.Message;
    row.OutputNifti = result.OutputNifti;
    row.OutputJson = result.OutputJson;
    row.OutputBval = result.OutputBval;
    row.OutputBvec = result.OutputBvec;
    row.QcJson = result.QcJson;
    row.GeometrySource = result.GeometrySource;
    row.SliceCountSource = result.SliceCountSource;
    row.TileSize = result.TileSize;
    row.TileGrid = result.TileGrid;
    row.TileOrder = result.TileOrder;
    row.SkipPaddingTiles = result.SkipPaddingTiles;
    row.SliceCount = result.SliceCount;
    row.VolumeCount = result.VolumeCount;
    row.OutputImageSize = result.OutputImageSize;
    row.AffineSource = result.AffineSource;
    row.AffineOriginPolicy = result.AffineOriginPolicy;
    row.BvecValidationMedianError = result.BvecValidationMedianError;
    row.BvecValidationMaxError = result.BvecValidationMaxError;
catch ME
    row.Status = 'failed';
    row.Message = mh_fiber_compact_message(ME.message);
end
end

function row = empty_row()
row = struct();
row.Subject = '';
row.Status = '';
row.Message = '';
row.SourceNifti = '';
row.SourceJson = '';
row.SourceBval = '';
row.SourceBvec = '';
row.DicomDir = '';
row.ReferenceNifti = '';
row.OutputDir = '';
row.OutputBase = '';
row.TileOrder = '';
row.SkipPaddingTiles = false;
row.OutputNifti = '';
row.OutputJson = '';
row.OutputBval = '';
row.OutputBvec = '';
row.QcJson = '';
row.GeometrySource = '';
row.SliceCountSource = '';
row.TileSize = '';
row.TileGrid = '';
row.SliceCount = NaN;
row.VolumeCount = NaN;
row.OutputImageSize = '';
row.AffineSource = '';
row.AffineOriginPolicy = '';
row.BvecValidationMedianError = NaN;
row.BvecValidationMaxError = NaN;
end

function value = row_value(inputTable, rowIndex, column)
raw = inputTable.(column)(rowIndex);
if iscell(raw)
    value = raw{1};
else
    value = raw;
end
value = char(string(value));
end

function value = optional_row_value(inputTable, rowIndex, column, defaultValue)
if nargin < 4
    defaultValue = '';
end
if ismember(column, inputTable.Properties.VariableNames)
    value = row_value(inputTable, rowIndex, column);
else
    value = defaultValue;
end
end

function value = optional_numeric_row_value(inputTable, rowIndex, column)
value = [];
if ~ismember(column, inputTable.Properties.VariableNames)
    return;
end
raw = inputTable.(column)(rowIndex);
if iscell(raw)
    raw = raw{1};
end
if isempty(raw) || (isstring(raw) && strlength(raw) == 0)
    return;
end
if isnumeric(raw)
    value = double(raw);
else
    value = str2num(char(string(raw))); %#ok<ST2NM>
end
end

function value = optional_logical_row_value(inputTable, rowIndex, column, defaultValue)
value = defaultValue;
if ~ismember(column, inputTable.Properties.VariableNames)
    return;
end
raw = inputTable.(column)(rowIndex);
if iscell(raw)
    raw = raw{1};
end
if isempty(raw)
    return;
end
value = logical(raw);
end
