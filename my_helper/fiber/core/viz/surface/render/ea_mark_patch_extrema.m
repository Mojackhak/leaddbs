function extrema = ea_mark_patch_extrema(hAx, patchObj, varargin)
%EA_MARK_PATCH_EXTREMA Highlight global min/max locations on a patch surface.
%
%   extrema = EA_MARK_PATCH_EXTREMA(hAx, patchObj)
%   extrema = EA_MARK_PATCH_EXTREMA(hAx, patchObj, 'Name', value, ...)
%
% This utility finds the global minimum and/or maximum of the scalar surface
% values (patchObj.facevertexcdata) and highlights a local neighborhood of
% faces around the extreme location. The highlight uses a simple "fade"
% colormap: the center is saturated (red for max, blue for min by default)
% and it gradually becomes lighter toward the boundary.
%
% Inputs
%   hAx      : target axes handle.
%   patchObj : struct with fields:
%       .faces            (Mx3) triangle indices
%       .vertices         (Nx3) vertex coordinates in mm
%       .facevertexcdata  (Nx1) scalar values per vertex
%
% Name-Value pairs
%   'MarkMin'        : logical. Default: true
%   'MarkMax'        : logical. Default: true
%   'ExcludeZero'    : logical. Exclude vertices with value==0 when searching
%                      for extrema. Default: true
%   'RadiusMm'       : scalar >0. Neighborhood radius in mm. Default: 0.5
%   'LightenFactor'  : scalar in [0,1]. Boundary color is computed as:
%                        boundary = (1-L)*base + L*[1 1 1]
%                      Default: 0.8
%   'MaxColor'       : 1x3 RGB (0..1). Default: [1 0 0]
%   'MinColor'       : 1x3 RGB (0..1). Default: [0 0 1]
%   'Alpha'          : scalar in [0,1]. Overlay alpha. Default: 1
%   'FontSize'       : label font size. Default: 10
%   'MarkerSize'     : scatter marker size. Default: 36
%
% Output
%   extrema : struct with fields for each marked extreme:
%       .max.value, .max.center_mm, .max.patch, .max.marker, .max.text
%       .min.value, .min.center_mm, .min.patch, .min.marker, .min.text
%
% Notes
%   - The extreme location is defined by the vertex with the global
%     min/max value. The "center" of the highlight is the center of a
%     triangle that contains that vertex (chosen as the closest adjacent
%     face center to the vertex).
%   - Faces within RadiusMm (by face-center distance) are highlighted.
%   - The highlight overlay uses truecolor (RGB) and does not affect the
%     main colormap (e.g., viridis) used for the base patch.

    if nargin < 2
        error('EA_MARK_PATCH_EXTREMA:BadInput', 'Usage: extrema = ea_mark_patch_extrema(hAx, patchObj, ...)');
    end
    if ~ishandle(hAx)
        error('EA_MARK_PATCH_EXTREMA:BadAxes', 'hAx must be a valid axes handle.');
    end
    if ~isstruct(patchObj) || ~isfield(patchObj, 'faces') || ~isfield(patchObj, 'vertices') || ~isfield(patchObj, 'facevertexcdata')
        error('EA_MARK_PATCH_EXTREMA:BadPatchObj', 'patchObj must include faces, vertices and facevertexcdata.');
    end

    F = patchObj.faces;
    V = patchObj.vertices;
    c = patchObj.facevertexcdata;

    if size(V,2) ~= 3
        error('EA_MARK_PATCH_EXTREMA:BadVertices', 'patchObj.vertices must be Nx3.');
    end
    if size(F,2) ~= 3
        error('EA_MARK_PATCH_EXTREMA:BadFaces', 'patchObj.faces must be Mx3.');
    end
    if numel(c) ~= size(V,1)
        error('EA_MARK_PATCH_EXTREMA:BadCData', 'facevertexcdata length must match number of vertices.');
    end
    c = double(c(:));

    ip = inputParser;
    ip.FunctionName = mfilename;
    addParameter(ip, 'MarkMin', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'MarkMax', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ExcludeZero', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'ExcludeMissing', true, @(x) islogical(x) && isscalar(x));
    addParameter(ip, 'RadiusMm', 0.5, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'LightenFactor', 0.8, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'MaxColor', [1 0 0], @(x) isnumeric(x) && numel(x) == 3);
    addParameter(ip, 'MinColor', [0 0 1], @(x) isnumeric(x) && numel(x) == 3);
    addParameter(ip, 'Alpha', 1, @(x) isnumeric(x) && isscalar(x) && x >= 0 && x <= 1);
    addParameter(ip, 'FontSize', 10, @(x) isnumeric(x) && isscalar(x) && x > 0);
    addParameter(ip, 'FontName', 'Arial', @(s) ischar(s) || (isstring(s) && isscalar(s)));
    addParameter(ip, 'MarkerSize', 36, @(x) isnumeric(x) && isscalar(x) && x > 0);
    parse(ip, varargin{:});
    p = ip.Results;

    extrema = struct();
    extrema.radius_mm = p.RadiusMm;
    extrema.exclude_zero = p.ExcludeZero;
    extrema.lighten_factor = p.LightenFactor;

    % Determine which vertices are eligible for min/max search.
    good = isfinite(c);
    if p.ExcludeZero
        good = good & (c ~= 0);
    end

    % Optionally exclude vertices that were missing during volume sampling
    % (useful when geometry comes from a template).
    if isfield(patchObj, 'missing_vertex_mask') && ~isempty(patchObj.missing_vertex_mask) && p.ExcludeMissing
        mv = patchObj.missing_vertex_mask(:);
        if numel(mv) == numel(c)
            good = good & ~mv;
        end
    end
    if ~any(good)
        warning('EA_MARK_PATCH_EXTREMA:NoValidValues', 'No valid surface values found after filtering; skipping extrema.');
        return;
    end

    % Precompute face centers (used for radius selection).
    faceCenters = (V(F(:,1),:) + V(F(:,2),:) + V(F(:,3),:)) / 3;

    if p.MarkMax
        extrema.max = local_make_one('max', true, p.MaxColor);
    end
    if p.MarkMin
        extrema.min = local_make_one('min', false, p.MinColor);
    end

    % ------------------------------------------------------------------
    % Nested helper: create one highlight region (min or max)
    % ------------------------------------------------------------------
    function out = local_make_one(kind, isMax, baseColor)
        out = struct();
        baseColor = double(baseColor(:))';
        if numel(baseColor) ~= 3
            error('EA_MARK_PATCH_EXTREMA:BadColor', '%s color must be 1x3.', kind);
        end

        % Find extreme vertex.
        cTmp = c;
        cTmp(~good) = NaN;
        if isMax
            [val, idxV] = max(cTmp);
        else
            [val, idxV] = min(cTmp);
        end
        if ~isfinite(val) || isempty(idxV)
            out.value = NaN;
            return;
        end
        out.value = val;
        out.vertex_index = idxV;
        out.vertex_mm = V(idxV,:);

        % Choose a face "representing" this vertex.
        facesWithV = find(any(F == idxV, 2));
        if isempty(facesWithV)
            out.center_mm = out.vertex_mm;
            return;
        end

        % Pick the adjacent face whose center is closest to the vertex.
        cAdj = faceCenters(facesWithV,:);
        dAdj = sqrt(sum((cAdj - out.vertex_mm).^2, 2));
        [~, iBest] = min(dAdj);
        iFace = facesWithV(iBest);
        out.face_index = iFace;
        center = faceCenters(iFace,:);
        out.center_mm = center;

        % Select faces within the requested radius by face-center distance.
        dAll = sqrt(sum((faceCenters - center).^2, 2));
        in = dAll <= p.RadiusMm;
        idxFaces = find(in);
        out.faces_in_radius = idxFaces;

        if isempty(idxFaces)
            return;
        end

        % Compute a smooth vertex-wise fade field inside the selected faces.
        idxVerts = unique(F(idxFaces,:));
        dV = sqrt(sum((V(idxVerts,:) - center).^2, 2));
        w = max(0, 1 - (dV ./ p.RadiusMm));

        % Boundary (light) color.
        L = p.LightenFactor;
        lightCol = (1 - L) * baseColor + L * [1 1 1];

        % Truecolor per vertex. Unused vertices can be set to light color.
        C = repmat(lightCol, size(V,1), 1);
        C(idxVerts,:) = baseColor .* w + lightCol .* (1 - w);

        % Draw an overlay patch (truecolor, independent of the main colormap).
        hp = patch(hAx, ...
            'Faces', F(idxFaces,:), ...
            'Vertices', V, ...
            'FaceVertexCData', C, ...
            'FaceColor', 'interp', ...
            'EdgeColor', 'none', ...
            'FaceAlpha', p.Alpha, ...
            'CDataMapping', 'direct', ...
            'HitTest', 'off');
        try
            hp.PickableParts = 'none';
        catch
        end
        out.patch = hp;

        % Add a point marker at the center and a short text label.
        hm = scatter3(hAx, center(1), center(2), center(3), p.MarkerSize, ...
            'filled', 'MarkerFaceColor', baseColor, 'MarkerEdgeColor', 'none', 'HitTest', 'off');
        try
            hm.PickableParts = 'none';
        catch
        end
        out.marker = hm;

        labelStr = kind;
        % Offset text slightly toward the camera for readability.
        tpos = center + local_text_offset(p.RadiusMm);
        ht = text(hAx, tpos(1), tpos(2), tpos(3), labelStr, ...
            'Color', baseColor, 'FontWeight', 'bold', 'FontSize', p.FontSize, 'FontName', char(p.FontName), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', 'HitTest', 'off');
        try
            ht.PickableParts = 'none';
        catch
        end
        out.text = ht;
    end

    function off = local_text_offset(radiusMm)
        % Move label slightly toward the camera so it is less likely to be
        % hidden inside semi-transparent surfaces.
        off = [0 0 0];
        try
            camPos = get(hAx, 'CameraPosition');
            camTar = get(hAx, 'CameraTarget');
            vdir = camPos - camTar;
            n = norm(vdir);
            if n > 0
                vdir = vdir / n;
                off = vdir * (0.25 * radiusMm);
            end
        catch
        end
    end
end
