function handles = mh_fiber_valid_graphics(handles)
% Return valid graphics handles from arrays, cells, or nested structs.

if nargin < 1 || isempty(handles)
    handles = gobjects(0);
    return;
end

if iscell(handles)
    handles = cellfun(@mh_fiber_valid_graphics, handles, 'UniformOutput', false);
    handles = handles(~cellfun(@isempty, handles));
    if isempty(handles)
        handles = gobjects(0);
        return;
    end
    handles = vertcat(handles{:});
    return;
end

if isstruct(handles)
    fields = fieldnames(handles);
    if isempty(fields)
        handles = gobjects(0);
        return;
    end
    collected = cell(numel(fields), 1);
    for f = 1:numel(fields)
        collected{f} = mh_fiber_valid_graphics(handles.(fields{f}));
    end
    collected = collected(~cellfun(@isempty, collected));
    if isempty(collected)
        handles = gobjects(0);
        return;
    end
    handles = vertcat(collected{:});
    return;
end

try
    handles = handles(isgraphics(handles));
catch
    handles = gobjects(0);
end

handles = handles(:);
end
