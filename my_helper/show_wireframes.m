ea_mnifigure('DISTAL Minimal (Ewert 2017)'); % open up Elvis viewer
ea_keepatlaslabels('GPI'); % hide all structures except GPi
load([ea_space([],'atlases'),'DISTAL Minimal (Ewert 2017)',filesep,'atlas_index.mat']); % manually load definition of DISTAL atlas.
rSTN=atlases.roi{1,1}.fv; % extract the right STN.
rSTN=reducepatch(rSTN,0.5); % reduce patch a bit.
patch('Faces',rSTN.faces,'Vertices',rSTN.vertices,'facecolor','none','edgecolor','w'); % visualize the right STN as wireframes.
lSTN=atlases.roi{1,2}.fv; % do the same for the left STN.
lSTN=reducepatch(lSTN,0.5);
patch('Faces',lSTN.faces,'Vertices',lSTN.vertices,'facecolor','none','edgecolor','w');
ea_setplanes(0,-30,nan); % set planes to a nice view.

% now define a specific camera view:
v.az= 126.0430;
v.el= -34.9893;
v.camva= 0.4648;
v.camup= [0 0 1];
v.camproj= 'orthographic';
v.camtarget= [-1.2419 -23.0911 3.9242];
v.campos= [1.0973e+03 1.0671e+03 -1.0542e+03];
ea_view(v); % apply view.