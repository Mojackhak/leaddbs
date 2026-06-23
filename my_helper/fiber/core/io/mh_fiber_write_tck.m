function mh_fiber_write_tck(tckPath, streamlines)
% Write streamlines to an MRtrix TCK file.

ea_mkdir(fileparts(tckPath));
fid = fopen(tckPath, 'w', 'ieee-le');
if fid < 0
    error('mh_fiber_write_tck:OpenFailed', 'Cannot write TCK file: %s', tckPath);
end
cleanup = onCleanup(@() fclose(fid));

header = make_header(0, 0);
offset = numel(header);
header = make_header(numel(streamlines), offset);
newOffset = numel(header);
while newOffset ~= offset
    offset = newOffset;
    header = make_header(numel(streamlines), offset);
    newOffset = numel(header);
end

fwrite(fid, header, 'char');
for i = 1:numel(streamlines)
    points = double(streamlines{i});
    if isempty(points)
        continue;
    end
    fwrite(fid, points', 'float32');
    fwrite(fid, single([NaN; NaN; NaN]), 'float32');
end
fwrite(fid, single([Inf; Inf; Inf]), 'float32');
end

function header = make_header(count, offset)
header = sprintf(['mrtrix tracks\n', ...
    'count: %d\n', ...
    'datatype: Float32LE\n', ...
    'file: . %d\n', ...
    'END\n'], count, offset);
end
