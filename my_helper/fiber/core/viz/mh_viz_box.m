function fig = mh_viz_box(groupLabels, values, varargin)
% Plot grouped distributions with a shared boxchart style.

parser = inputParser;
parser.FunctionName = 'mh_viz_box';
parser.addParameter('Title', '', @(x) ischar(x) || isstring(x));
parser.addParameter('YLabel', 'Value', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputPath', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Position', [100, 100, 920, 460], @(x) isnumeric(x) && numel(x) == 4);
parser.parse(varargin{:});
opts = parser.Results;

fig = figure('Visible', 'off', 'Color', 'w', 'Position', opts.Position);
ax = axes(fig);
boxchart(ax, categorical(string(groupLabels)), double(values));
ylabel(ax, char(string(opts.YLabel)));
if strlength(string(opts.Title)) > 0
    title(ax, char(string(opts.Title)), 'Interpreter', 'none', 'FontWeight', 'normal');
end
mh_viz_apply_style(ax);

if strlength(string(opts.OutputPath)) > 0
    exportgraphics(fig, char(string(opts.OutputPath)), ...
        'Resolution', 220, 'BackgroundColor', 'white');
end
end
