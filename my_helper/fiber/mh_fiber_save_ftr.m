function mh_fiber_save_ftr(ftrSubset, outputMat, referenceNii)
% Save a Lead-DBS FTR subset and optionally export a TrackVis TRK file.

ea_mkdir(fileparts(outputMat));
save(outputMat, '-struct', 'ftrSubset', '-v7.3');

if nargin >= 3 && ~isempty(referenceNii) && isfile(referenceNii) && ~isempty(ftrSubset.idx)
    try
        ea_ftr2trk(outputMat, referenceNii, 0);
    catch ME
        warning('mh_fiber_save_ftr:TrkExportFailed', ...
            'Could not export TRK for %s: %s', outputMat, ME.message);
    end
end

end
