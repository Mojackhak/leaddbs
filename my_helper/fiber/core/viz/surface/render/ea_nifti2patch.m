function patchObj = ea_nifti2patch(niftiInput, varargin)
%EA_NIFTI2PATCH Convert a NIfTI volume into a colored surface patch (mesh).
%
%   patchObj = EA_NIFTI2PATCH(niftiInput)
%   patchObj = EA_NIFTI2PATCH(niftiInput, 'Name', value, ...)
%
% Overview
%   This function produces a triangulated surface mesh and maps scalar voxel
%   values onto that surface as FaceVertexCData for color rendering.
%
%   The key idea is to decouple:
%     - Geometry (where the surface is)
%     - Color (which values are painted on the surface)
%
% Geometry source
%   By default, the surface is extracted from the same NIfTI volume that is
%   also used for coloring. You can optionally provide a *template* NIfTI
%   (e.g., an atlas probability map, 0..1) to define the surface boundary.
%   In that case, colors are still sampled from the original niftiInput.
%
% Surface extraction modes
%   'mask' (default):
%     1) Build a binary mask by thresholding the geometry volume:
%           mask = (Ygeom > MaskThreshold)
%     2) Extract the boundary using isosurface(mask, MaskIsovalue).
%
%   'iso' (legacy):
%     Extract an isosurface directly from the geometry volume at IsoValue.
%
% Smoothing
%   Two optional smoothing stages are supported:
%     1) Volume smoothing (Gaussian) on the GEOMETRY volume prior to surface
%        extraction (useful for binary masks or noisy probability maps).
%     2) Mesh smoothing (Taubin/Laplacian) on the extracted surface.
%
% Output
%   patchObj is a struct intended to be visualized with EA_PLOT_PATCH_LEADDBS.
%   Key fields:
%       patchObj.faces              : F-by-3 face indices
%       patchObj.vertices           : V-by-3 vertices in world (mm)
%       patchObj.facevertexcdata    : V-by-1 scalar values for colormapping
%       patchObj.alpha              : transparency (0..1)
%       patchObj.colormap           : Nx3 colormap (default: viridis)
%       patchObj.clim               : 1x2 color limits
%       patchObj.surface_mode       : 'mask' or 'iso'
%       patchObj.geometry_source    : 'data' or 'template'
%       patchObj.mask_threshold     : threshold used in mask mode (if any)
%       patchObj.surface_level      : 0.5 (mask mode) or IsoValue (iso mode)
%
% Name-Value pairs (optional)
%   Geometry / template
%   'TemplateNifti'        : geometry source NIfTI (path / spm_vol / nifti).
%                            Default: [] (use niftiInput for geometry).
%
%   Surface extraction
%   'SurfaceMode'          : 'mask' (default) or 'iso'
%   'MaskThreshold'        : numeric scalar, [] or 'auto'. Default: 0
%                            Used in mask mode: mask = (Ygeom > MaskThreshold)
%   'MaskIsovalue'         : scalar in (0,1). Default: 0.5
%                            Used in mask mode for isosurface(mask, MaskIsovalue)
%   'IsoValue'             : scalar or []. Used only in iso mode.
%                            If empty, an automatic value is selected.
%
%   Smoothing
%   'VolumeSmoothingSigmaMm' : Gaussian sigma in mm applied to the GEOMETRY
%                              volume prior to surface extraction. Default: 0
%   'SurfaceSmoothingIters'  : integer >=0. Mesh smoothing iterations. Default: 0
%   'SurfaceSmoothingMethod' : 'taubin' (default) or 'laplacian'
%   'SurfaceSmoothingLambda' : Taubin/Laplacian lambda. Default: 0.5
%   'SurfaceSmoothingMu'     : Taubin mu (negative). Default: -0.53
%
%   Color sampling
%   'ColorSampling'        : 'onSurface', 'insideOnly', or 'inside'.
%                            Default: 'insideOnly'
%                            - 'onSurface' samples niftiInput values at the surface.
%                            - 'insideOnly' samples both normal-offset sides
%                              and keeps the side that is most consistent with
%                              the geometry mask interior.
%                            - 'inside' samples on both sides along the surface normal
%                              and keeps the sample with larger absolute value.
%   'OnSurfaceMissingFallback' : 'nearestFinite', 'nearest', or 'none'.
%                            Default: 'nearestFinite'. Used only when
%                            ColorSampling='onSurface' and the direct linear
%                            surface sample is missing.
%   'OnSurfaceFallbackRadiusVox' : nonnegative integer search radius for the
%                            nearest-finite fallback. Default: 1.
%   'SampleDepthMm'        : scalar >= 0. Default: 1.0
%   'SampleDepthVox'       : scalar >= 0. If provided, overrides SampleDepthMm.
%
%   Rendering / misc
%   'Alpha'                : scalar in [0, 1]. Default: 0.6
%   'Colormap'             : Nx3 colormap OR a string name. Default: 'viridis'
%                            Supported names include: 'viridis', 'vik'
%   'CLim'                 : 1x2. Default: [min(cdata) max(cdata)]
%   'CLimMode'             : 'auto' (default) or 'symmetric'. If 'symmetric',
%                            sets CLim = [-A A] where A = max(abs(cdata)).
%   'SymmetricCLimA'       : scalar > 0. If provided and CLimMode='symmetric',
%                            uses CLim = [-A A] with this A.
%   'GeometryUpsampleFactor': integer >=1. Default: 1. If >1, upsamples the
%                            geometry grid before surface extraction to increase
%                            mesh resolution.
%   'PermuteXY'            : logical. Default: true
%                            Recommended for SPM/Lead-DBS voxel conventions.
%   'ReduceFactor'         : scalar in (0, 1]. Default: 1 (no reduction)
%
% Requirements
%   - SPM12 is strongly recommended (Lead-DBS depends on it).
%
% See also: EA_PLOT_PATCH_LEADDBS, EA_COLORMAP_VIRIDIS, EA_READ_NIFTI_ANY,
%           isosurface, reducepatch, interp3

    ip = inputParser;
    ip.FunctionName = mfilename;

    addParameter(ip, 'TemplateNifti', [], @(x) isempty(x) || ischar(x) || (isstring(x) && isscalar(x)) || isstruct(x) || (exist('nifti','class')==8 && isa(x,'nifti')));

    addParameter(ip, 'SurfaceMode', 'mask', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'MaskThreshold', 0, @(x) isempty(x) || (isnumeric(x) && isscalar(x)) || ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(ip, 'MaskIsovalue', 0.5, @(x) isnumeric(x) && isscalar(x) && x > 0 && x < 1);

    addParameter(ip, 'IsoValue', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));

    addParameter(ip, 'VolumeSmoothingSigmaMm', 0, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    addParameter(ip, 'SurfaceSmoothingIters', 0, @(x) isnumeric(x) && isscalar(x) && x >= 0 && mod(x,1)==0);
    addParameter(ip, 'SurfaceSmoothingMethod', 'taubin', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'SurfaceSmoothingLambda', 0.5, @(x) isnumeric(x) && isscalar(x));
    addParameter(ip, 'SurfaceSmoothingMu', -0.53, @(x) isnumeric(x) && isscalar(x));

    addParameter(ip, 'ColorSampling', 'insideOnly', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'OnSurfaceMissingFallback', 'nearestFinite', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'OnSurfaceFallbackRadiusVox', 1, @(x) isnumeric(x) && isscalar(x) && x >= 0 && mod(x,1)==0);
    addParameter(ip, 'SampleDepthMm', 1.0, @(x) isnumeric(x) && isscalar(x) && x >= 0);
    addParameter(ip, 'SampleDepthVox', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x >= 0));

    addParameter(ip, 'Alpha', 0.6, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'Colormap', [], @(x) isempty(x) || (isnumeric(x) && size(x,2) == 3) || ischar(x) || (isstring(x) && isscalar(x)));
    addParameter(ip, 'CLim', [], @(x) isempty(x) || (isnumeric(x) && numel(x) == 2));
    addParameter(ip, 'CLimMode', 'auto', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'SymmetricCLimA', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x) && x > 0));
    addParameter(ip, 'GeometryUpsampleFactor', 1, @(x) isnumeric(x) && isscalar(x) && x >= 1 && mod(x,1)==0);

    addParameter(ip, 'PermuteXY', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ReduceFactor', 1, @(x) isnumeric(x) && isscalar(x) && x > 0 && x <= 1);

    parse(ip, varargin{:});
    p = ip.Results;

    % Read the DATA volume (used for coloring).
    [Ydata, Mdata, metaData] = ea_read_nifti_any(niftiInput);
    if ndims(Ydata) ~= 3
        error('EA_NIFTI2PATCH:Not3D', 'The input (data) volume must be 3D.');
    end

    % Read the GEOMETRY volume (used for surface extraction).
    if isempty(p.TemplateNifti)
        Ygeom = Ydata;
        Mgeom = Mdata;
        metaGeom = metaData;
        geomSource = 'data';
    else
        [Ygeom, Mgeom, metaGeom] = ea_read_nifti_any(p.TemplateNifti);
        if ndims(Ygeom) ~= 3
            error('EA_NIFTI2PATCH:TemplateNot3D', 'The template/geometry volume must be 3D.');
        end
        geomSource = 'template';
    end

    % Resolve colormap (accepts Nx3 arrays or a string name).
    [p.Colormap, cmapName] = local_resolve_colormap(p.Colormap, 256);


    % Permute X/Y to align MATLAB isosurface/interp3 with SPM voxel conventions.
    if p.PermuteXY
        Ydata_p = permute(Ydata, [2 1 3]);
        Ygeom_p = permute(Ygeom, [2 1 3]);
    else
        Ydata_p = Ydata;
        Ygeom_p = Ygeom;
        warning('EA_NIFTI2PATCH:PermuteXYOff', ...
            ['PermuteXY is set to false. Ensure you understand how voxel axes ' ...
             'map to world space in your environment.']);
    end

    % Optional Gaussian smoothing on the GEOMETRY volume (prior to extraction).
    if p.VolumeSmoothingSigmaMm > 0
        voxSizeGeom = local_vox_size_mm(Mgeom);
        if p.PermuteXY
            voxSizeGeom = voxSizeGeom([2 1 3]);
        end
        sigmaVox = p.VolumeSmoothingSigmaMm ./ max(voxSizeGeom, eps);
        Ygeom_p_use = local_gauss_smooth3_nan(Ygeom_p, sigmaVox);
    else
        Ygeom_p_use = Ygeom_p;
    end

    % --- Surface extraction ---
    surfaceMode = lower(strtrim(char(p.SurfaceMode)));
    maskThr = [];
    surfaceLevel = [];
    maskField = [];
    upFactor = round(p.GeometryUpsampleFactor);
    MgeomSurf = Mgeom;

    switch surfaceMode
        case 'mask'
            maskThr = local_parse_mask_threshold(p.MaskThreshold, Ygeom);

            % Build binary mask (inside = 1, outside = 0).
            mask = (Ygeom_p_use > maskThr) & isfinite(Ygeom_p_use);

            % Optional geometry upsampling to increase surface resolution.
            % This can noticeably reduce jagged edges in boundaries derived
            % from voxel data (at the cost of more faces/vertices).
            if upFactor > 1
                [maskField, MgeomSurf] = local_upsample_volume(single(mask), Mgeom, upFactor);
            else
                maskField = single(mask);
            end

            % Extract boundary surface from the mask.
            fv = isosurface(maskField, p.MaskIsovalue);
            if isempty(fv.vertices) || isempty(fv.faces)
                error('EA_NIFTI2PATCH:EmptySurface', ...
                    ['Mask is empty or does not form a surface at the given threshold. ' ...
                     'Try a lower MaskThreshold or use ''MaskThreshold'',''auto''.']);
            end

            % Optional mesh reduction for faster rendering.
            if p.ReduceFactor < 1
                fv = reducepatch(fv, p.ReduceFactor);
            end

            v_vox_geom = fv.vertices;
            faces = fv.faces;
            surfaceLevel = p.MaskIsovalue;

        case 'iso'
            iso = p.IsoValue;
            if isempty(iso)
                iso = local_auto_isovalue(Ygeom);
            end

            % Optional geometry upsampling to increase surface resolution.
            Yfield = Ygeom_p_use;
            if upFactor > 1
                [Yfield, MgeomSurf] = local_upsample_volume(single(Yfield), Mgeom, upFactor);
            end

            fv = isosurface(Yfield, iso);
            if isempty(fv.vertices) || isempty(fv.faces)
                error('EA_NIFTI2PATCH:EmptySurface', ...
                    'isosurface returned an empty mesh. Try a different IsoValue.');
            end

            if p.ReduceFactor < 1
                fv = reducepatch(fv, p.ReduceFactor);
            end

            v_vox_geom = fv.vertices;
            faces = fv.faces;
            surfaceLevel = iso;

        otherwise
            error('EA_NIFTI2PATCH:BadSurfaceMode', ...
                'Unknown SurfaceMode: %s (use ''mask'' or ''iso'').', p.SurfaceMode);
    end

% Convert geometry vertices to world coordinates (mm).
    v_world = [v_vox_geom, ones(size(v_vox_geom,1), 1)] * MgeomSurf';
    v_world = v_world(:, 1:3);

    % Optional mesh smoothing in world space.
    if p.SurfaceSmoothingIters > 0
        method = lower(strtrim(char(p.SurfaceSmoothingMethod)));
        v_world = local_smooth_mesh(v_world, faces, p.SurfaceSmoothingIters, method, p.SurfaceSmoothingLambda, p.SurfaceSmoothingMu);
    end

    % --- Color sampling from DATA volume ---
    colorSampling = lower(strtrim(char(p.ColorSampling)));
    onSurfaceFallbackStats = local_empty_on_surface_fallback_stats( ...
        p.OnSurfaceMissingFallback, p.OnSurfaceFallbackRadiusVox);
    insideOnlyStats = local_empty_inside_only_stats();

    % Convert sample depth to mm (use DATA voxel size if user provided vox units).
    stepMm = p.SampleDepthMm;
    if ~isempty(p.SampleDepthVox)
        voxSizeData = local_vox_size_mm(Mdata);
        stepMm = p.SampleDepthVox * mean(abs(voxSizeData));
    end

    switch colorSampling
        case 'onsurface'
            c = local_sample_data_at_world(Ydata_p, Mdata, v_world, 'linear');
            [c, onSurfaceFallbackStats] = local_apply_on_surface_missing_fallback( ...
                Ydata_p, Mdata, v_world, c, ...
                p.OnSurfaceMissingFallback, p.OnSurfaceFallbackRadiusVox);

        case {'insideonly','inside_only','inner','interior'}
            if stepMm <= 0
                c = local_sample_data_at_world(Ydata_p, Mdata, v_world, 'linear');
                insideOnlyStats = local_inside_only_stats_from_direct_sample(c);
            else
                n_world = local_vertex_normals(v_world, faces);
                n_world = local_normalize_rows(n_world);

                vPlus  = v_world + n_world * stepMm;
                vMinus = v_world - n_world * stepMm;

                cPlus  = local_sample_data_at_world(Ydata_p, Mdata, vPlus, 'linear');
                cMinus = local_sample_data_at_world(Ydata_p, Mdata, vMinus, 'linear');
                [mPlus, mMinus] = local_sample_geometry_mask_scores( ...
                    surfaceMode, maskField, MgeomSurf, vPlus, vMinus);

                [c, insideOnlyStats] = local_select_inside_only_samples( ...
                    cPlus, cMinus, mPlus, mMinus, surfaceLevel);
            end

        case 'inside'
            if stepMm <= 0
                c = local_sample_data_at_world(Ydata_p, Mdata, v_world, 'linear');
            else
                n_world = local_vertex_normals(v_world, faces);
                n_world = local_normalize_rows(n_world);

                vPlus  = v_world + n_world * stepMm;
                vMinus = v_world - n_world * stepMm;

                cPlus  = local_sample_data_at_world(Ydata_p, Mdata, vPlus, 'linear');
                cMinus = local_sample_data_at_world(Ydata_p, Mdata, vMinus, 'linear');

                % Robust selection: prefer finite samples; if both are finite,
                % pick the one with larger absolute value.
                c = cPlus;
                plusFinite = isfinite(cPlus);
                minusFinite = isfinite(cMinus);

                % If plus is missing but minus is valid, take minus.
                takeMinus = ~plusFinite & minusFinite;
                c(takeMinus) = cMinus(takeMinus);

                % If both are valid, choose by larger abs value.
                bothFinite = plusFinite & minusFinite;
                takeMinus = bothFinite & (abs(cMinus) > abs(cPlus));
                c(takeMinus) = cMinus(takeMinus);

                % If both missing, the value remains NaN.
            end

        otherwise
            error('EA_NIFTI2PATCH:BadColorSampling', ...
                'Unknown ColorSampling: %s (use ''onSurface'', ''insideOnly'', or ''inside'').', p.ColorSampling);
    end

    % Keep the raw sampled values (may contain NaNs) so we can track
    % vertices/faces that could not be mapped back to the DATA volume.
    c_raw = c;
    missingVertexMask = ~isfinite(c_raw);

    % Replace NaNs by a robust fill value (e.g., outside-volume samples).
    c = c_raw;
    cvalid = c(isfinite(c));
    if isempty(cvalid)
        fillVal = 0;
    else
        fillVal = median(cvalid);
    end
    c(~isfinite(c)) = fillVal;

    % Determine default CLim if needed.
    if isempty(p.CLim)
        climMode = lower(strtrim(char(p.CLimMode)));

        % Use the raw (unfilled) samples to avoid missing-data fill values
        % influencing automatic color limits.
        cvalid = c_raw(isfinite(c_raw));
        if isempty(cvalid)
            cvalid = c(isfinite(c));
        end
        if isempty(cvalid)
            cvalid = 0;
        end

        switch climMode
            case {'symmetric','sym','centered','center'}
                if ~isempty(p.SymmetricCLimA)
                    A = abs(double(p.SymmetricCLimA));
                else
                    A = max(abs(double(cvalid)));
                end
                if ~isfinite(A) || A == 0
                    A = 1;
                end
                p.CLim = [-A A];

            otherwise
                p.CLim = [min(cvalid) max(cvalid)];
                if p.CLim(1) == p.CLim(2)
                    p.CLim = p.CLim + [-1 1] * eps(p.CLim(1) + 1);
                end
        end
    end

    % Package output.

    patchObj = struct();
    patchObj.faces = faces;
    patchObj.vertices = v_world;
    patchObj.facevertexcdata = c;

    % Missing-data bookkeeping (useful when geometry comes from a template).
    patchObj.facevertexcdata_raw = c_raw;           % may contain NaNs
    patchObj.missing_vertex_mask = missingVertexMask;
    patchObj.missing_fill_value  = fillVal;
    patchObj.missing_vertex_count = sum(missingVertexMask);

    patchObj.alpha = p.Alpha;
    patchObj.colormap = p.Colormap;
    patchObj.colormap_name = cmapName;
    patchObj.clim = p.CLim;

    patchObj.clim_mode = lower(strtrim(char(p.CLimMode)));

    patchObj.surface_mode = surfaceMode;
    patchObj.surface_level = surfaceLevel;
    patchObj.geometry_source = geomSource;

    if strcmp(surfaceMode, 'mask')
        patchObj.mask_threshold = maskThr;
        patchObj.mask_isovalue = p.MaskIsovalue;
    else
        patchObj.mask_threshold = [];
        patchObj.mask_isovalue = [];
    end

    % Provenance and affines (helpful for debugging/reproducibility).
    patchObj.affine = Mgeom;              % kept for backward compatibility
    patchObj.affine_geometry = Mgeom;
    patchObj.affine_geometry_surface = MgeomSurf;
    patchObj.geometry_upsample_factor = upFactor;
    patchObj.affine_data = Mdata;

    patchObj.meta = metaData;             % kept for backward compatibility
    patchObj.meta_data = metaData;
    patchObj.meta_geometry = metaGeom;

    patchObj.vertices_vox_geometry = v_vox_geom;
    patchObj.color_sampling = colorSampling;
    patchObj.sample_depth_mm = stepMm;
    patchObj.on_surface_missing_fallback = onSurfaceFallbackStats;
    patchObj.inside_only_sampling = insideOnlyStats;
end

% -------------------------------------------------------------------------
% Helper functions
% -------------------------------------------------------------------------

function thr = local_parse_mask_threshold(maskThrIn, Y)
%LOCAL_PARSE_MASK_THRESHOLD Parse a user-supplied mask threshold.
%
% Accepted inputs:
%   - numeric scalar: used directly
%   - [] or 'auto'  : automatic heuristic

    if isempty(maskThrIn)
        thr = local_auto_mask_threshold(Y);
        return;
    end

    if ischar(maskThrIn) || (isstring(maskThrIn) && isscalar(maskThrIn))
        token = lower(strtrim(char(maskThrIn)));
        if strcmp(token, 'auto')
            thr = local_auto_mask_threshold(Y);
            return;
        end
        error('EA_NIFTI2PATCH:BadMaskThreshold', ...
            'MaskThreshold must be numeric, [], or ''auto''.');
    end

    if isnumeric(maskThrIn) && isscalar(maskThrIn)
        thr = double(maskThrIn);
        return;
    end

    error('EA_NIFTI2PATCH:BadMaskThreshold', ...
        'MaskThreshold must be numeric, [], or ''auto''.');
end

function thr = local_auto_mask_threshold(Y)
%LOCAL_AUTO_MASK_THRESHOLD Heuristic threshold for building a binary mask.
%
% Goal:
%   Pick a threshold that behaves like "background == 0" maps, while being
%   more robust against tiny positive interpolation noise.
%
% Strategy:
%   - If data spans negative and positive values: thr = 0
%   - Else, if zeros and non-zeros exist: thr = 0.5 * min(abs(nonzero))
%     (i.e., safely above tiny numerical noise, below real signal)
%   - Else: thr = 5% above the minimum value

    v = Y(:);
    v = v(isfinite(v));
    if isempty(v)
        thr = 0;
        return;
    end

    vmin = min(v);
    vmax = max(v);

    if vmin < 0 && vmax > 0
        thr = 0;
        return;
    end

    hasZero = any(v == 0);
    v_nz = v(v ~= 0);
    if hasZero && ~isempty(v_nz)
        thr = 0.5 * min(abs(v_nz));
        if vmax < 0
            thr = -thr;
        end
        return;
    end

    % Fallback when the background is not exactly zero.
    thr = vmin + 0.05 * (vmax - vmin);
end

function iso = local_auto_isovalue(Y)
%LOCAL_AUTO_ISOVALUE Heuristic iso-value selection for "iso" mode.
%
% Strategy:
%   - If data spans negative and positive values: iso = 0
%   - Else, if there are zeros and non-zeros: iso = 0.5 * min(abs(nonzero))
%   - Else: iso = midpoint of min/max

    v = Y(:);
    v = v(isfinite(v));
    if isempty(v)
        iso = 0;
        return;
    end

    vmin = min(v);
    vmax = max(v);

    if vmin < 0 && vmax > 0
        iso = 0;
        return;
    end

    hasZero = any(v == 0);
    v_nz = v(v ~= 0);

    if hasZero && ~isempty(v_nz)
        iso = 0.5 * min(abs(v_nz));
        if vmax < 0
            iso = -iso;
        end
        return;
    end

    iso = 0.5 * (vmin + vmax);
end

function voxSize = local_vox_size_mm(M)
%LOCAL_VOX_SIZE_MM Approximate voxel sizes (mm) from an affine matrix.
%
% This returns the column norms of the 3x3 submatrix.

    A = M(1:3, 1:3);
    voxSize = sqrt(sum(A.^2, 1));
    voxSize = abs(voxSize(:))';
    voxSize(~isfinite(voxSize) | voxSize == 0) = 1;
end

function Ysm = local_gauss_smooth3_nan(Y, sigmaVox)
%LOCAL_GAUSS_SMOOTH3_NAN Simple separable 3D Gaussian smoothing with NaN handling.
%
% Inputs
%   Y        : 3D array (double recommended)
%   sigmaVox : 1x3 (or scalar) Gaussian sigma in voxel units
%
% Notes
%   - This function avoids toolbox dependencies.
%   - NaNs are treated as missing values and do not bleed into valid regions.

    if isscalar(sigmaVox)
        sigmaVox = repmat(double(sigmaVox), 1, 3);
    else
        sigmaVox = double(sigmaVox(:))';
        if numel(sigmaVox) ~= 3
            error('sigmaVox must be a scalar or a 1x3 vector.');
        end
    end

    Ysm = double(Y);

    finiteMask = isfinite(Ysm);
    Ysm(~finiteMask) = 0;
    W = double(finiteMask);

    for dim = 1:3
        s = sigmaVox(dim);
        if ~isfinite(s) || s <= 0
            continue;
        end

        rad = max(1, ceil(3 * s));
        x = (-rad:rad);
        k = exp(-(x.^2) / (2 * s^2));
        k = k / sum(k);

        shape = [1 1 1];
        shape(dim) = numel(k);
        k = reshape(k, shape);

        Ysm = convn(Ysm, k, 'same');
        W = convn(W, k, 'same');
        Ysm = Ysm ./ max(W, eps);
    end
end

function [Vout, Mout] = local_upsample_volume(Vin, M, upFactor)
%LOCAL_UPSAMPLE_VOLUME Upsample a 3D volume by an integer factor and update affine.
%
% Inputs
%   Vin      : 3D array (single/double/logical). Interpreted in voxel space.
%   M        : 4x4 affine mapping voxel coordinates to world coordinates.
%   upFactor : integer >= 1. If 1, the input is returned unchanged.
%
% Outputs
%   Vout : upsampled volume (same class as Vin, unless logical -> single)
%   Mout : updated affine such that world coordinates remain consistent.
%
% Notes
%   - The upsampling grid preserves the original volume endpoints. The new
%     size is: (N-1)*upFactor + 1 along each dimension.
%   - NaNs in Vin are treated as missing values and do not bleed into valid
%     regions. Missing regions are filled with 0 in the output.
%   - Affine update: voxel_new -> voxel_old mapping is
%         x_old = (x_new-1)/upFactor + 1
%     hence Mout = M * T, where T encodes this mapping.

    upFactor = round(double(upFactor));
    if ~isfinite(upFactor) || upFactor < 1
        error('EA_NIFTI2PATCH:BadUpsampleFactor', 'GeometryUpsampleFactor must be an integer >= 1.');
    end

    if upFactor == 1
        Vout = Vin;
        Mout = M;
        return;
    end

    inClass = class(Vin);
    if islogical(Vin)
        Vin = single(Vin);
        inClass = 'single';
    end

    VinD = double(Vin);
    finiteMask = isfinite(VinD);
    VinD(~finiteMask) = 0;

    [ny, nx, nz] = size(VinD);
    ny2 = (ny - 1) * upFactor + 1;
    nx2 = (nx - 1) * upFactor + 1;
    nz2 = (nz - 1) * upFactor + 1;

    yq = linspace(1, ny, ny2);
    xq = linspace(1, nx, nx2);
    zq = linspace(1, nz, nz2);

    [Yq, Xq, Zq] = ndgrid(yq, xq, zq);

    % NaN-safe interpolation using value + weight fields.
    try
        Fv = griddedInterpolant(VinD, 'linear', 'nearest');
        Fw = griddedInterpolant(double(finiteMask), 'linear', 'nearest');
        Vq = Fv(Yq, Xq, Zq);
        Wq = Fw(Yq, Xq, Zq);
    catch
        % Fallback for older MATLAB versions.
        [X, Y, Z] = meshgrid(1:nx, 1:ny, 1:nz);
        Vq = interp3(X, Y, Z, VinD, Xq, Yq, Zq, 'linear', 0);
        Wq = interp3(X, Y, Z, double(finiteMask), Xq, Yq, Zq, 'linear', 0);
    end

    VoutD = Vq ./ max(Wq, eps);
    VoutD(Wq == 0) = 0;

    % Cast back.
    switch inClass
        case 'single'
            Vout = single(VoutD);
        case 'double'
            Vout = double(VoutD);
        otherwise
            % For other numeric types, keep as single to avoid overflow.
            Vout = single(VoutD);
    end

    % Update affine: map new voxel indices to old voxel indices.
    f = double(upFactor);
    T = eye(4);
    T(1,1) = 1 / f;
    T(2,2) = 1 / f;
    T(3,3) = 1 / f;
    T(1,4) = 1 - 1 / f;
    T(2,4) = 1 - 1 / f;
    T(3,4) = 1 - 1 / f;

    Mout = M * T;
end

function stats = local_empty_on_surface_fallback_stats(modeIn, radiusVox)
%LOCAL_EMPTY_ON_SURFACE_FALLBACK_STATS Create fallback provenance.

    stats = struct();
    stats.mode = char(string(modeIn));
    stats.radius_vox = double(radiusVox);
    stats.missing_before = 0;
    stats.filled_nearest = 0;
    stats.filled_nearest_finite = 0;
    stats.missing_after = 0;
end

function stats = local_empty_inside_only_stats()
%LOCAL_EMPTY_INSIDE_ONLY_STATS Create inside-only sampling provenance.

    stats = struct();
    stats.mode = 'insideOnly';
    stats.total_vertices = 0;
    stats.plus_selected_count = 0;
    stats.minus_selected_count = 0;
    stats.plus_mask_inside_finite_count = 0;
    stats.minus_mask_inside_finite_count = 0;
    stats.mask_inside_selected_count = 0;
    stats.finite_fallback_selected_count = 0;
    stats.mask_score_fallback_selected_count = 0;
    stats.tie_break_plus_count = 0;
    stats.missing_count = 0;
end

function stats = local_inside_only_stats_from_direct_sample(c)
%LOCAL_INSIDE_ONLY_STATS_FROM_DIRECT_SAMPLE Provenance for zero-depth sampling.

    stats = local_empty_inside_only_stats();
    stats.total_vertices = numel(c);
    stats.plus_selected_count = nnz(isfinite(c));
    stats.missing_count = nnz(~isfinite(c));
end

function [mPlus, mMinus] = local_sample_geometry_mask_scores( ...
    surfaceMode, maskField, MgeomSurf, vPlus, vMinus)
%LOCAL_SAMPLE_GEOMETRY_MASK_SCORES Sample mask-interior scores near vertices.

    n = size(vPlus, 1);
    mPlus = nan(n, 1);
    mMinus = nan(n, 1);

    if ~strcmp(surfaceMode, 'mask') || isempty(maskField)
        return;
    end

    mPlus = local_sample_data_at_world(maskField, MgeomSurf, vPlus, 'linear');
    mMinus = local_sample_data_at_world(maskField, MgeomSurf, vMinus, 'linear');
end

function [cOut, stats] = local_select_inside_only_samples( ...
    cPlus, cMinus, mPlus, mMinus, surfaceLevel)
%LOCAL_SELECT_INSIDE_ONLY_SAMPLES Select the mask-interior side per vertex.

    cPlus = cPlus(:);
    cMinus = cMinus(:);
    mPlus = mPlus(:);
    mMinus = mMinus(:);

    n = numel(cPlus);
    cOut = nan(n, 1);
    selected = false(n, 1);
    plusSelected = false(n, 1);
    minusSelected = false(n, 1);

    if isempty(surfaceLevel) || ~isfinite(surfaceLevel)
        insideThreshold = 0.5;
    else
        insideThreshold = double(surfaceLevel);
    end

    plusFinite = isfinite(cPlus);
    minusFinite = isfinite(cMinus);
    plusScoreFinite = isfinite(mPlus);
    minusScoreFinite = isfinite(mMinus);
    plusInside = plusScoreFinite & (mPlus >= insideThreshold);
    minusInside = minusScoreFinite & (mMinus >= insideThreshold);

    plusInsideFinite = plusInside & plusFinite;
    minusInsideFinite = minusInside & minusFinite;

    takePlus = plusInsideFinite & ~minusInsideFinite;
    takeMinus = minusInsideFinite & ~plusInsideFinite;

    bothInsideFinite = plusInsideFinite & minusInsideFinite;
    takePlus = takePlus | (bothInsideFinite & (mPlus > mMinus));
    takeMinus = takeMinus | (bothInsideFinite & (mMinus > mPlus));
    maskInsideTie = bothInsideFinite & ~(takePlus | takeMinus);
    takePlus = takePlus | maskInsideTie;

    [cOut, selected, plusSelected, minusSelected] = local_apply_side_selection( ...
        cOut, selected, plusSelected, minusSelected, takePlus, takeMinus, cPlus, cMinus);

    remaining = ~selected;
    onlyPlusFinite = remaining & plusFinite & ~minusFinite;
    onlyMinusFinite = remaining & minusFinite & ~plusFinite;

    [cOut, selected, plusSelected, minusSelected] = local_apply_side_selection( ...
        cOut, selected, plusSelected, minusSelected, ...
        onlyPlusFinite, onlyMinusFinite, cPlus, cMinus);

    remaining = ~selected;
    bothFinite = remaining & plusFinite & minusFinite;
    plusHasHigherScore = bothFinite & plusScoreFinite & ...
        (~minusScoreFinite | (mPlus > mMinus));
    minusHasHigherScore = bothFinite & minusScoreFinite & ...
        (~plusScoreFinite | (mMinus > mPlus));
    scoreTie = bothFinite & ~(plusHasHigherScore | minusHasHigherScore);
    plusHasHigherScore = plusHasHigherScore | scoreTie;

    [cOut, ~, plusSelected, minusSelected] = local_apply_side_selection( ...
        cOut, selected, plusSelected, minusSelected, ...
        plusHasHigherScore, minusHasHigherScore, cPlus, cMinus);

    stats = local_empty_inside_only_stats();
    stats.total_vertices = n;
    stats.plus_selected_count = nnz(plusSelected);
    stats.minus_selected_count = nnz(minusSelected);
    stats.plus_mask_inside_finite_count = nnz(plusInsideFinite);
    stats.minus_mask_inside_finite_count = nnz(minusInsideFinite);
    stats.mask_inside_selected_count = nnz((takePlus | takeMinus) & ...
        (plusInsideFinite | minusInsideFinite));
    stats.finite_fallback_selected_count = nnz(onlyPlusFinite | onlyMinusFinite);
    stats.mask_score_fallback_selected_count = nnz(plusHasHigherScore | minusHasHigherScore);
    stats.tie_break_plus_count = nnz(maskInsideTie | scoreTie);
    stats.missing_count = nnz(~isfinite(cOut));
end

function [cOut, selected, plusSelected, minusSelected] = local_apply_side_selection( ...
    cOut, selected, plusSelected, minusSelected, takePlus, takeMinus, cPlus, cMinus)
%LOCAL_APPLY_SIDE_SELECTION Apply mutually exclusive plus/minus choices.

    takePlus = takePlus & ~takeMinus & ~selected;
    takeMinus = takeMinus & ~takePlus & ~selected;

    cOut(takePlus) = cPlus(takePlus);
    cOut(takeMinus) = cMinus(takeMinus);
    selected = selected | takePlus | takeMinus;
    plusSelected = plusSelected | takePlus;
    minusSelected = minusSelected | takeMinus;
end

function [cOut, stats] = local_apply_on_surface_missing_fallback( ...
    Ydata_p, Mdata, v_world, cIn, modeIn, radiusVox)
%LOCAL_APPLY_ON_SURFACE_MISSING_FALLBACK Fill missing boundary samples.
%
% Exact linear interpolation on a mask-derived boundary can be missing when
% the surface lies between finite data and outside-mask NaNs. This fallback
% stays on the boundary coordinate system: it does not sample along normals
% and does not choose values by absolute magnitude.

    cOut = cIn;
    stats = local_empty_on_surface_fallback_stats(modeIn, radiusVox);

    mode = lower(strtrim(char(string(modeIn))));
    radiusVox = round(double(radiusVox));
    stats.radius_vox = radiusVox;

    missing = ~isfinite(cOut);
    stats.missing_before = nnz(missing);
    if ~any(missing) || any(strcmp(mode, {'none','off','false','disabled'}))
        stats.missing_after = nnz(~isfinite(cOut));
        return;
    end

    if any(strcmp(mode, {'nearest','nearestfinite','nearest_finite'}))
        cNearest = local_sample_data_at_world(Ydata_p, Mdata, v_world, 'nearest');
        take = missing & isfinite(cNearest);
        cOut(take) = cNearest(take);
        stats.filled_nearest = nnz(take);
    end

    missing = ~isfinite(cOut);
    if any(strcmp(mode, {'nearestfinite','nearest_finite'})) && any(missing) && radiusVox > 0
        idx = find(missing);
        cFinite = local_sample_nearest_finite_voxel( ...
            Ydata_p, Mdata, v_world(idx, :), radiusVox);
        take = isfinite(cFinite);
        cOut(idx(take)) = cFinite(take);
        stats.filled_nearest_finite = nnz(take);
    elseif ~any(strcmp(mode, {'nearest','nearestfinite','nearest_finite'}))
        error('EA_NIFTI2PATCH:BadOnSurfaceMissingFallback', ...
            'Unknown OnSurfaceMissingFallback: %s (use ''nearestFinite'', ''nearest'', or ''none'').', ...
            char(string(modeIn)));
    end

    stats.missing_after = nnz(~isfinite(cOut));
end

function c = local_sample_data_at_world(Ydata_p, Mdata, v_world, method)
%LOCAL_SAMPLE_DATA_AT_WORLD Sample DATA volume at world (mm) coordinates.
%
% This converts world coordinates to voxel coordinates using inv(Mdata), and
% then interpolates from Ydata_p (which may be permuted).

    if nargin < 4 || isempty(method)
        method = 'linear';
    end

    Minv = inv(Mdata);
    v_vox = [v_world, ones(size(v_world,1), 1)] * Minv';
    xq = v_vox(:, 1);
    yq = v_vox(:, 2);
    zq = v_vox(:, 3);
    c = local_interp3_safe(Ydata_p, xq, yq, zq, method);
end

function vq = local_interp3_safe(V, xq, yq, zq, method)
%LOCAL_INTERP3_SAFE Robust 3D interpolation with NaN fill outside bounds.

    if nargin < 5 || isempty(method)
        method = 'linear';
    end
    method = char(string(method));

    try
        vq = interp3(V, xq, yq, zq, method, NaN);
    catch
        % Some MATLAB versions require explicit grids.
        [ny, nx, nz] = size(V);
        [X, Y, Z] = meshgrid(1:nx, 1:ny, 1:nz);
        vq = interp3(X, Y, Z, V, xq, yq, zq, method, NaN);
    end
end

function values = local_sample_nearest_finite_voxel(V, Mdata, v_world, radiusVox)
%LOCAL_SAMPLE_NEAREST_FINITE_VOXEL Find nearest finite voxel around samples.

    n = size(v_world, 1);
    values = nan(n, 1);
    if n == 0
        return;
    end

    radiusVox = max(0, round(double(radiusVox)));
    Minv = inv(Mdata);
    v_vox = [v_world, ones(n, 1)] * Minv';
    xq = v_vox(:, 1);
    yq = v_vox(:, 2);
    zq = v_vox(:, 3);

    [nRows, nCols, nPlanes] = size(V);

    for i = 1:n
        if ~all(isfinite([xq(i), yq(i), zq(i)]))
            continue;
        end

        x0 = round(xq(i));
        y0 = round(yq(i));
        z0 = round(zq(i));

        xMin = max(1, x0 - radiusVox);
        xMax = min(nCols, x0 + radiusVox);
        yMin = max(1, y0 - radiusVox);
        yMax = min(nRows, y0 + radiusVox);
        zMin = max(1, z0 - radiusVox);
        zMax = min(nPlanes, z0 + radiusVox);

        if xMin > xMax || yMin > yMax || zMin > zMax
            continue;
        end

        block = V(yMin:yMax, xMin:xMax, zMin:zMax);
        finiteMask = isfinite(block);
        if ~any(finiteMask(:))
            continue;
        end

        [yy, xx, zz] = ndgrid(yMin:yMax, xMin:xMax, zMin:zMax);
        d2 = (double(xx) - xq(i)).^2 + ...
             (double(yy) - yq(i)).^2 + ...
             (double(zz) - zq(i)).^2;
        d2(~finiteMask) = inf;
        [~, bestIdx] = min(d2(:));
        values(i) = block(bestIdx);
    end
end

function N = local_vertex_normals(V, F)
%LOCAL_VERTEX_NORMALS Compute per-vertex normals from a triangular mesh.
%
% Inputs
%   V : Nx3 vertices
%   F : Mx3 faces
%
% Output
%   N : Nx3 (unnormalized) vertex normals

    v1 = V(F(:,1), :);
    v2 = V(F(:,2), :);
    v3 = V(F(:,3), :);

    fn = cross(v2 - v1, v3 - v1, 2);  % face normals (area-weighted)

    nV = size(V, 1);
    N = zeros(nV, 3);

    % Accumulate face normals into vertex normals.
    for k = 1:3
        idx = F(:, k);
        N = N + accumarray(idx, fn(:,1), [nV 1], @sum, 0) * [1 0 0] + ...
                accumarray(idx, fn(:,2), [nV 1], @sum, 0) * [0 1 0] + ...
                accumarray(idx, fn(:,3), [nV 1], @sum, 0) * [0 0 1];
    end
end

function X = local_normalize_rows(X)
%LOCAL_NORMALIZE_ROWS Normalize each row vector to unit length.

    n = sqrt(sum(X.^2, 2));
    n(n == 0) = 1;
    X = X ./ n;
end

function Vsm = local_smooth_mesh(V, F, iters, method, lambda, mu)
%LOCAL_SMOOTH_MESH Smooth a mesh using Laplacian or Taubin smoothing.
%
% Notes
%   - 'laplacian' uses: V <- V + lambda * (mean(neigh) - V)
%   - 'taubin' applies a second pass with negative mu to reduce shrinkage.

    Vsm = V;

    % Build symmetric adjacency matrix.
    nV = size(Vsm, 1);
    I = [F(:,1); F(:,2); F(:,3)];
    J = [F(:,2); F(:,3); F(:,1)];
    A = sparse([I; J], [J; I], 1, nV, nV);
    A = A > 0;

    deg = sum(A, 2);
    deg(deg == 0) = 1;

    method = lower(strtrim(method));
    for i = 1:iters
        Vsm = local_lap_step(Vsm, A, deg, lambda);
        if strcmp(method, 'taubin')
            Vsm = local_lap_step(Vsm, A, deg, mu);
        elseif ~strcmp(method, 'laplacian')
            error('EA_NIFTI2PATCH:BadSmoothingMethod', ...
                'Unknown SurfaceSmoothingMethod: %s (use ''taubin'' or ''laplacian'').', method);
        end
    end
end

function Vout = local_lap_step(Vin, A, deg, w)
%LOCAL_LAP_STEP Single Laplacian smoothing step.

    neighMean = (A * Vin) ./ deg;
    Vout = Vin + w * (neighMean - Vin);
end

function [cmap, cmapName] = local_resolve_colormap(cmapIn, n)
%LOCAL_RESOLVE_COLORMAP Resolve a colormap specification into an Nx3 array.
%
% Inputs
%   cmapIn : [] | Nx3 numeric array | string/char name
%   n      : number of samples (rows) to return
%
% Outputs
%   cmap     : n-by-3 colormap array
%   cmapName : resolved name (best effort)
%
% Notes
%   - If cmapIn is empty, defaults to 'viridis'.
%   - Supported custom names: 'viridis', 'vik'.
%   - For other names, this function attempts to call a MATLAB colormap
%     function of the same name (e.g., 'parula', 'jet').

    if nargin < 2 || isempty(n)
        n = 256;
    end

    if isempty(cmapIn)
        cmapIn = 'viridis';
    end

    if isnumeric(cmapIn)
        % Numeric Nx3 colormap.
        if size(cmapIn, 2) ~= 3
            error('EA_NIFTI2PATCH:BadColormap', 'Numeric Colormap must be an Nx3 array.');
        end
        if size(cmapIn, 1) == n
            cmap = cmapIn;
        else
            % Resample to n rows.
            x0 = linspace(0, 1, size(cmapIn, 1));
            x1 = linspace(0, 1, n);
            cmap = interp1(x0, cmapIn, x1, 'linear');
        end
        cmapName = 'custom';
        return;
    end

    if isstring(cmapIn) || ischar(cmapIn)
        s = lower(strtrim(char(cmapIn)));
        cmapName = s;

        switch s
            case {'viridis', 'vir'}
                cmap = ea_colormap_viridis(n);
                cmapName = 'viridis';
            case {'vik'}
                cmap = ea_colormap_vik(n);
                cmapName = 'vik';
            otherwise
                % Try to fall back to MATLAB built-in colormap functions.
                try
                    f = str2func(s);
                    cmap = f(n);
                catch
                    warning('EA_NIFTI2PATCH:UnknownColormap', ...
                        'Unknown colormap name "%s". Falling back to viridis.', s);
                    cmap = ea_colormap_viridis(n);
                    cmapName = 'viridis';
                end
        end
        return;
    end

    error('EA_NIFTI2PATCH:BadColormap', ...
        'Colormap must be empty, an Nx3 numeric array, or a string name.');
end
