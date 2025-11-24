function fv = nii2fv(niifile, thr, doSmooth, redFactor)
% fv = nii2fv('STN.nii.gz', 0.3, true, 0.5);
%  niifile   : NIfTI 文件（概率图，MNI 空间）
%  thr       : 概率阈值，比如 0.3、0.5 等
%  doSmooth  : 是否在 volume 上做一点平滑（true/false）
%  redFactor : reducepatch 的压缩比例（0~1，1 表示不减）

if nargin < 3 || isempty(doSmooth),  doSmooth  = true; end
if nargin < 4 || isempty(redFactor), redFactor = 1;    end

%--- 1. 读入 NIfTI ---
V  = spm_vol(niifile);        % 需要 SPM 在 path 上
Y  = spm_read_vols(V);        % Y 为 3D 概率体，double

%--- 2. 可选：轻微平滑，避免网格锯齿 ---
if doSmooth
    Y = smooth3(Y, 'box', 3); % 核大小可以自己改
end

%--- 3. 构建体素坐标网格 ---
% 注意这里用 ndgrid，保证和 SPM 的 (i,j,k) 一致
[II, JJ, KK] = ndgrid(1:V.dim(1), 1:V.dim(2), 1:V.dim(3));

%--- 4. 在概率场上提取等值面 (isosurface) ---
% 这里直接用概率图 Y 和阈值 thr
fv = isosurface(II, JJ, KK, Y, thr);

%--- 5. 把顶点从体素坐标变到 MNI 坐标 ---
% SPM/lead‑DBS 中，世界坐标 = V.mat * [i j k 1]^T
nvert      = size(fv.vertices,1);
verts_hom  = [fv.vertices, ones(nvert,1)];   % N×4
verts_mni  = (V.mat * verts_hom')';          % N×4
fv.vertices = verts_mni(:,1:3);              % 只保留 xyz

%--- 6. 可选：减面 ---
if redFactor < 1
    fv = reducepatch(fv, redFactor);
end

% 此时 fv 就是:
% fv.faces    -> [Nfaces × 3]
% fv.vertices -> [Nverts × 3] (MNI mm)
end