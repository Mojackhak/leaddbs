ea_mnifigure('Custom_Ewert_Zhang_Middlebrooks'); % open up Elvis viewer
load([ea_space([],'atlases'),'Custom_Ewert_Zhang_Middlebrooks0.05',filesep,'atlas_index.mat']); % manually load definition of atlas.
rSNr=atlases.roi{14,1}.fv; % extract the right SNr.
rSNr=reducepatch(rSNr,0.5); % reduce patch a bit.
rh=patch('Faces',rSNr.faces,'Vertices',rSNr.vertices,'facecolor','none','edgecolor','w'); % visualize the right SNr as wireframes.
