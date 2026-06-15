function [fv, sfv, h] = vol2patch(niftiFile, opts)
% VOL2PATCH  将体积图集转为三维表面 patch（参考 Lead-DBS ea_roi.update_roi）
%
%   [fv,sfv,h] = vol2patch('STN.nii.gz');
%
% INPUTS:
%   niftiFile : NIfTI 文件路径或 ea_load_nii 返回的结构
%   opts.threshold   : 阈值（默认自动）
%   opts.smooth      : 平滑程度，默认 1
%   opts.hullsimplify: 简化程度，<1 表比例，>1 表目标面数
%
% OUTPUTS:
%   fv  : 原始 surface (faces/vertices)
%   sfv : 平滑/简化后的 surface
%   h   : patch 句柄

    arguments
        niftiFile
        opts.threshold   = []
        opts.smooth      = 1
        opts.hullsimplify = []
    end

    % ----- 1. 读取 NIfTI -----
    if ischar(niftiFile) || isstring(niftiFile)
        nii = ea_load_nii(niftiFile);
    else
        nii = niftiFile;
    end
    img = nii.img;

    % 处理 NaN / Inf
    img(img==0)    = nan;
    img(isinf(img)) = nan;
    validVox       = ~isnan(img(:));
    maxVal         = max(img(validVox));
    minVal         = min(img(validVox));

    % ----- 2. 自动/指定阈值 -----
    if isempty(opts.threshold)
        if maxVal == minVal
            thr = maxVal/2;
        else
            thr = maxVal - 0.5*(maxVal - minVal);
        end
    else
        thr = opts.threshold;
    end

    img(isnan(img)) = 0;

    % ----- 3. 构建体素网格并转换到 mm 空间 -----
    img_size = size(img);
    [X_vox, Y_vox, Z_vox] = meshgrid(1:img_size(1), 1:img_size(2), 1:img_size(3));
    XYZ_mm = ea_vox2mm([X_vox(:), Y_vox(:), Z_vox(:)], nii.mat);

    % ✅ 这里用 size(X_vox) 而不是 size(img)
    X_mm = reshape(XYZ_mm(:,1), size(X_vox));
    Y_mm = reshape(XYZ_mm(:,2), size(Y_vox));
    Z_mm = reshape(XYZ_mm(:,3), size(Z_vox));

    % ----- 4. isosurface + isocaps 生成表面 -----
    V = permute(img, [2,1,3]);   % 注意: 与 X_mm/Y_mm/Z_mm 的尺寸相匹配
    fvIso = isosurface(X_mm, Y_mm, Z_mm, V, thr);
    fvCap = isocaps(  X_mm, Y_mm, Z_mm, V, thr);

    fv.faces    = [fvIso.faces; fvCap.faces + size(fvIso.vertices,1)];
    fv.vertices = [fvIso.vertices; fvCap.vertices];

    % ----- 5. 平滑 -----
    if ~isempty(opts.smooth) && opts.smooth > 0 ...
            && ~isempty(fv.vertices) && ~isempty(fv.faces)
        sfv = ea_smoothpatch(fv, 1, opts.smooth);
    else
        sfv = fv;
    end

    % ----- 6. 简化 -----
    if ~isempty(opts.hullsimplify) && ~isempty(sfv.faces)
        if opts.hullsimplify < 1 && opts.hullsimplify > 0
            % 比例简化
            sfv = reducepatch(sfv, opts.hullsimplify);
        elseif opts.hullsimplify >= 1
            % 目标面数
            simplify = opts.hullsimplify / length(sfv.faces);
            sfv      = reducepatch(sfv, simplify);
        end
    end

    % ----- 7. 画 patch -----
    if nargout > 2
        h = patch('Faces', sfv.faces, ...
                  'Vertices', sfv.vertices, ...
                  'FaceColor', [0.8 0.8 0.8], ...
                  'EdgeColor', 'none', ...
                  'FaceLighting','gouraud', ...
                  'SpecularStrength',0.3, ...
                  'DiffuseStrength',0.4);
    else
        h = [];
    end
end