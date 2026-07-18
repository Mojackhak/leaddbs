function args = struct2namevalue(s)
%DBSLFP_STRUCT2NAMEVALUE Convert struct to name-value cell array.
%
% args = struct2namevalue(s)
%
% Example:
%   s = struct('Alpha', 1, 'Colormap', 'vik');
%   args -> {'Alpha', 1, 'Colormap', 'vik'}

    f = fieldnames(s);
    args = cell(1, 2 * numel(f));
    for i = 1:numel(f)
        args{2*i-1} = f{i};
        args{2*i} = s.(f{i});
    end
end
