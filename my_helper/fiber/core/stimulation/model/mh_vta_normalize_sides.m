function sides = mh_vta_normalize_sides(request)
% Normalize side inputs to a cell array of side codes.

if isstruct(request) && isfield(request, 'sides') && ~isempty(request.sides)
    rawSides = request.sides;
else
    rawSides = {'R', 'L'};
end

if isnumeric(rawSides)
    sides = cell(size(rawSides));
    for i = 1:numel(rawSides)
        if rawSides(i) == 1
            sides{i} = 'R';
        elseif rawSides(i) == 2
            sides{i} = 'L';
        else
            error('mh_vta_normalize_sides:InvalidSide', ...
                'Invalid side index: %d', rawSides(i));
        end
    end
elseif ischar(rawSides) || isstring(rawSides)
    rawSides = cellstr(string(rawSides));
    sides = cell(size(rawSides));
    for i = 1:numel(rawSides)
        sides{i} = normalize_one_side(rawSides{i});
    end
elseif iscell(rawSides)
    sides = cell(size(rawSides));
    for i = 1:numel(rawSides)
        sides{i} = normalize_one_side(rawSides{i});
    end
else
    error('mh_vta_normalize_sides:InvalidSides', ...
        'request.sides must be numeric, string, char, or cell.');
end

sides = unique(sides(:)', 'stable');
end

function side = normalize_one_side(value)
side = upper(char(string(value)));
switch side
    case {'R', 'L'}
        return;
    case '1'
        side = 'R';
    case '2'
        side = 'L';
    otherwise
        error('mh_vta_normalize_sides:InvalidSide', 'Invalid side: %s', side);
end
end
