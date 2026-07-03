function fig = mh_viz_stacked_share_bar(groupLabels, categoryNames, values, varargin)
% Plot multiple part-whole compositions as 100 percent stacked bars.

parser = inputParser;
parser.FunctionName = 'mh_viz_stacked_share_bar';
parser.addParameter('Title', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputPath', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Position', [100, 100, 900, 460], @(x) isnumeric(x) && numel(x) == 4);
parser.parse(varargin{:});
opts = parser.Results;

groupLabels = string(groupLabels);
categoryNames = string(categoryNames);
values = double(values);
rowSums = sum(values, 2, 'omitnan');
shares = zeros(size(values));
valid = rowSums > 0;
shares(valid, :) = values(valid, :) ./ rowSums(valid) .* 100;

fig = figure('Visible', 'off', 'Color', 'w', 'Position', opts.Position);
ax = axes(fig);
b = bar(ax, categorical(groupLabels), shares, 'stacked');
colors = mh_viz_palette(categoryNames);
for i = 1:min(numel(b), size(colors, 1))
    b(i).FaceColor = colors(i, :);
    b(i).EdgeColor = 'w';
end
ylabel(ax, 'Share of VTA (%)');
ylim(ax, [0, 100]);
if strlength(string(opts.Title)) > 0
    title(ax, char(string(opts.Title)), 'Interpreter', 'none', 'FontWeight', 'normal');
end
legend(ax, cellstr(categoryNames), 'Location', 'eastoutside', 'Interpreter', 'none', ...
    'Box', 'off');
mh_viz_apply_style(ax);

if strlength(string(opts.OutputPath)) > 0
    exportgraphics(fig, char(string(opts.OutputPath)), ...
        'Resolution', 220, 'BackgroundColor', 'white');
end
end
