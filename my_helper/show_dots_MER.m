ea_mnifigure('Custom_Ewert_Zhang_Middlebrooks0.05'); % open up Elvis viewer
load([ea_space([],'atlases'),'Custom_Ewert_Zhang_Middlebrooks0.05',filesep,'atlas_index.mat']); % manually load definition of atlas.
rSNr=atlases.roi{13,1}.fv; % extract the right SNr.
rSNr=reducepatch(rSNr,0.5); % reduce patch a bit.
rh=patch('Faces',rSNr.faces,'Vertices',rSNr.vertices,'facecolor','none','edgecolor',[1,0.5020,0]); % visualize the right SNr as wireframes.
lSNr=atlases.roi{13,2}.fv; % do the same for the left SNr.
lSNr=reducepatch(lSNr,0.5);
lh=patch('Faces',lSNr.faces,'Vertices',lSNr.vertices,'facecolor','none','edgecolor',[1,0.5020,0]);

% add MER coords
df = readtable('/Volumes/Data/STNSNr/summary/spike/MER_loc_contact_clean_mni_loc.csv');
coords = [df.MNI_x, df.MNI_y, df.MNI_z];
mask = strcmp(df.SNr_in, 'TRUE');
coords(~mask,:) = [];
coords(any(isnan(coords),2),:) = [];
radius = 0.127;
n = 100;
color = [0.4, 1, 1];
h = add_spheres(coords, radius, n, 'FaceColor', color);

% set(h, 'FaceAlpha', 0);   % fully transparent (effectively hidden)
% set(rh, 'edgeAlpha', 0);   % fully transparent (effectively hidden)
% set(lh, 'edgeAlpha', 0);   % fully transparent (effectively hidden)