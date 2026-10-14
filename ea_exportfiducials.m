function ea_exportfiducials(options, filename)
% Export RAS contact coordinates with electrode and contact identity.
[coords,~,~,~,~,~,reco] = ea_load_reconstruction(options);
fid = fopen(filename, 'w');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '# Markups fiducial file version = 4.7\n# CoordinateSystem = 0\n');
fprintf(fid, '# columns = id,x,y,z,ow,ox,oy,oz,vis,sel,lock,label,desc,associatedNodeID\n');
row = 0;
for side = options.sides
    for contact = 1:size(coords{side}, 1)
        label = sprintf('E%d_C%d', side, contact);
        if isfield(reco.props, 'labels') && ~isempty(reco.props(side).labels)
            label = sprintf('E%d_%s', side, reco.props(side).labels{contact});
        end
        label = strrep(label, '"', '""');
        fprintf(fid, 'vtkMRMLMarkupsFiducialNode_%d,%.15g,%.15g,%.15g,0,0,0,1,1,1,0,"%s",,vtkMRMLScalarVolumeNode2\n', ...
            row, coords{side}(contact, :), label);
        row = row + 1;
    end
end
end
