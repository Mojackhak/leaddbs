function lead_dbs_to_obj(mat_filename, obj_filename)
% Convert Lead-DBS electrode model to OBJ+MTL format, with each contact
% and each insulation element as a separate object/group.

    %% Load model and prepare filenames
    fprintf('Loading electrode model: %s\n', mat_filename);
    load(mat_filename);  % must populate "electrode" struct

    [objPath, baseName, ~] = fileparts(obj_filename);
    mtl_filename = fullfile(objPath, baseName + '.mtl');

    %% Write MTL
    fid_mtl = fopen(mtl_filename, 'w');
    if fid_mtl == -1
        error('Could not create MTL file: %s', mtl_filename);
    end
    % Dark-gray metal for contacts
    fprintf(fid_mtl, ...
        ['newmtl ContactMat\n'...
         'Ka 0.200000 0.200000 0.200000\n'...
         'Kd 0.400000 0.400000 0.400000\n'...
         'Ks 0.700000 0.700000 0.700000\n'...
         'Ns 200.0\n'...
         'illum 2\n\n']);
    % White translucent plastic for insulation
    fprintf(fid_mtl, ...
        ['newmtl InsulationMat\n'...
         'Ka 0.200000 0.200000 0.200000\n'...
         'Kd 1.000000 1.000000 1.000000\n'...
         'Ks 0.100000 0.100000 0.100000\n'...
         'Ns 10.0\n'...
         'illum 2\n'...
         'd 0.500000\n']);
    fclose(fid_mtl);

    %% Open OBJ and reference MTL
    fid = fopen(obj_filename, 'w');
    if fid == -1
        error('Could not create OBJ file: %s', obj_filename);
    end
    fprintf(fid, '# OBJ file created from Lead-DBS electrode model\n');
    fprintf(fid, '# Created on: %s\n', datestr(now));
    fprintf(fid, 'mtllib %s\n\n', baseName + '.mtl');

    vertex_offset = 0;

    %% Write each contact as separate object and group
    for i = 1:numel(electrode.contacts)
        fprintf(fid, 'o Contact_%d\n', i);
        fprintf(fid, 'g Contact_%d\n', i);
        fprintf(fid, 'usemtl ContactMat\n');

        V = electrode.contacts(i).vertices;
        F = electrode.contacts(i).faces;

        % vertices
        fprintf(fid, 'v %f %f %f\n', V');
        % faces (with offset)
        F = F + vertex_offset;
        fprintf(fid, 'f %d %d %d\n', F');

        vertex_offset = vertex_offset + size(V, 1);
        fprintf(fid, '\n');
    end

    %% Write each insulation as separate object and group
    for i = 1:numel(electrode.insulation)
        fprintf(fid, 'o Insulation_%d\n', i);
        fprintf(fid, 'g Insulation_%d\n', i);
        fprintf(fid, 'usemtl InsulationMat\n');

        V = electrode.insulation(i).vertices;
        F = electrode.insulation(i).faces;

        % vertices
        fprintf(fid, 'v %f %f %f\n', V');
        % faces (with offset)
        F = F + vertex_offset;
        fprintf(fid, 'f %d %d %d\n', F');

        vertex_offset = vertex_offset + size(V, 1);
        fprintf(fid, '\n');
    end

    fclose(fid);
    fprintf('OBJ + MTL files created:\n  %s\n  %s\n', obj_filename, mtl_filename);
end
