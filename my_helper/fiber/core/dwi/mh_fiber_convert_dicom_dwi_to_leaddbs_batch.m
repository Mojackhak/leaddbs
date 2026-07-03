function summary = mh_fiber_convert_dicom_dwi_to_leaddbs_batch(inputs, varargin)
% Convert multiple DWI DICOM folders to Lead-DBS/BIDS DWI four-file sets.

parser = inputParser;
parser.FunctionName = 'mh_fiber_convert_dicom_dwi_to_leaddbs_batch';
parser.addRequired('inputs', @(x) istable(x) || isstruct(x));
parser.addParameter('RepoDir', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Parallel', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('ParallelWorkers', 4, @(x) isnumeric(x) && isscalar(x) && x >= 1);
parser.addParameter('Force', false, @(x) islogical(x) || isnumeric(x));
parser.addParameter('DryRun', false, @(x) islogical(x) || isnumeric(x));
parser.parse(inputs, varargin{:});
opts = normalize_options(parser.Results);

inputTable = normalize_inputs(inputs);
validate_input_columns(inputTable);

nRows = height(inputTable);
rows = repmat(empty_row(), nRows, 1);
useSubjectParallel = opts.Parallel && nRows > 1 && mh_fiber_ensure_parallel_pool(opts.ParallelWorkers);

if useSubjectParallel
    parfor i = 1:nRows
        rows(i) = convert_row(inputTable, i, opts, false);
    end
else
    for i = 1:nRows
        useVolumeParallel = opts.Parallel && nRows == 1;
        rows(i) = convert_row(inputTable, i, opts, useVolumeParallel);
    end
end

summary = struct2table(rows, 'AsArray', true);
end

function opts = normalize_options(opts)
opts.RepoDir = char(string(opts.RepoDir));
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
row.Status = 'started';

try
    result = mh_fiber_convert_dicom_dwi_to_leaddbs( ...
        'DicomDir', row.DicomDir, ...
        'OutputDir', row.OutputDir, ...
        'OutputBase', row.OutputBase, ...
        'RepoDir', opts.RepoDir, ...
        'WorkDir', row.WorkDir, ...
        'ReferenceNifti', row.ReferenceNifti, ...
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

function value = optional_row_value(inputTable, rowIndex, column)
if ismember(column, inputTable.Properties.VariableNames)
    value = row_value(inputTable, rowIndex, column);
else
    value = '';
end
end
