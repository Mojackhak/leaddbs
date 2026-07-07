function ea_normalize(options)
% Entry function to run normalization

if ~ea_reglocked(options, options.subj.preopAnat.(options.subj.AnchorModality).norm)
    % Setup log
    if options.prefs.diary
        ea_mkdir(fileparts(options.subj.norm.log.logBaseName));
        diary([options.subj.norm.log.logBaseName, char(datetime('now', 'Format', 'yyyyMMdd''T''HHmmss')), '.log']);
    end

    isReApply = ismember(lower(options.normalize.method), lower({'(Re-)apply (priorly) estimated normalization', 'Apply', 'ReApply'}));
    runOptions = options;
    refineContext = [];

    if ~isReApply
        [runOptions, refineContext] = ea_norm_refine_prepare(runOptions);
        if isfield(refineContext, 'cancelled') && refineContext.cancelled
            if options.prefs.diary
                diary off;
            end
            return;
        end

        % Dump method before running normalization, needed by apply functions.
        ea_dumpmethod(runOptions, 'norm');
        ea_norm_refine_update_log(runOptions, refineContext);
    end

    % Do normalization
    switch lower(runOptions.normalize.method)
        case lower({'ANTs (Avants 2008)', 'ANTs'})
            ea_normalize_ants(runOptions);
        case lower({'(Re-)apply (priorly) estimated normalization', 'Apply', 'ReApply'})
            ea_normalize_apply_normalization(runOptions);
        case lower({'FNIRT (Andersson 2010)', 'FNIRT'})
            ea_normalize_fsl(runOptions);
        case lower({'Three-step affine normalization (ANTs; Schonecker 2009)', 'Three-step', 'ThreeStep'})
            ea_normalize_schoenecker(runOptions);
        case lower({'SPM12 DARTEL (Ashburner 2007)', 'SPMDARTEL', 'DARTEL'})
            ea_normalize_spmdartel(runOptions);
        case lower({'SPM12 Segment (Ashburner 2005)', 'SPMSegment', 'Segment'})
            ea_normalize_spmnewseg(runOptions);
        case lower({'SPM12 SHOOT (Ashburner 2011)', 'SPMSHOOT', 'SHOOT'})
            ea_normalize_spmshoot(runOptions);
        case lower({'EasyReg (Iglesias 2023)', 'EasyReg'})
            ea_normalize_easyreg(runOptions);
        case lower({'SynthMorph (Hoffmann 2024)', 'SynthMorph'})
            ea_normalize_synthmorph(runOptions);
        otherwise
            warning('Normalization method not recognized...');
            if options.prefs.diary
                diary off;
            end
            return;
    end

    if ~isReApply && strcmp(refineContext.mode, 'refine')
        ea_norm_refine_finalize(options, runOptions, refineContext);
    end

    % Compute tone-mapped normalized CT
    if strcmp(options.subj.postopModality, 'CT')
        ea_tonemapct(options, 'norm');
    end

    if options.prefs.diary
        diary off;
    end

    if options.overwriteapproved && isfolder(options.subj.brainshiftDir)
        ea_segmask_cleanup(options);
        ea_cprintf('CmdWinWarnings', 'Normalization has been rerun. Please also rerun brain shift correction!\n');
    end
end
end
