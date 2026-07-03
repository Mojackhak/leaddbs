function mh_viz_apply_style(ax)
% Apply a shared quiet figure style.

if nargin < 1 || isempty(ax)
    ax = gca;
end
set(ax, 'FontName', 'Helvetica', 'FontSize', 10, 'LineWidth', 0.8, ...
    'Box', 'off', 'Color', 'w');
grid(ax, 'on');
ax.GridAlpha = 0.18;
ax.MinorGridAlpha = 0.10;
end
