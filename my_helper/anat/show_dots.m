ea_mnifigure('Custom_Ewert_Zhang_Middlebrooks0.05'); % open up Elvis viewer
load([ea_space([],'atlases'),'Custom_Ewert_Zhang_Middlebrooks0.05',filesep,'atlas_index.mat']); % manually load definition of atlas.
rSNr=atlases.roi{13,1}.fv; % extract the right SNr.
rSNr=reducepatch(rSNr,0.5); % reduce patch a bit.
rh=patch('Faces',rSNr.faces,'Vertices',rSNr.vertices,'facecolor','none','edgecolor',[1,0.5020,0],'EdgeAlpha', 0.4); % visualize the right SNr as wireframes.
rSTN=atlases.roi{14,1}.fv; % do the same for the left SNr.
rSTN=reducepatch(rSTN,0.5);
lh=patch('Faces',rSTN.faces,'Vertices',rSTN.vertices,'facecolor','none','edgecolor',[0,0.7843,0],'EdgeAlpha', 0.4);

% add MER coords
df = readtable('/Users/mojackhu/Research/STNSNr/summary/stats/clinic/coords/scale/scale_contact_only.xlsx');
coords = [df.MNI_x_flip, df.MNI_y_flip, df.MNI_z_flip];
% mask = strcmp(df.SNr_in, 'TRUE');
% coords(~mask,:) = [];
% coords(any(isnan(coords),2),:) = [];
radius = 0.25;
n = 100;
color = [0.301960784313725, 0.745098039215686, 0.933333333333333];
h = add_spheres(coords, radius, n, 'FaceColor', color);

% set(h, 'FaceAlpha', 0);   % fully transparent (effectively hidden)
% set(rh, 'edgeAlpha', 0);   % fully transparent (effectively hidden)
% set(lh, 'edgeAlpha', 0);   % fully transparent (effectively hidden)