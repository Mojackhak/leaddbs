function paths = mh_atlas_write_manifest(spec, records)
% Write CSV and JSON provenance manifests for generated atlas ROIs.

csvPath = fullfile(spec.output_dir, 'roi_manifest.csv');
jsonPath = fullfile(spec.output_dir, 'roi_manifest.json');

if isempty(records)
    error('mh_atlas_write_manifest:NoRecords', 'No records to write.');
end

tbl = struct2table(records);
writetable(tbl, csvPath);

fid = fopen(jsonPath, 'w');
if fid < 0
    error('mh_atlas_write_manifest:JsonOpenFailed', 'Cannot write JSON manifest: %s', jsonPath);
end
cleaner = onCleanup(@() fclose(fid));

payload = struct();
payload.atlas_name = spec.atlas_name;
payload.space = spec.space;
payload.reference_image = spec.reference_image;
payload.output_dir = spec.output_dir;
payload.spec_path = spec.spec_path;
payload.rois = records;

try
    text = jsonencode(payload, PrettyPrint=true);
catch
    text = jsonencode(payload);
end
fprintf(fid, '%s\n', text);

paths = struct('csv', csvPath, 'json', jsonPath);
end
