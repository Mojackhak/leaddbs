ea_mnifigure('Custom_Ewert_Zhang_Middlebrooks0.05'); % open up Elvis viewer
load([ea_space([],'atlases'),'Custom_Ewert_Zhang_Middlebrooks0.05',filesep,'atlas_index.mat']); % manually load definition of atlas.

rSNr=atlases.roi{13,1}.fv; % extract the right SNr.
rSNr=reducepatch(rSNr,0.5); % reduce patch a bit.
rh=patch('Faces',rSNr.faces,'Vertices',rSNr.vertices,'facecolor','none','edgecolor',[1,0.5020,0]); % visualize the right SNr as wireframes.
lSNr=atlases.roi{13,2}.fv; % do the same for the left SNr.
lSNr=reducepatch(lSNr,0.5);
lh=patch('Faces',lSNr.faces,'Vertices',lSNr.vertices,'facecolor','none','edgecolor',[1,0.5020,0]);

rSTN=atlases.roi{14,1}.fv; % extract the right STN.
rSTN=reducepatch(rSTN,0.5); % reduce patch a bit.
rh=patch('Faces',rSTN.faces,'Vertices',rSTN.vertices,'facecolor','none','edgecolor',[0,0.7843,0]); % visualize the right STN as wireframes.
lSTN=atlases.roi{14,2}.fv; % do the same for the left STN.
lSTN=reducepatch(lSTN,0.5);
lh=patch('Faces',lSTN.faces,'Vertices',lSTN.vertices,'facecolor','none','edgecolor',[0,0.7843,0]);

% add MER coords
df = readtable('/Volumes/Data/STNSNr/summary/lead_loc/contact_space_locs_LFP25.csv');
coords4 = [df.MNI_x, df.MNI_y, df.MNI_z];
mask4 = df.contactNum==4;
coords4(~mask4,:) = [];
coords4(any(isnan(coords4),2),:) = [];
radius = 0.127;
n = 100;
color4 = [1, 0.411764705882353, 0.16078431372549];
h4 = add_spheres(coords4, radius, n, 'FaceColor', color4);

coords8 = [df.MNI_x, df.MNI_y, df.MNI_z];
mask8 = df.contactNum==8;
coords8(~mask8,:) = [];
coords8(any(isnan(coords8),2),:) = [];
radius = 0.127;
n = 100;
color8 = [0.301960784313725, 0.745098039215686, 0.933333333333333];
h8 = add_spheres(coords8, radius, n, 'FaceColor', color8);

% set(h, 'FaceAlpha', 0);   % fully transparent (effectively hidden)
% set(rh, 'edgeAlpha', 0);   % fully transparent (effectively hidden)
% set(lh, 'edgeAlpha', 0);   % fully transparent (effectively hidden)