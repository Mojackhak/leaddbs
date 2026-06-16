function mh_fiber_write_ftr_vtk(ftrMatPath, vtkPath)
% Write a Lead-DBS-style fiber MAT file as legacy VTK PolyData lines.

if ~isfile(ftrMatPath)
    error('mh_fiber_write_ftr_vtk:MissingInput', 'Input MAT file does not exist: %s', ftrMatPath);
end

data = load(ftrMatPath, 'fibers', 'idx');
if ~isfield(data, 'fibers') || ~isfield(data, 'idx')
    error('mh_fiber_write_ftr_vtk:InvalidInput', 'Input MAT file is missing fibers or idx: %s', ftrMatPath);
end

ea_mkdir(fileparts(vtkPath));
fid = fopen(vtkPath, 'w');
if fid < 0
    error('mh_fiber_write_ftr_vtk:OpenFailed', 'Cannot write VTK file: %s', vtkPath);
end
cleanup = onCleanup(@() fclose(fid));

fibers = double(data.fibers);
idx = double(data.idx(:));
if isempty(fibers) || isempty(idx) || sum(idx) == 0
    write_header(fid, 0, 0, 0);
    return;
end

if size(fibers, 2) < 3
    error('mh_fiber_write_ftr_vtk:InvalidFibers', 'Fiber array must contain at least three coordinate columns: %s', ftrMatPath);
end

pointCount = size(fibers, 1);
if sum(idx) ~= pointCount
    [fibers, idx] = regroup_by_fiber_id(fibers);
    pointCount = size(fibers, 1);
end

lineCount = numel(idx);
lineIndexCount = sum(idx) + lineCount;
write_header(fid, pointCount, lineCount, lineIndexCount);

for i = 1:pointCount
    fprintf(fid, '%.9g %.9g %.9g\n', fibers(i, 1), fibers(i, 2), fibers(i, 3));
end

fprintf(fid, 'LINES %d %d\n', lineCount, lineIndexCount);
cursor = 0;
for i = 1:lineCount
    n = idx(i);
    fprintf(fid, '%d', n);
    for j = 0:(n - 1)
        fprintf(fid, ' %d', cursor + j);
    end
    fprintf(fid, '\n');
    cursor = cursor + n;
end
end

function write_header(fid, pointCount, lineCount, lineIndexCount)
fprintf(fid, '# vtk DataFile Version 3.0\n');
fprintf(fid, 'Lead-DBS helper fiber display export\n');
fprintf(fid, 'ASCII\n');
fprintf(fid, 'DATASET POLYDATA\n');
fprintf(fid, 'POINTS %d float\n', pointCount);
if pointCount == 0
    fprintf(fid, 'LINES %d %d\n', lineCount, lineIndexCount);
end
end

function [fibers, idx] = regroup_by_fiber_id(fibers)
if size(fibers, 2) < 4
    error('mh_fiber_write_ftr_vtk:InvalidIdx', 'Point count does not match idx and no fiber ID column is available.');
end

ids = unique(fibers(:, 4), 'stable');
parts = cell(numel(ids), 1);
idx = zeros(numel(ids), 1);
for i = 1:numel(ids)
    part = fibers(fibers(:, 4) == ids(i), :);
    parts{i} = part;
    idx(i) = size(part, 1);
end
fibers = vertcat(parts{:});
end
