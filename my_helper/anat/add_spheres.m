function h = add_spheres(centers, radius, n, varargin)
% centers: [N x 3] (mm, same space as your STN meshes)
% radius : scalar (mm) # default 0.25
% n      : sphere mesh resolution (e.g., 8–16). Higher = smoother.
% varargin: passed to patch (e.g., 'FaceColor',[1 0 0],'EdgeColor','none')

if nargin < 3 || isempty(n), n = 12; end
if nargin < 2, error('Need centers and radius'); end

% base unit sphere -> triangles
[X,Y,Z] = sphere(n);
[F0,V0] = surf2patch(X*radius, Y*radius, Z*radius, 'triangles');  % scale to radius
nv = size(V0,1); nf = size(F0,1);

k  = size(centers,1);
V  = zeros(nv*k,3);
F  = zeros(nf*k,3);

for i = 1:k
    vi = (i-1)*nv + (1:nv);
    fi = (i-1)*nf + (1:nf);
    V(vi,:) = V0 + centers(i,:);        % translate
    F(fi,:) = F0 + (i-1)*nv;            % reindex faces
end

hold on
h = patch('Faces',F,'Vertices',V, ...
          'FaceColor',[1 1 1], 'EdgeColor','none', ...
          'FaceAlpha',1, varargin{:});
% optional lighting to make them look like true spheres
lighting gouraud; material dull; camlight('headlight');
end

% set(h, 'FaceAlpha', 0);   % fully transparent (effectively hidden)
% set(h, 'FaceAlpha', 0.3); % semi-transparent
