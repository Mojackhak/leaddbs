function fig = mh_viz_stacked_share_bar(groupLabels, categoryNames, values, varargin)
% Plot multiple part-whole compositions as 100 percent stacked bars.

parser = inputParser;
parser.FunctionName = 'mh_viz_stacked_share_bar';
parser.addParameter('Title', '', @(x) ischar(x) || isstring(x));
parser.addParameter('OutputPath', '', @(x) ischar(x) || isstring(x));
parser.addParameter('Position', [100, 100, 900, 460], @(x) isnumeric(x) && numel(x) == 4);
parser.addParameter('LabelMinimumShare', 4, @(x) isnumeric(x) && isscalar(x) && x >= 0);
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
label_stacked_shares(ax, shares, colors, double(opts.LabelMinimumShare));
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

function label_stacked_shares(ax, shares, colors, minimumShare)
cumulative = cumsum(shares, 2);
starts = cumulative - shares;
for row = 1:size(shares, 1)
    for col = 1:size(shares, 2)
        share = shares(row, col);
        if share < minimumShare || share <= 0
            continue;
        end
        y = starts(row, col) + share / 2;
        text(ax, row, y, sprintf('%.0f%%', share), ...
            'HorizontalAlignment', 'center', ...
            'VerticalAlignment', 'middle', ...
            'FontName', 'Helvetica', ...
            'FontSize', 8, ...
            'FontWeight', 'bold', ...
            'Color', contrast_text_color(colors(col, :)), ...
            'Clipping', 'on');
    end
end
end

function color = contrast_text_color(rgb)
if numel(rgb) < 3
    color = [0.1, 0.1, 0.1];
    return;
end
luminance = 0.2126 * rgb(1) + 0.7152 * rgb(2) + 0.0722 * rgb(3);
if luminance < 0.45
    color = [1, 1, 1];
else
    color = [0.1, 0.1, 0.1];
end
end
