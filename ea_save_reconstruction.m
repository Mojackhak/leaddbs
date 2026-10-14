function updatedSides = ea_save_reconstruction(coords_mm,trajectory,markers,elmodel,manually_corrected,options,outFilePath)
updatedSides = [];

if nargin < 7 || isempty(outFilePath)
    outFilePath = options.subj.recon.recon;
end

ea_mkdir(fileparts(outFilePath));

if isfile(outFilePath)
    saved = load(outFilePath, 'reco');
    reco = saved.reco;
else
    reco = struct;
    if isfield(options, 'elmodels')
        for side = 1:numel(options.elmodels)
            reco.props(side).elmodel = options.elmodels{side};
            reco.props(side).manually_corrected = 0;
            if isfield(options, 'elnames') && ~isempty(options.elnames)
                reco.props(side).elname = options.elnames{side};
            end
        end
    end
end
if isequal(manually_corrected, 1) && isfield(options, 'elside')
    options.sides = options.elside;
end
options.elmodel = elmodel;
if options.native
    space = 'native';
else
    space = 'mni';
end
if ~isfield(reco, space)
    count = max(options.sides);
    if isfield(options, 'elmodels')
        count = numel(options.elmodels);
    end
    reco.(space).coords_mm = cell(1, count);
    reco.(space).trajectory = cell(1, count);
    reco.(space).markers = repmat(struct('head', [], 'tail', [], 'x', [], 'y', []), 1, count);
end
for side=options.sides
    electrodeOptions = ea_resolve_elspec(options, side);
    existing = numel(reco.(space).markers) >= side && ~isempty(reco.(space).markers(side).head);
    modelChanged = existing && ~strcmp(strrep(reco.props(side).elmodel, 'St. Jude', 'Abbott'), electrodeOptions.elmodel);
    geometryChanged = ~existing;
    if existing
        previous = reco.(space).markers(side);
        incoming = markers(side);
        geometryChanged = ~isequaln([previous.head;previous.tail;previous.x;previous.y], ...
            [incoming.head;incoming.tail;incoming.x;incoming.y]) || ...
            modelChanged;
    end
    if isequal(manually_corrected, 1) && existing && geometryChanged
        electrodeOptions.sides = side;
        [~, yvec] = ea_calc_rotation(markers(side).y, markers(side).head);
        [xunitv, yunitv] = ea_calcxy(markers(side).head, markers(side).tail, yvec);
        markers(side).x = markers(side).head + xunitv*electrodeOptions.elspec.lead_diameter/2;
        markers(side).y = markers(side).head + yunitv*electrodeOptions.elspec.lead_diameter/2;
        [updatedCoords, updatedTrajectory, markers] = ea_resolvecoords(markers, electrodeOptions, modelChanged);
        coords_mm{side} = updatedCoords{side};
        trajectory{side} = updatedTrajectory{side};
    end
    if geometryChanged
        updatedSides(end+1) = side;
    end
    if modelChanged && isfield(reco.props, 'labels')
        reco.props(side).labels = {};
    end
    reco.props(side).elmodel=electrodeOptions.elmodel;
    if ~isempty(manually_corrected)
        reco.props(side).manually_corrected=manually_corrected;
        if isfield(options, 'elnames') && ~isempty(options.elnames) && ...
                (~strcmp(options.elnames{side}, sprintf('Electrode %d', side)) || ...
                ~isfield(reco.props, 'elname') || isempty(reco.props(side).elname))
            reco.props(side).elname = options.elnames{side};
        end
    end
    reco.(space).coords_mm{side}=coords_mm{side};
    reco.(space).trajectory{side}=trajectory{side};
    if options.native && geometryChanged
        for field = {'x', 'y'}
            vector = markers(side).(field{1}) - markers(side).head;
            markers(side).(field{1}) = markers(side).head + vector/norm(vector)*electrodeOptions.elspec.lead_diameter/2;
        end
    end
    reco.(space).markers(side)=markers(side);
end

if options.native
    save(outFilePath, 'reco');

    if isfield(options,'hybridsave')
        ea_dispt('Warping fiducials to template space');
        ea_reconstruction2mni(options);
        if options.prefs.reco.saveACPC
            ea_dispt('Mapping fiducials to AC/PC space');
            ea_reconstruction2acpc(options);
            ea_dispt('');
        end
        load(outFilePath, 'reco');
        if numel(reco.props) == 2 && numel(unique({reco.props.elmodel})) == 1
            [reco,corrected]=ea_checkswap_lr(reco,options);
        end

        save(outFilePath, 'reco');
        ea_dispt('');
    end
else
    save(outFilePath, 'reco');

    if isfield(options,'hybridsave')
        ea_dispt('Warping fiducials to native space');
        ea_reconstruction2native(options);
        if options.prefs.reco.saveACPC
            ea_dispt('Mapping fiducials to AC/PC space');
            ea_reconstruction2acpc(options);
            ea_dispt('');
        end
        load(outFilePath, 'reco');
        corrected = false;
        if numel(reco.props) == 2 && numel(unique({reco.props.elmodel})) == 1
            [reco,corrected]=ea_checkswap_lr(reco,options);
        end

        save(outFilePath, 'reco');
        ea_dispt('');

        if corrected
            options.hybridsave=1;
            ea_save_reconstruction(reco.mni.coords_mm,reco.mni.trajectory,reco.mni.markers,elmodel,manually_corrected,options)
        end
    end
end

% recalculate angles after ea_save_reconstruction has completed
if isfield(options, 'hybridsave')
    ea_recalc_angles(outFilePath, options.sides);
elseif ~isempty(updatedSides)
    ea_recalc_angles(outFilePath, updatedSides);
end


function [reco,corrected]=ea_checkswap_lr(reco,options)
options.native=0; % this can only be done in MNI space.
corrected=0;
if length(reco.mni.coords_mm)==2 && ~any(cellfun(@isempty,reco.mni.coords_mm))
    if mean(reco.mni.coords_mm{1}(:,1))<mean(reco.mni.coords_mm{2}(:,1)) % RL swapped
        % swap RL:
        options.hybridsave=1;
        ncoords_mm{1}=reco.mni.coords_mm{2};
        ncoords_mm{2}=reco.mni.coords_mm{1};
        ntrajectory{1}=reco.mni.trajectory{2};
        ntrajectory{2}=reco.mni.trajectory{1};
        nmarkers(1)=reco.mni.markers(2);
        nmarkers(2)=reco.mni.markers(1);

        reco.mni.coords_mm=ncoords_mm;
        reco.mni.trajectory=ntrajectory;
        reco.mni.markers=nmarkers;

        ncoords_mm{1}=reco.native.coords_mm{2};
        ncoords_mm{2}=reco.native.coords_mm{1};
        ntrajectory{1}=reco.native.trajectory{2};
        ntrajectory{2}=reco.native.trajectory{1};
        nmarkers(1)=reco.native.markers(2);
        nmarkers(2)=reco.native.markers(1);

        reco.native.coords_mm=ncoords_mm;
        reco.native.trajectory=ntrajectory;
        reco.native.markers=nmarkers;

        corrected=1;
    end
end

vizz=0;

% check that markers are correct (important for directional leads):
if ~reco.props(options.sides(1)).manually_corrected
    options.hybridsave=1;

    for side=options.sides
        if vizz
            figure
            hold on
            plot3(reco.mni.trajectory{side}(:,1),reco.mni.trajectory{side}(:,2),reco.mni.trajectory{side}(:,3),'r-');
            plot3(reco.mni.markers(side).head(:,1),reco.mni.markers(side).head(:,2),reco.mni.markers(side).head(:,3),'y*');
            plot3(reco.mni.markers(side).tail(:,1),reco.mni.markers(side).tail(:,2),reco.mni.markers(side).tail(:,3),'m*');
            plot3(reco.mni.markers(side).x(:,1),reco.mni.markers(side).x(:,2),reco.mni.markers(side).x(:,3),'k*');
            plot3(reco.mni.markers(side).y(:,1),reco.mni.markers(side).y(:,2),reco.mni.markers(side).y(:,3),'g*');
        end

        if reco.mni.markers(side).head(2)>reco.mni.markers(side).y(2) % Flip y marker if head is anterior to y marker.
            reco.mni.markers(side).y=reco.mni.markers(side).head+(reco.mni.markers(side).head-reco.mni.markers(side).y); % 180 deg flip
            corrected=1;
        end

        if reco.mni.markers(side).head(1)>reco.mni.markers(side).x(1) % Flip x marker if head is right to x marker.
            reco.mni.markers(side).x=reco.mni.markers(side).head+(reco.mni.markers(side).head-reco.mni.markers(side).x);
            corrected=1;
        end

        if vizz
            plot3(reco.mni.markers(side).x(:,1),reco.mni.markers(side).x(:,2),reco.mni.markers(side).x(:,3),'ko');
            plot3(reco.mni.markers(side).y(:,1),reco.mni.markers(side).y(:,2),reco.mni.markers(side).y(:,3),'go');
            axis equal
            keyboard
        end
    end
    reco.mni.coords_mm=ea_resolvecoords(reco.mni.markers,options);
end
