% edit the atlases colormap first
% this script auto replace the atlases.roi.color with the corresponding RGB
% in atlases.colormap

n = length(atlases.names);
% atlases.colormap = color;
% atlases.presets = presets;
for i = 1:n
    atlases.roi{i,1}.color = atlases.colormap(i,:);
    atlases.roi{i,2}.color = atlases.colormap(i,:);
    atlases.roi{i,1}.threshold = atlases.threshold.value;
    atlases.roi{i,2}.threshold = atlases.threshold.value;
end
