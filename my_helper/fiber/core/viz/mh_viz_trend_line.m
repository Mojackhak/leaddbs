function fig = mh_viz_trend_line(x, y, varargin)
% Plot one or more threshold/volume trend lines.

parser = inputParser;
parser.FunctionName = 'mh_viz_trend_line';
parser.addParameter('Group', strings(size(x)), @(v) ischar(v) || isstring(v) || iscell(v));
parser.addParameter('Title', '', @(x) ischar(x) || isstring(x));
parser.addParameter('XLabel', 'X', @(x) ischar(x) || isstring(x));
parser.addParameter('YLabel', 'Y', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputPath', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Position', [100, 100, 640, 430], @(x) isnumeric(x) && numel(x) == 4);
parser.parse(varargin{:});
opts = parser.Results;

x = double(x(:));
y = double(y(:));
group = string(opts.Group);
if isscalar(group) && numel(x) > 1
    group = repmat(group, size(x));
else
    group = group(:);
end

fig = figure('Visible', 'off', 'Color', 'w', 'Position', opts.Position);
ax = axes(fig);
hold(ax, 'on');
groups = unique(group, 'stable');
colors = mh_viz_palette(groups);
for i = 1:numel(groups)
    one = group == groups(i);
    [xOne, order] = sort(x(one));
    yOne = y(one);
    yOne = yOne(order);
    plot(ax, xOne, yOne, '-o', 'LineWidth', 1.6, 'MarkerSize', 5, ...
        'Color', colors(i, :), 'DisplayName', groups(i));
end
hold(ax, 'off');
xlabel(ax, char(string(opts.XLabel)));
ylabel(ax, char(string(opts.YLabel)));
if strlength(string(opts.Title)) > 0
    title(ax, char(string(opts.Title)), 'Interpreter', 'none', 'FontWeight', 'normal');
end
if numel(groups) > 1
    legend(ax, 'Location', 'best', 'Interpreter', 'none', 'Box', 'off');
end
mh_viz_apply_style(ax);

if strlength(string(opts.OutputPath)) > 0
    exportgraphics(fig, char(string(opts.OutputPath)), ...
        'Resolution', 220, 'BackgroundColor', 'white');
end
end
