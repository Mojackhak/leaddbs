function h = ea_heatmap2patch(nii, patchIn, opts)
% EA_HEATMAP2PATCH
%   将 NIfTI 热图映射到已有的 mesh（faces/vertices）或 patch 上。
%
% 用法：
%   h = ea_heatmap2patch('STN_heatmap.nii', sfvStruct);      % sfvStruct.faces / .vertices
%   h = ea_heatmap2patch('STN_heatmap.nii', stnPatchHandle); % 已有 patch 上上色

    %% 1. 处理 opts 与默认值
    if ~exist('opts','var') || isempty(opts)
        opts = struct;
    end
    if ~isfield(opts,'posvisible'),    opts.posvisible   = 1;          end
    if ~isfield(opts,'negvisible'),    opts.negvisible   = 1;          end
    if ~isfield(opts,'heatcolormap'),  opts.heatcolormap = ea_redblue; end

    cmapHeat      = opts.heatcolormap;
    gradientLevel = size(cmapHeat,1);
    defaultColor  = [1 1 1];          % NaN 顶点用白色
    cmap          = [cmapHeat; defaultColor];

    %% 2. 读取 NIfTI 热图
    if ischar(nii) || isstring(nii)
        res = ea_load_nii(nii);
    else
        res = nii;
    end
    if isempty(res) || ~isfield(res,'img') || ~isfield(res,'mat')
        error('ea_heatmap2patch:InvalidNii', ...
              '输入的 NIfTI 为空或格式不正确。');
    end

    % 屏蔽正/负值（可选）
    if ~opts.posvisible
        res.img(res.img > 0) = 0;
    end
    if ~opts.negvisible
        res.img(res.img < 0) = 0;
    end

    %% 3. 构建 mm 空间下的 3D 网格（与 ea_heatmap2surface 同一逻辑）
    bb = res.mat * [ ...
        1,              size(res.img,1); ...
        1,              size(res.img,2); ...
        1,              size(res.img,3); ...
        1,              1               ];

    [X,Y,Z] = meshgrid( ...
        linspace(bb(1,1), bb(1,2), size(res.img,1)), ...
        linspace(bb(2,1), bb(2,2), size(res.img,2)), ...
        linspace(bb(3,1), bb(3,2), size(res.img,3)));

    V = permute(res.img,[2,1,3]);   % 和 ea_heatmap2surface 保持一致

    %% 4. 统一 patch / struct 输入，并检查句柄是否有效
    createNew = false;
    patchHandle = [];

    if isa(patchIn,'matlab.graphics.primitive.Patch')
        % ---- 传进来的是 patch 句柄 ----
        if ~isvalid(patchIn)
            error('ea_heatmap2patch:InvalidPatchHandle', ...
                ['传入的 patch 句柄已失效（可能 figure 被关闭）。\n' ...
                 '建议：传入 faces/vertices 结构，而不是句柄。']);
        end
        patchHandle = patchIn;
        faces       = patchHandle.Faces;
        vertices    = patchHandle.Vertices;

    elseif isstruct(patchIn) && isfield(patchIn,'faces') && isfield(patchIn,'vertices')
        % ---- 传进来的是 mesh 结构 ----
        faces       = patchIn.faces;
        vertices    = patchIn.vertices;
        createNew   = true;

    else
        error('ea_heatmap2patch:BadPatchInput', ...
              '第二个参数必须是 patch 句柄或含 faces / vertices 的结构体。');
    end

    %% 5. 对 mesh 顶点插值热图值并映射 colormap
    ic = isocolors(X, Y, Z, V, vertices);

    if any(~isnan(ic(:)))
        icNorm      = ea_contrast(ic);                   % [-1,1] 或 [0,1] 归一
        CInd        = round(icNorm * gradientLevel + 1);
        CInd(isnan(CInd)) = gradientLevel + 1;           % NaN 顶点 -> defaultColor
        cdata       = cmap(CInd,:);
    else
        % 整个 mesh 都在体积之外，就统一给默认色
        cdata = repmat(defaultColor, size(vertices,1), 1);
    end

    %% 6. 更新或新建 patch
    if createNew
        h = patch('Faces',    faces, ...
                  'Vertices', vertices, ...
                  'FaceVertexCData', cdata, ...
                  'FaceColor',       'interp', ...
                  'EdgeColor',       'none', ...
                  'SpecularStrength',          0.35, ...
                  'SpecularExponent',          30,   ...
                  'SpecularColorReflectance',  0,    ...
                  'AmbientStrength',           0.07, ...
                  'DiffuseStrength',           0.45, ...
                  'FaceLighting',             'gouraud');
    else
        set(patchHandle, ...
            'FaceVertexCData', cdata, ...
            'FaceColor',       'interp', ...
            'EdgeColor',       'none', ...
            'SpecularStrength',          0.35, ...
            'SpecularExponent',          30,   ...
            'SpecularColorReflectance',  0,    ...
            'AmbientStrength',           0.07, ...
            'DiffuseStrength',           0.45, ...
            'FaceLighting',             'gouraud');
        h = patchHandle;
    end

    % 可选：给 patch 标个 Tag
    try
        [~,niiname] = fileparts(res.fname);
        set(h,'Tag',['heatmap_', niiname]);
    end
end