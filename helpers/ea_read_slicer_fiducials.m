function markers = ea_read_slicer_fiducials(filename, sides)
% Parse Slicer fiducial pairs by electrode identity, returning RAS millimeters.
contents = fileread(filename);
system = regexp(contents, '# CoordinateSystem\s*=\s*([^\r\n]+)', 'tokens', 'once');
if isempty(system) || ~ismember(strtrim(system{1}), {'0', '1', 'RAS', 'LPS'})
    error('LeadDBS:InvalidFiducials', 'The fiducial file must declare RAS or LPS coordinates.');
end
rows = textscan(contents, '%s %f %f %f %f %f %f %f %f %f %f %s %s %s', ...
    'Delimiter', ',', 'CommentStyle', '#', 'ReturnOnError', false);
coordinates = [rows{2}, rows{3}, rows{4}];
labels = rows{12};
if numel(labels) ~= size(coordinates, 1) || any(~isfinite(coordinates(:)))
    error('LeadDBS:InvalidFiducials', 'Fiducial rows must contain finite coordinates and labels.');
end
if ismember(strtrim(system{1}), {'1', 'LPS'})
    coordinates(:, 1:2) = -coordinates(:, 1:2);
end
markers = repmat(struct('head', [], 'tail', [], 'x', [], 'y', []), 1, max(sides));
for side = sides
    head = find(strcmp(labels, sprintf('Head_%d', side)));
    tail = find(strcmp(labels, sprintf('Tail_%d', side)));
    if numel(head) ~= 1 || numel(tail) ~= 1 || isequal(coordinates(head, :), coordinates(tail, :))
        error('LeadDBS:InvalidFiducials', 'Electrode %d requires one distinct Head_%d and Tail_%d pair.', side, side, side);
    end
    markers(side).head = coordinates(head, :);
    markers(side).tail = coordinates(tail, :);
end
end
