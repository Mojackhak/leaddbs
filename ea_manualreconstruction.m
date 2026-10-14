function ea_manualreconstruction(mcfig,patientname,options)
% This is the function that enables the user to manually correct the
% electrode positions that have been reconstructed by the algorithm. A
% handle for the figure, the coordinates of the contacts in millimeter
% notation, optionally manually measured coordinates, the fitted line in
% form of a 1x2 cell each containing a nx3 matrix that describes the line,
% the full path to the coronal nifti file, the name of the patient and the
% usual options struct must be handed to the function as parameters.
%
% Output parameters are the figure handle and the corrected coordinates and
% will be returned once the user presses the spacebar.
% __________________________________________________________________________________
% Copyright (C) 2015 Charite University Medicine Berlin, Movement Disorders Unit
%
% Andreas Horn

set(mcfig,'color','k');
axis off
setappdata(mcfig,'c_lims',[1800,2800]);
setappdata(mcfig,'selectrode',0);
setappdata(mcfig,'planecset',0);

set(mcfig,'KeyPressFcn',@ea_keystr);
set(mcfig, 'BusyAction','cancel', 'Interruptible','off');
setappdata(mcfig,'patientname',patientname);
%setappdata(mcfig,'trajectory',trajectory);
setappdata(mcfig,'origoptions',options); % store original options for further processing.

options.native=1;
options.loadnativereco = 1; % Load native reco intead of scrf
options.xray=0;
setappdata(mcfig,'options',options);

if ~isfile(options.subj.recon.recon)
    close(mcfig);
    msgbox('Please run pre-Reconstruct module first.');
    return
end

[~,trajectory,markers,elmodel,manually_corrected,~,stored]=ea_load_reconstruction(options);
storedModels = {stored.props.elmodel};
if (~isfield(options, 'elmodels') || isempty(options.elmodels)) && ...
        (numel(storedModels) > 2 || numel(unique(storedModels)) > 1)
    options.elmodels = storedModels;
    original = getappdata(mcfig, 'origoptions');
    original.elmodels = storedModels;
    setappdata(mcfig, 'origoptions', original);
    setappdata(mcfig, 'options', options);
end
for side = options.sides
    if side > numel(markers) || isempty(markers(side).head) || isempty(markers(side).tail)
        close(mcfig);
        error('LeadDBS:MissingElectrodeLocalization', 'Localize electrode %d before opening manual refinement.', side);
    end
end
setappdata(mcfig,'markers',markers);

setappdata(mcfig,'origtrajectory',trajectory);
setappdata(mcfig,'manually_corrected',manually_corrected);

% initialize scene
ea_mancor_updatescene([],[],mcfig);

% initialize toolbar
ht=uitoolbar(mcfig);
captions=getappdata(mcfig,'captions');
c_step=2;

prevlead=uipushtool(ht,'CData',ea_get_icn('prevlead'),'TooltipString','Previous Electrode [<]','ClickedCallback',{@sequenceelectrode,mcfig,'prev'});
nextlead=uipushtool(ht,'CData',ea_get_icn('nextlead'),'TooltipString','Next Electrode [>]','ClickedCallback',{@sequenceelectrode,mcfig,'next'});

hf=uitoggletool(ht,'CData',ea_get_icn('hidefid'),'TooltipString','Show/Hide Fiducials','State','off','OnCallback',{@hidefid,mcfig},'OffCallback',{@showfid,mcfig});
setappdata(mcfig,'hf',hf);

minuscontrast=uipushtool(ht,'CData',ea_get_icn('contrastminus'),'TooltipString','Decrease Contrast [C]','ClickedCallback',{@setcontrast,'c',nan,mcfig});
pluscontrast=uipushtool(ht,'CData',ea_get_icn('contrastplus'),'TooltipString','Increase Contrast [V]','ClickedCallback',{@setcontrast,'v',nan,mcfig});
minusbrightness=uipushtool(ht,'CData',ea_get_icn('brightnessminus'),'TooltipString','Decrease Brightness [B]','ClickedCallback',{@setcontrast,'b',nan,mcfig});
plusbrightness=uipushtool(ht,'CData',ea_get_icn('brightnessplus'),'TooltipString','Increase Brightness [N]','ClickedCallback',{@setcontrast,'n',nan,mcfig});

eltog(1)=uitoggletool(ht,'CData',ea_get_icn('el0'),'TooltipString','Select distal contact [0]','State','off','OnCallback',{@selectelectrode},'OffCallback',{@deselectelectrode});
eltog(2)=uitoggletool(ht,'CData',ea_get_icn('el3'),'TooltipString','Select proximal contact [3]','State','off','OnCallback',{@selectelectrode},'OffCallback',{@deselectelectrode});
%eltog(3)=uitoggletool(ht,'CData',ea_get_icn('el4'),'TooltipString','Select Electrode 4 [4]','State','off','OnCallback',{@selectelectrode},'OffCallback',{@deselectelectrode});
%eltog(4)=uitoggletool(ht,'CData',ea_get_icn('el7'),'TooltipString','Select Electrode 7 [7]','State','off','OnCallback',{@selectelectrode},'OffCallback',{@deselectelectrode});

% if numel(options.sides) == 1    % only one hemisphere
%     switch options.sides
%         case 1  % right hemisphere, disable '4' and '7' buttons
%             set(eltog(3), 'Enable', 'off');
%             set(eltog(4), 'Enable', 'off')
%         case 2  % left hemisphere, disable '0' and '3' buttons
%             set(eltog(1), 'Enable', 'off')
%             set(eltog(2), 'Enable', 'off')
%     end
% end

%xview=uipushtool(ht,'CData',ea_get_icn('elX'),'TooltipString','Set view from X-Direction [X]','ClickedCallback',{@ea_view,'x'});
%yview=uipushtool(ht,'CData',ea_get_icn('elY'),'TooltipString','Set view from Y-Direction [Y]','ClickedCallback',{@ea_view,'y'});

% rotleft=uipushtool(ht,'CData',ea_get_icn('rotleft'),'TooltipString','Rotate Electrode counter-clockwise','ClickedCallback',{@ea_rotate,'cc',mcfig});
% rotright=uipushtool(ht,'CData',ea_get_icn('rotright'),'TooltipString','Rotate Electrode clockwise','ClickedCallback',{@ea_rotate,'c',mcfig});

% rotleftcw=uipushtool(ht,'CData',ea_get_icn('rotleftcw'),'TooltipString','Rotate left lead clockwise','ClickedCallback',{@ea_rotate,'lc',mcfig});
% rotleftccw=uipushtool(ht,'CData',ea_get_icn('rotleftccw'),'TooltipString','Rotate left lead counterclockwise','ClickedCallback',{@ea_rotate,'lcc',mcfig});
autorotation=uipushtool(ht,'CData',ea_get_icn('autorot'),'TooltipString','Detect directional leads (auto mode)','ClickedCallback',{@ea_autorotate,'clockwise',mcfig});
manualrotation=uipushtool(ht,'CData',ea_get_icn('manualrot'),'TooltipString','Detect directional leads (manual mode)','ClickedCallback',{@ea_manualrotate,'clockwise',mcfig});
rotationcw=uipushtool(ht,'CData',ea_get_icn('cw'),'TooltipString','Rotate lead clockwise','ClickedCallback',{@ea_rotate,'clockwise',mcfig});
rotationccw=uipushtool(ht,'CData',ea_get_icn('ccw'),'TooltipString','Rotate lead counterclockwise','ClickedCallback',{@ea_rotate,'counterclockwise',mcfig});
setappdata(mcfig, 'orientationtools', [manualrotation, rotationcw, rotationccw]);
currentOptions = ea_resolve_elspec(options, options.elside);
set([manualrotation, rotationcw, rotationccw], 'Enable', ea_bool2onoff(currentOptions.elspec.isdirected));
if isfield(options, 'elmodels') && (numel(options.elmodels)>2 || numel(unique(options.elmodels))>1)
    autorotation.Enable = 'off';
    manualrotation.TooltipString = 'Set directional lead roll angle (degrees)';
end

% mni=uitoggletool(ht,'CData',ea_get_icn('mninative'),'TooltipString','Toggle MNI vs. Native space','State','off','OnCallback',{@ea_mancor_updatescene,mcfig,'mni'},'OffCallback',{@ea_mancor_updatescene,mcfig,'native'});

finish_mc=uipushtool(ht,'CData',ea_get_icn('done'),'TooltipString','Finish manual corrections [space]','ClickedCallback',{@robotSpace});

captoggle=uitoggletool(ht,'CData',ea_get_icn('labels'),'TooltipString','Orientation','OnCallback',{@objvisible,captions},'OffCallback',{@objinvisible,captions},'State','on');

xt=uitoggletool(ht,'CData',ea_get_icn('xray'),'TooltipString','Toggle X-Ray Mode','State','off','OnCallback',{@xrayon,mcfig},'OffCallback',{@xrayoff,mcfig});
setappdata(mcfig,'xt',xt);

setappdata(mcfig,'eltog',eltog);

elplot=getappdata(mcfig,'elplot');

try
    realcoords_plot=getappdata(mcfig,'realcoords_plot');
end
trajectory_plot=getappdata(mcfig,'trajectory_plot');
planes=getappdata(mcfig,'planes');

%% Manual height correction here:
%set(mcfig,'Position',[10 400 700 500])

drawnow;

disp('Manual correction: Press arrows to adjust, space to end adjustment. For more shortcuts hover over buttons in the menu-bar.');


%% export variables to figure
setappdata(mcfig,'eltog',eltog);


function ea_endfcn(mcfig)
% This subfunction terminates the process of manual correction and saves
% results.
disp('Saving results.');

ea_busyaction('on',mcfig,'reco');
% markers=getappdata(gcf,'markers');
% trajectory=getappdata(gcf,'trajectory');
options=getappdata(mcfig,'origoptions');

options.hybridsave=1;
options.native=1;
options.loadnativereco = 1; % Load native reco intead of scrf
[coords_mm,trajectory,markers]=ea_load_reconstruction(options);
currentOptions = getappdata(mcfig, 'options');
options.elside = currentOptions.elside;
markers = getappdata(mcfig, 'markers');

saveCurrent(mcfig,coords_mm,trajectory,markers,options);
modified = getappdata(mcfig, 'modifiedelectrodes');
if ~isempty(modified)
    options.sides = modified;
    [coords_mm,trajectory,markers]=ea_load_reconstruction(options);
    ea_save_reconstruction(coords_mm,trajectory,markers,options.elmodel,[],options);
end
options=getappdata(mcfig,'origoptions');
try options=rmfield(options,'hybridsave'); end
ea_busyaction('off',mcfig,'reco');
close(mcfig);

if options.autoimprove
    disp('Storing results in template.');
    ea_export_templates(coords_mm{1}(1:4,:),trajectory{1},options.patientname,options,'r')
    ea_export_templates(coords_mm{2}(1:4,:),trajectory{2},options.patientname,options,'l')
    disp('Done.');
end

%% methods dump:
ea_methods(options,...
    ['DBS-Electrodes were manually localized based on post-operative acquisitions using a tool specifically designed for this task (as implemented in Lead-DBS software',...
    '; Horn & Kuehn 2005; SCR_002915; https://www.lead-dbs.org).'],...
    {'Horn, A., & Kuehn, A. A. (2015). Lead-DBS: a toolbox for deep brain stimulation electrode localizations and visualizations. NeuroImage, 107, 127?135. http://doi.org/10.1016/j.neuroimage.2014.12.002'});

% continue with rest of the program schedule..
if options.d2.write || options.d3.write
    if options.atl.genpt % generate patient specific atlas set
        ea_ptspecific_atl(options);
    end
    ea_write(options);
end


function ea_keystr(mcfig,event)
% pause
% commnd=get (gcf, 'CurrentKey');

% get vars
eltog=getappdata(mcfig,'eltog');
elplot=getappdata(mcfig,'elplot');
mplot=getappdata(mcfig,'mplot');
options=getappdata(mcfig,'options');
if ~isfield(options,'visible')
    options.visible=1;
end
if  ~isfile(options.subj.recon.recon)
    close(mcfig);
    return
end

options.loadnativereco = 1;  % Load native reco intead of scrf
[~,~,markers]=ea_load_reconstruction(options);

commnd=event.Character;
switch lower(commnd)
    case ' '
        %markers=getappdata(mcfig,'markers');
        if options.elside==options.sides(end)
            ea_endfcn(mcfig);
            return
        else % Accept this electrode before moving to the next.
            currentCoords = getappdata(mcfig, 'coords_mm');
            currentTrajectory = getappdata(mcfig, 'trajectory');
            currentMarkers = getappdata(mcfig, 'markers');
            saveCurrent(mcfig,currentCoords,currentTrajectory,currentMarkers,options);
            set(0,'CurrentFigure',mcfig);
            setappdata(mcfig,'selectrode',0);
            [~,ix]=ismember(options.elside,options.sides);
            options.elside=options.sides(ix+1);
            setappdata(mcfig,'options',options);
            ea_mancor_updatescene([],[],mcfig);
        end
    case '.' % center selected electrode - this doesn't seem to work yet.
        selectrode=getappdata(mcfig,'selectrode');
        if selectrode

            optoffsets=getappdata(mcfig,'optoffsets');
            [coords_mm,trajectory,markers,elmodel]=ea_load_reconstruction(options);
            movedcoords=moveonecoord(markers,selectrode,optoffsets(selectrode,:),options); % move the correct coord to the correct direction.

            markers = movedcoords;
            set(mplot(1,1),'XData',movedcoords(options.elside).head(1),'YData',movedcoords(options.elside).head(2),'ZData',movedcoords(options.elside).head(3))
            set(mplot(2,1),'XData',movedcoords(options.elside).tail(1),'YData',movedcoords(options.elside).tail(2),'ZData',movedcoords(options.elside).tail(3))
            %            setappdata(mcfig,'markers',markers);
            saveCurrent(mcfig,coords_mm,trajectory,markers,options);
            ea_mancor_updatescene([],[],mcfig);
        end
    case '<' % move to previous electrode in batch
        sequenceelectrode([],[],mcfig,'prev');
    case '>' % move to next electrode in batch
        sequenceelectrode([],[],mcfig,'next')
        %     case {'x','a','p','y','l','r'} % view angles.
        %         %markers=getappdata(mcfig,'markers');
        %         ea_view(nan,nan,commnd);
    case 'h'
        showhidefid([],[],mcfig);
    case 'x'
        xrayswitch([],[],mcfig);
    case {'0','3','4','7'}
        switch lower(commnd)
            case {'0','4'}
                selectrode=1;
            case {'3','7'}
                selectrode=2;
        end

        oselectrode=getappdata(mcfig,'selectrode');
        if selectrode==oselectrode % toggle had already been clicked -> deselect all.
            % reset all toggletools
            for i=1:2
                set(eltog(i),'State','off');
            end
            setappdata(mcfig,'selectrode',0);
            ea_mancor_updatescene([],[],mcfig);
        else
            % clear all toggletools.
            for i=1:2
                set(eltog(i),'State','off');
            end

            % set the correct toggletool again.
            set(eltog(selectrode),'State','on');

            % store selected electrode in appdata.
            setappdata(mcfig,'selectrode',selectrode);
            ea_mancor_updatescene([],[],mcfig);
        end
        clear oselectrode
    case {'c','v','b','n'}
        setcontrast(nan,nan,event.Character,event.Modifier,mcfig);
        %     case 'v'
        %         increasecontrast(nan,nan,event);
        %     case 'b'
        %         increaseoffset(nan,nan,event);
        %     case 'n'
        %         decreaseoffset(nan,nan,event);

    case {'s','d'}

    case 'm' % Set the current electrode's fiducials in native millimeters.
        side = options.elside;
        answer = inputdlg({'Head XYZ (mm):', 'Tail XYZ (mm):'}, ...
            sprintf('Electrode %d fiducials', side), [1, 60], ...
            {num2str(markers(side).head, '%.4f '), num2str(markers(side).tail, '%.4f ')});
        if isempty(answer)
            return;
        end
        head = sscanf(answer{1}, '%f')';
        tail = sscanf(answer{2}, '%f')';
        if numel(head) ~= 3 || numel(tail) ~= 3 || any(~isfinite([head, tail])) || isequal(head, tail)
            errordlg('Enter two distinct finite XYZ coordinates.', 'Electrode fiducials');
            return;
        end
        [coords_mm, trajectory, markers, elmodel] = ea_load_reconstruction(options);
        delta = head - markers(side).head;
        markers(side).head = head;
        markers(side).tail = tail;
        markers(side).x = markers(side).x + delta;
        markers(side).y = markers(side).y + delta;
        saveCurrent(mcfig,coords_mm,trajectory,markers,options);
        ea_mancor_updatescene([],[],mcfig);
    otherwise % arrow keys, plus, minus
        if ismember(event.Key,{'rightarrow','leftarrow','uparrow','downarrow'}) || ismember(event.Character,{'+','-','*','_'})
            selectrode=getappdata(mcfig,'selectrode');
            if ~selectrode % no electrode is highlighted, move electrodes alongside trajectory or increase/decrease spacing.
                [coords_mm,trajectory,markers,elmodel,manually_corrected]=ea_load_reconstruction(options);

                markers=ea_correctcoords(markers,trajectory,event,options);
                if isfield(options,'hybridsave')
                    options=rmfield(options,'hybridsave');
                end
                saveCurrent(mcfig,coords_mm,trajectory,markers,options);

                ea_mancor_updatescene([],[],mcfig);
                [coords_mm,trajectory,markers,elmodel,manually_corrected]=ea_load_reconstruction(options);

            else % electrode is highlighted. Move in xy dirs.
                [coords_mm,trajectory,markers,elmodel,manually_corrected]=ea_load_reconstruction(options);
                movedcoords=moveonecoord(markers,selectrode,event,options); % move the correct coord to the correct direction.

                markers = movedcoords;
            set(mplot(1,1),'XData',movedcoords(options.elside).head(1),'YData',movedcoords(options.elside).head(2),'ZData',movedcoords(options.elside).head(3))
                set(mplot(2,1),'XData',movedcoords(options.elside).tail(1),'YData',movedcoords(options.elside).tail(2),'ZData',movedcoords(options.elside).tail(3))

                saveCurrent(mcfig,coords_mm,trajectory,markers,options);

                ea_mancor_updatescene([],[],mcfig);

                [coords_mm,trajectory,markers,elmodel,manually_corrected]=ea_load_reconstruction(options);
            end
        end
end

drawnow


function showhidefid(m,n,mcfig)
options=getappdata(mcfig,'options');
if options.visible
    hidefid([],[],mcfig);
else
    showfid([],[],mcfig);
end


function hidefid(m,n,mcfig)
options=getappdata(mcfig,'options');
options.visible=0;
hf=getappdata(mcfig,'hf');
setappdata(mcfig,'options',options);
ea_mancor_updatescene([],[],mcfig);
set(hf,'State','on');


function showfid(m,n,mcfig)
options=getappdata(mcfig,'options');
options.visible=1;
hf=getappdata(mcfig,'hf');
setappdata(mcfig,'options',options);
ea_mancor_updatescene([],[],mcfig);
set(hf,'State','off');


function xrayswitch(hf,t,mcfig)
options=getappdata(mcfig,'options');
if options.xray
    xrayoff(hf,t,mcfig);
else
    xrayon(hf,t,mcfig);
end


function xrayoff(hf,t,mcfig)
options=getappdata(mcfig,'options');
options.xray=0;
xt=getappdata(mcfig,'xt');
setappdata(mcfig,'options',options);
ea_mancor_updatescene([],[],mcfig);
set(xt,'State','off');


function xrayon(hf,t,mcfig)
options=getappdata(mcfig,'options');
options.xray=1;
xt=getappdata(mcfig,'xt');
setappdata(mcfig,'options',options);
ea_mancor_updatescene([],[],mcfig);
set(xt,'State','on');


function sequenceelectrode(m,n,mcfig,what)
options=getappdata(mcfig,'options');
switch what
    case 'next'
        [~,ix]=ismember(options.elside,options.sides);
        if ix<length(options.sides)
            setappdata(mcfig,'selectrode',0);
            options.elside=options.sides(ix+1);
            setappdata(mcfig,'options',options);
            ea_mancor_updatescene([],[],mcfig);
        end
    case 'prev'
        [~,ix]=ismember(options.elside,options.sides);
        if ix>1
            setappdata(mcfig,'selectrode',0);
            options.elside=options.sides(ix-1);
            setappdata(mcfig,'options',options);
            ea_mancor_updatescene([],[],mcfig);
        end
end


function sp=getsuplots(sides)
if isequal(sides,[1:2])
    sp=1:4;
elseif isequal(sides,1)
    sp=1:2;
elseif isequal(sides,2)
    sp=3:4;
end


function markers=moveonecoord(markers,selectrode,command,options)

grone=[0.02,0.1,1]; % step-sizes

movedcoords=[markers(options.elside).head;markers(options.elside).tail];

if isnumeric(command)
    movedcoords(selectrode,:)=movedcoords(selectrode,:)+[command,0];
else
    switch command.Key
        case 'leftarrow'
            movedcoords(selectrode,1)=movedcoords(selectrode,1)-grone(2+ismember('shift',command.Modifier)-ismember('alt',command.Modifier));
        case 'rightarrow'
            movedcoords(selectrode,1)=movedcoords(selectrode,1)+grone(2+ismember('shift',command.Modifier)-ismember('alt',command.Modifier));
        case 'uparrow'
            movedcoords(selectrode,2)=movedcoords(selectrode,2)+grone(2+ismember('shift',command.Modifier)-ismember('alt',command.Modifier));
        case 'downarrow'
            movedcoords(selectrode,2)=movedcoords(selectrode,2)-grone(2+ismember('shift',command.Modifier)-ismember('alt',command.Modifier));
    end
end
markers(options.elside).head=movedcoords(1,:);
markers(options.elside).tail=movedcoords(2,:);


function objvisible(hobj,ev,atls)
set(atls, 'Visible', 'on');
%disp([atls,'visible clicked']);


function objinvisible(hobj,ev,atls)
set(atls, 'Visible', 'off');
%disp([atls,'invisible clicked']);


function ea_rotate(~,~,ccw,mcfig)
% rotation=getappdata(gcf,'rotation'); % rotation angle in degrees
% 
% if isempty(rotation)
%     rotation{1} = 0;
%     rotation{2} = 0;
% end
% sideact = options.elside;
% switch ccw
%     case 'clockwise'
%         rotation{sideact} = rotation{sideact} + 15;
%     case 'counterclockwise'
%         rotation{sideact} = rotation{sideact} - 15;
% end
% setappdata(gcf,'rotation',rotation);

%% new orientation workflow
if isnumeric(ccw)
    deltaRoll = ccw;
else
switch ccw
    case 'clockwise'
        deltaRoll = 15;
    case 'counterclockwise'
        deltaRoll = -15;
end
end
deltaRoll = mod(deltaRoll, 360);
options = getappdata(mcfig,'options');
options = ea_resolve_elspec(options, options.elside);
load(options.subj.recon.recon,'reco');
reco.angles.orientationmethod{options.elside} = 'manual';
save(options.subj.recon.recon,'reco');
if deltaRoll == 0
    return;
end
head = reco.native.markers(options.elside).head;
tail = reco.native.markers(options.elside).tail;
y = reco.native.markers(options.elside).y;
z = tail(:) - head(:);
z = z / norm(z);
% vector to rotate
yvec = y(:)-head(:);
% angle
theta = deg2rad(deltaRoll);

% Rodrigues rotation
yrot = (yvec*cos(theta) + ...
    cross(z,yvec)*sin(theta) + ...
    z*dot(z,yvec)*(1-cos(theta)))';

%%
[xunitv, yunitv] = ea_calcxy(head, tail, yrot);
ynew = head + yunitv * (options.elspec.lead_diameter / 2);
xnew = head + xunitv * (options.elspec.lead_diameter / 2);
reco.native.markers(options.elside).y = ynew;
reco.native.markers(options.elside).x = xnew;

%% for direct saving into manual reconstruction
calculation = options;
calculation.sides = options.elside;
[coords,trajectory,markers]=ea_resolvecoords(reco.native.markers,calculation);
saveCurrent(mcfig,coords,trajectory,markers,options)
ea_mancor_updatescene([],[],mcfig);


function ea_autorotate(hobj,ev,ccw,mcfig)
options = getappdata(gcf,'options');
ea_diode_main(options);
figure(mcfig);
ea_mancor_updatescene([],[],mcfig);


function ea_manualrotate(hobj,ev,ccw,mcfig)
options = getappdata(mcfig,'options');
if isfield(options, 'elmodels') && (numel(options.elmodels)>2 || numel(unique(options.elmodels))>1)
    saved = load(options.subj.recon.recon, 'reco');
    currentRoll = saved.reco.angles.native(options.elside).roll;
    answer = inputdlg('Native roll angle (degrees):', ...
        sprintf('Electrode %d orientation', options.elside), [1,60], {num2str(currentRoll)});
    if isempty(answer), return; end
    angle = str2double(answer{1});
    if ~isfinite(angle)
        errordlg('Enter a finite roll angle in degrees.', 'Electrode orientation');
        return;
    end
    ea_rotate(hobj,ev,angle-currentRoll,mcfig);
    return;
end
before = getappdata(mcfig, 'markers');
options.sides = options.elside;
ea_diode_manual_main(options);
figure(mcfig);
ea_mancor_updatescene([],[],mcfig);
after = getappdata(mcfig, 'markers');
side = options.elside;
if ~isequaln([before(side).head;before(side).tail;before(side).x;before(side).y], ...
        [after(side).head;after(side).tail;after(side).x;after(side).y])
    setappdata(mcfig, 'modifiedelectrodes', unique([getappdata(mcfig, 'modifiedelectrodes'), side]));
end


function setcontrast(hobj,ev,key,modifier,mcfig)
% c_lims=getappdata(gcf,'c_lims');
% comms={'v','c','b','n'}; % key commands
% perfs=[1 -1 % actions to perform on key commands
%       -1 1
%        1 1
%       -1 -1];
% kern=(c_lims(2)-c_lims(1))/20; % gain to correct contrast
%
doshift=any(ismember('shift',modifier));
% c_lims=c_lims+(perfs(ismember(comms,lower(key)),:)*(kern*(doshift+1)));
% setappdata(gcf,'c_lims',c_lims);
doshift=1+doshift*4;
% new code:
contrast=getappdata(mcfig,'contrast');
offset=getappdata(mcfig,'offset');
grain=0.1;

switch lower(key)
    case 'v'
        contrast=contrast+grain*doshift;
    case 'c'
        contrast=contrast-grain*doshift;
    case 'b'
        offset=offset-grain*doshift*2;
    case 'n'
        offset=offset+grain*doshift*2;
end
% if offset<=0
%     offset=0;
% end
if contrast<0.1
    contrast=0.1;
end
setappdata(mcfig,'contrast',contrast);
setappdata(mcfig,'offset',offset);
%disp(['Contrast: ',num2str(contrast),', Offset: ',num2str(offset),'.']);
ea_mancor_updatescene([],[],mcfig);


function selectelectrode(hobj,ev)
% reset all toggletools
warning ('off','all');
eltog=getappdata(gcf,'eltog');
elplot=getappdata(gcf,'elplot');
mplot=getappdata(gcf,'mplot');
options=getappdata(gcf,'options');
set(mplot(1,1),'MarkerEdgeColor','r');
set(mplot(2,1),'MarkerEdgeColor','g');

for i=getsuplots(1)
    set(eltog(i),'State','off');
    if eltog(i)==hobj
        selectrode=i;
    end
end
if ~exist('selectrode','var')
    return
end

% set the clicked toggletool again.
set(eltog(selectrode),'State','on');

set(mplot(selectrode),'MarkerEdgeColor','y');

% store selected electrode in appdata.
setappdata(gcf,'selectrode',selectrode);
warning ('off','all');


function deselectelectrode(hobj,ev)
% reset all toggletools
mplot=getappdata(gcf,'mplot');
set(mplot(1,1),'MarkerEdgeColor','r');
set(mplot(2,1),'MarkerEdgeColor','g');

setappdata(gcf,'selectrode',0);


function robotSpace(hobj,ev) % simulates key presses using Java.
import java.awt.Robot;
import java.awt.event.*;
SimKey=Robot;
SimKey.keyPress(KeyEvent.VK_SPACE)
SimKey.keyRelease(KeyEvent.VK_SPACE)


function saveCurrent(mcfig,coords_mm,trajectory,markers,options)
% Save native edits and defer propagation until Finish.
if isfield(options, 'hybridsave')
    options = rmfield(options, 'hybridsave');
end
changed = ea_save_reconstruction(coords_mm,trajectory,markers,options.elmodel,1,options);
setappdata(mcfig, 'modifiedelectrodes', unique([getappdata(mcfig, 'modifiedelectrodes'), changed]));
