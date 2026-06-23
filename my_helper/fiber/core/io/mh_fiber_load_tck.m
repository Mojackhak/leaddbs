function tck = mh_fiber_load_tck(tckPath, maxStreamlines, pointStride)
% Load an MRtrix .tck file into streamline cells and Lead-DBS-style arrays.

if nargin < 2 || isempty(maxStreamlines)
    maxStreamlines = Inf;
end
if nargin < 3 || isempty(pointStride) || pointStride < 1
    pointStride = 1;
end
if ~isfile(tckPath)
    error('mh_fiber_load_tck:MissingFile', 'TCK file does not exist: %s', tckPath);
end

[offset, machineFormat] = read_tck_header(tckPath);
fid = fopen(tckPath, 'r', machineFormat);
if fid < 0
    error('mh_fiber_load_tck:OpenFailed', 'Cannot open TCK file: %s', tckPath);
end
cleanup = onCleanup(@() fclose(fid));
fseek(fid, offset, 'bof');
points = fread(fid, [3, Inf], 'float32=>double')';

terminator = find(any(isinf(points), 2), 1, 'first');
if ~isempty(terminator)
    points = points(1:terminator-1, :);
end

separator = any(isnan(points), 2);
breaks = [0; find(separator); size(points, 1) + 1];
streamlines = {};
for i = 1:(numel(breaks) - 1)
    first = breaks(i) + 1;
    last = breaks(i+1) - 1;
    if last < first
        continue;
    end
    streamline = points(first:last, :);
    if pointStride > 1
        streamline = streamline(1:pointStride:end, :);
        if ~isequal(streamline(end, :), points(last, :))
            streamline(end+1, :) = points(last, :); %#ok<AGROW>
        end
    end
    streamlines{end+1, 1} = streamline; %#ok<AGROW>
    if numel(streamlines) >= maxStreamlines
        break;
    end
end

[fibers, idx] = streamlines_to_fibers(streamlines);
tck = struct();
tck.path = tckPath;
tck.streamlines = streamlines;
tck.fibers = fibers;
tck.idx = idx;
tck.streamlineCount = numel(streamlines);
tck.pointCount = size(fibers, 1);
end

function [offset, machineFormat] = read_tck_header(tckPath)
fid = fopen(tckPath, 'r');
if fid < 0
    error('mh_fiber_load_tck:OpenFailed', 'Cannot open TCK file: %s', tckPath);
end
cleanup = onCleanup(@() fclose(fid));

offset = [];
datatype = '';
while ~feof(fid)
    line = fgetl(fid);
    if ~ischar(line)
        break;
    end
    if startsWith(line, 'file:')
        tokens = regexp(line, 'file:\s+\.\s+(\d+)', 'tokens', 'once');
        if ~isempty(tokens)
            offset = str2double(tokens{1});
        end
    elseif startsWith(line, 'datatype:')
        datatype = strtrim(extractAfter(string(line), 'datatype:'));
    elseif strcmp(strtrim(line), 'END')
        break;
    end
end

if isempty(offset) || ~isfinite(offset)
    error('mh_fiber_load_tck:MissingOffset', 'Cannot parse TCK data offset: %s', tckPath);
end

if contains(datatype, 'BE', 'IgnoreCase', true)
    machineFormat = 'ieee-be';
else
    machineFormat = 'ieee-le';
end
end

function [fibers, idx] = streamlines_to_fibers(streamlines)
idx = cellfun(@(x) size(x, 1), streamlines);
if isempty(idx)
    fibers = zeros(0, 4);
    idx = zeros(0, 1);
    return;
end

totalPoints = sum(idx);
fibers = zeros(totalPoints, 4);
cursor = 1;
for i = 1:numel(streamlines)
    n = size(streamlines{i}, 1);
    rows = cursor:(cursor + n - 1);
    fibers(rows, 1:3) = streamlines{i};
    fibers(rows, 4) = i;
    cursor = cursor + n;
end
idx = idx(:);
end
