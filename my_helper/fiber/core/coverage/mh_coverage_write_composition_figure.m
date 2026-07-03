function figPath = mh_coverage_write_composition_figure(outputDir, baseLabel, categoryRows, titleText)
% Write a VTA coverage composition donut figure from category summary rows.

figPath = fullfile(char(string(outputDir)), [char(string(baseLabel)), '_desc-vtaCoverage.png']);
names = string(categoryRows(:, 1));
volumes = cell2mat(categoryRows(:, 3));
fig = mh_viz_composition_donut(names, volumes, ...
    'Title', char(string(titleText)), ...
    'CenterText', sprintf('%.0f mm3', sum(volumes)), ...
    'OutputPath', figPath);
close(fig);
end
