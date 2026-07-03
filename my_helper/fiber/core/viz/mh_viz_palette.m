function colors = mh_viz_palette(names)
% Return stable RGB colors for region/category names.

names = string(names);
colors = zeros(numel(names), 3);
fallback = [ ...
    0.1216, 0.4667, 0.7059; ...
    1.0000, 0.4980, 0.0549; ...
    0.1725, 0.6275, 0.1725; ...
    0.8392, 0.1529, 0.1569; ...
    0.5804, 0.4039, 0.7412; ...
    0.5490, 0.3373, 0.2941; ...
    0.8902, 0.4667, 0.7608; ...
    0.4980, 0.4980, 0.4980; ...
    0.7373, 0.7412, 0.1333; ...
    0.0902, 0.7451, 0.8118];

for i = 1:numel(names)
    key = char(names(i));
    switch key
        case {'STN', 'STN_only'}
            color = [0.1216, 0.4667, 0.7059];
        case {'SNr', 'SNr_only'}
            color = [0.8902, 0.4667, 0.1255];
        case {'STN_SNr'}
            color = [0.1725, 0.6275, 0.1725];
        case {'Outside'}
            color = [0.6800, 0.6800, 0.6800];
        case {'NAc'}
            color = [0.5098, 0.8196, 0.2627];
        case {'ALIC'}
            color = [0.1882, 0.4392, 0.7176];
        case {'VTA'}
            color = [0.8000, 0.1000, 0.1000];
        otherwise
            color = fallback(mod(i - 1, size(fallback, 1)) + 1, :);
    end
    colors(i, :) = color;
end
end
