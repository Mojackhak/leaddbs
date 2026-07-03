function fig = mh_viz_composition_donut(names, values, varargin)
% Plot a part-whole composition as a donut chart.

parser = inputParser;
parser.FunctionName = 'mh_viz_composition_donut';
parser.addParameter('Title', '', @(x) ischar(x) || isstring(x));
parser.addParameter('CenterText', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputPath', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Position', [100, 100, 760, 480], @(x) isnumeric(x) && numel(x) == 4);
parser.parse(varargin{:});
opts = parser.Results;

names = string(names);
values = double(values(:));
fig = figure('Visible', 'off', 'Color', 'w', 'Position', opts.Position);
ax = axes(fig);
hold(ax, 'on');

if isempty(values) || sum(values, 'omitnan') <= 0
    text(ax, 0.5, 0.5, 'No VTA voxels', 'HorizontalAlignment', 'center', ...
        'FontName', 'Helvetica', 'FontSize', 12);
    axis(ax, 'off');
else
    values(isnan(values) | values < 0) = 0;
    total = sum(values);
    labels = strings(size(names));
    for i = 1:numel(names)
        labels(i) = sprintf('%s %.1f%%', names(i), 100 * values(i) / max(total, eps));
    end
    parts = pie(ax, values, cellstr(labels));
    patches = findobj(parts, 'Type', 'Patch');
    patches = flipud(patches(:));
    colors = mh_viz_palette(names);
    for i = 1:min(numel(patches), size(colors, 1))
        patches(i).FaceColor = colors(i, :);
        patches(i).EdgeColor = 'w';
        patches(i).LineWidth = 1.0;
    end
    textObjects = findobj(parts, 'Type', 'Text');
    for i = 1:numel(textObjects)
        textObjects(i).FontName = 'Helvetica';
        textObjects(i).FontSize = 9;
        textObjects(i).Interpreter = 'none';
    end
    theta = linspace(0, 2*pi, 160);
    patch(ax, 0.45*cos(theta), 0.45*sin(theta), 'w', ...
        'EdgeColor', 'w', 'FaceColor', 'w');
    if strlength(string(opts.CenterText)) > 0
        text(ax, 0, 0, char(string(opts.CenterText)), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
            'FontName', 'Helvetica', 'FontSize', 10, 'FontWeight', 'bold', ...
            'Interpreter', 'none');
    end
    axis(ax, 'equal');
    axis(ax, 'off');
    legend(ax, cellstr(names), 'Location', 'eastoutside', 'Interpreter', 'none', ...
        'Box', 'off');
end

if strlength(string(opts.Title)) > 0
    title(ax, char(string(opts.Title)), 'Interpreter', 'none', 'FontWeight', 'normal');
end

if strlength(string(opts.OutputPath)) > 0
    exportgraphics(fig, char(string(opts.OutputPath)), ...
        'Resolution', 220, 'BackgroundColor', 'white');
end
end
