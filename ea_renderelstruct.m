function [el_render, el_label, elSide] = ea_renderelstruct(options,resultfig,elstruct,pt,el_render,el_label)
% Wrapper function to render lead trajectories based on elstruct
if ~exist('elstruct','var')
    [coords_mm,trajectory,markers] = ea_load_reconstruction(options);
    elstruct(1).coords_mm = coords_mm;
    elstruct(1).trajectory = trajectory;
    elstruct(1).name = options.patientname;
    elstruct(1).markers = markers;
end

if ~exist('pt','var')
    pt = 1;
end

popts = options;
if strcmp(options.leadprod,'group')
    popts.nowrite = 1; % Group visualization must not rewrite subject reconstructions.
    [popts.root, popts.patientname] = fileparts(options.patient_list{pt});
    popts.root = [popts.root, filesep];
    popts.subj.recon.recon = fullfile(options.patient_list{pt}, 'reconstruction', ...
        [popts.patientname, '_desc-reconstruction.mat']);
    popts.sides = find(~cellfun(@(c) isempty(c) || all(isnan(c(:))), elstruct(pt).coords_mm));
end

elSide = popts.sides;
if strcmp(options.leadprod, 'dbs')
    reconstruction = load(options.subj.recon.recon, 'reco');
end

for side=elSide
    pobj = struct;
    try
        pobj = ea_load_electrode(popts.subj.recon.recon, side);
        pobj.hasPlanning = 1;
        pobj.showPlanning = strcmp(options.leadprod,'or');
    end
    pobj.pt = pt;
    pobj.options = popts;
    pobj.elstruct = elstruct(pt);
    pobj.showMacro = 1;
    pobj.side = side;
    if strcmp(options.leadprod, 'dbs')
        pobj.elmodel = reconstruction.reco.props(side).elmodel;
        pobj.elstruct.elmodel = pobj.elmodel;
        if isfield(reconstruction.reco.props, 'labels')
            pobj.elstruct.labels = {reconstruction.reco.props.labels};
        end
    elseif strcmp(options.leadprod, 'group') && isfield(elstruct, 'elmodels')
        pobj.elmodel = elstruct(pt).elmodels{side};
        pobj.elstruct.elmodel = pobj.elmodel;
    end

    set(0,'CurrentFigure',resultfig);
    if ~exist('el_render','var') || ~isobject(el_render)
        el_render = struct([]);
    end
    if ~strcmp(options.leadprod, 'dbs') && isfield(options, 'reconmethod') && isequal(options.reconmethod, 'LeGUI (Davis 2021)')
%         ea_trajectory(pobj); % Option for if you want to visualize the
%         actual electrodes as opposed to spheres
        ea_trajectory_seeg(elstruct, options);
        stub = struct('ellabel', 'SEEG');
        if isempty(el_render)
            el_render = stub;
        else
            el_render(end+1) = stub;
        end
    else
        if isempty(el_render)
            el_render = ea_trajectory(pobj);
        else
            el_render(end+1) = ea_trajectory(pobj);
        end
    end
    
    if ~exist('el_label','var')
        try
            el_label = el_render(end).ellabel;
        catch
            el_label = 'SEEG';
        end
    else
        try
            el_label(end+1) = el_render(end).ellabel;
        catch
            if iscell(el_label)
                el_label{end+1} = 'SEEG';
            else
                el_label = [el_label, 'SEEG'];
            end
        end
    end
end
