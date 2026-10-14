function result = build_stnvo_plus_atlas()
% Build the approved STN/VO expanded seeds without replacing existing data.

atlasDir = fileparts(mfilename('fullpath'));
spec = mh_atlas_load_spec(fullfile(atlasDir, 'specs', 'stnvo_plus.json'));
if isfolder(spec.output_dir) || isfile(spec.output_dir)
    error('build_stnvo_plus_atlas:OutputExists', ...
        'Refusing to replace an existing atlas: %s', spec.output_dir);
end
result = mh_atlas_build_binary_atlas(spec.spec_path, 'Force', false);
if any([result.qc.empty_mask]) || any(~[result.qc.grid_match]) || any(~[result.qc.side_ok])
    error('build_stnvo_plus_atlas:InvalidOutput', ...
        'Atlas masks failed nonempty, reference-grid, or laterality checks.');
end

% MRtrix may change NIfTI transform codes. Retain the exact reference forms.
previousPath = path;
pathCleanup = onCleanup(@() path(previousPath));
addpath(fullfile(spec.repo_dir, 'ext_libs', 'nii_lib'));
referenceHeader = load_untouch_header_only(spec.reference_image);
formFields = {'qform_code', 'sform_code', 'quatern_b', 'quatern_c', ...
    'quatern_d', 'qoffset_x', 'qoffset_y', 'qoffset_z', ...
    'srow_x', 'srow_y', 'srow_z'};
for i = 1:numel(result.records)
    output = result.records(i).output_file;
    nii = load_untouch_nii(output);
    nii.img = uint8(nii.img);
    nii.hdr.dime.datatype = 2;
    nii.hdr.dime.bitpix = 8;
    nii.hdr.dime.scl_slope = 1;
    nii.hdr.dime.scl_inter = 0;
    nii.hdr.dime.pixdim = referenceHeader.dime.pixdim;
    for j = 1:numel(formFields)
        field = formFields{j};
        nii.hdr.hist.(field) = referenceHeader.hist.(field);
    end
    save_untouch_nii(nii, output);
end

overlap = struct([]);
for side = {'lh', 'rh'}
    stn = niftiread(fullfile(spec.output_dir, side{1}, 'STNplus.nii.gz')) > 0;
    vo = niftiread(fullfile(spec.output_dir, side{1}, 'VOplus.nii.gz')) > 0;
    count = nnz(stn & vo);
    item = struct('side', side{1}, 'overlap_voxels', count, ...
        'overlap_mm3', count * prod(referenceHeader.dime.pixdim(2:4)), ...
        'fraction_of_stnplus', count / nnz(stn), ...
        'fraction_of_voplus', count / nnz(vo));
    overlap = [overlap; item]; %#ok<AGROW>
end
result.overlap = struct2table(overlap);
writetable(result.overlap, fullfile(spec.output_dir, 'roi_overlap_qc.csv'));
fid = fopen(result.readme, 'a');
assert(fid >= 0, 'Cannot append atlas construction notes.');
readmeCleanup = onCleanup(@() fclose(fid));
fprintf(fid, '\n## Construction details\n\n');
fprintf(fid, ['STN uses an absolute probability >=0.05. VO uses the original ' ...
    'Voa+Vop values, exactly aligned on their common 0.25 mm lattice, ' ...
    'before the same threshold. Binary masks are resampled with nearest ' ...
    'neighbor to the 0.5 mm reference, then dilated by Euclidean voxel-center ' ...
    'distance <=2 mm. No smoothing, hole filling, additional component ' ...
    'selection, tissue clipping, or overlap subtraction is applied.\n\n']);
fprintf(fid, ['The source Voa was already restricted to its largest component ' ...
    'near probability 0.5. Lower-probability voxels removed from that source ' ...
    'are not restored. These expanded masks are tracking seeds, not pure ' ...
    'anatomical nucleus segmentations.\n\n']);
fprintf(fid, ['Reference qform and sform are preserved. Overlap is retained ' ...
    'and recorded in `roi_overlap_qc.csv`. Lead-DBS display caches are not ' ...
    'copied from the source atlas.\n']);
end
