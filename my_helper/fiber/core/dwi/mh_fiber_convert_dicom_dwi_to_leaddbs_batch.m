function summary = mh_fiber_convert_dicom_dwi_to_leaddbs_batch(inputs, varargin)
% Convert multiple DWI DICOM folders to Lead-DBS/BIDS DWI four-file sets.

parser = inputParser;
parser.FunctionName = 'mh_fiber_convert_dicom_dwi_to_leaddbs_batch';
parser.addRequired('inputs', @(x) istable(x) || isstruct(x));
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('TileOrder', 'row_major_right_to_left', @(x) ischar(x) || isstring(x));
parser.addParameter('SkipPaddingTiles', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.parse(inputs, varargin{:});
opts = normalize_options(parser.Results);

inputTable = normalize_inputs(inputs);
validate_input_columns(inputTable);

nRows = height(inputTable);
rows = mh_fiber_run_item_batch(nRows, ...
    @(rowIndex, useVolumeParallel, ~) convert_row(inputTable, rowIndex, opts, useVolumeParallel), ...
    empty_row(), ...
    'Parallel', opts.Parallel, ...
    'ParallelWorkers', opts.ParallelWorkers);

summary = struct2table(rows, 'AsArray', true);
end

function opts = normalize_options(opts)
opts.RepoDir = char(string(opts.RepoDir));
opts.TileOrder = validatestring(char(string(opts.TileOrder)), ...
    {'row_major_right_to_left', 'row_major_left_to_right', ...
    'bottom_to_top_left_to_right'}, ...
    'mh_fiber_convert_dicom_dwi_to_leaddbs_batch', 'TileOrder');
opts.SkipPaddingTiles = logical(opts.SkipPaddingTiles);
opts.Parallel = logical(opts.Parallel);
opts.ParallelWorkers = max(1, round(double(opts.ParallelWorkers)));
opts.Force = logical(opts.Force);
opts.DryRun = logical(opts.DryRun);
end

function inputTable = normalize_inputs(inputs)
if istable(inputs)
    inputTable = inputs;
else
    inputTable = struct2table(inputs);
end
end

function validate_input_columns(inputTable)
required = {'Subject', 'DicomDir', 'OutputDir', 'OutputBase'};
for i = 1:numel(required)
    if ~ismember(required{i}, inputTable.Properties.VariableNames)
        error('mh_fiber_convert_dicom_dwi_to_leaddbs_batch:MissingColumn', ...
            'Input table is missing required column: %s', required{i});
    end
end
end

function row = convert_row(inputTable, rowIndex, opts, useVolumeParallel)
row = empty_row();
row.Subject = row_value(inputTable, rowIndex, 'Subject');
row.DicomDir = row_value(inputTable, rowIndex, 'DicomDir');
row.OutputDir = row_value(inputTable, rowIndex, 'OutputDir');
row.OutputBase = row_value(inputTable, rowIndex, 'OutputBase');
row.WorkDir = optional_row_value(inputTable, rowIndex, 'WorkDir');
row.ReferenceNifti = optional_row_value(inputTable, rowIndex, 'ReferenceNifti');
row.TileOrder = optional_row_value(inputTable, rowIndex, 'TileOrder', opts.TileOrder);
row.SkipPaddingTiles = optional_logical_row_value(inputTable, rowIndex, ...
    'SkipPaddingTiles', opts.SkipPaddingTiles);
row.Status = 'started';

try
    result = mh_fiber_convert_dicom_dwi_to_leaddbs( ...
        'DicomDir', row.DicomDir, ...
        'OutputDir', row.OutputDir, ...
        'OutputBase', row.OutputBase, ...
        'RepoDir', opts.RepoDir, ...
        'WorkDir', row.WorkDir, ...
        'ReferenceNifti', row.ReferenceNifti, ...
        'SliceCount', optional_numeric_row_value(inputTable, rowIndex, 'SliceCount'), ...
        'TileOrder', row.TileOrder, ...
        'SkipPaddingTiles', row.SkipPaddingTiles, ...
        'Parallel', useVolumeParallel, ...
        'ParallelWorkers', opts.ParallelWorkers, ...
        'Force', opts.Force, ...
        'DryRun', opts.DryRun);
    row.Status = result.Status;
    row.Message = result.Message;
    row.Decision = result.Decision;
    row.OutputNifti = result.OutputNifti;
    row.OutputJson = result.OutputJson;
    row.OutputBval = result.OutputBval;
    row.OutputBvec = result.OutputBvec;
    row.QcJson = result.QcJson;
    row.ConvertedNifti = result.ConvertedNifti;
    row.ConvertedImageSize = result.ConvertedImageSize;
    row.OutputImageSize = result.OutputImageSize;
    row.Dcm2niixSource = result.Dcm2niixSource;
    row.TileOrder = result.TileOrder;
    row.SkipPaddingTiles = result.SkipPaddingTiles;
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
row.Decision = '';
row.DicomDir = '';
row.OutputDir = '';
row.OutputBase = '';
row.WorkDir = '';
row.ReferenceNifti = '';
row.TileOrder = '';
row.SkipPaddingTiles = false;
row.OutputNifti = '';
row.OutputJson = '';
row.OutputBval = '';
row.OutputBvec = '';
row.QcJson = '';
row.ConvertedNifti = '';
row.ConvertedImageSize = '';
row.OutputImageSize = '';
row.Dcm2niixSource = '';
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
if isempty(raw)
    return;
end
value = double(raw);
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
