function apref = ea_antspreset_macaque_d99_deep(cmd)
% Fixed T1-only D99v2 recipe selected by the documented parameter scan.

if ischar(cmd)
    apref = 'Macaque D99v2: Deep Nuclei (T1)';
    return
end

apref.space = 'D99v2';
apref.randomseed = 1;
apref.float = 0;
apref.interpolation = 'Linear';
apref.deepMarginMm = 2;

apref.rigid.gradientstep = '0.1';
apref.rigid.metric = 'MI';
apref.rigid.metricparams = '1,32,Regular,0.25';
apref.rigid.convergence = '[1000x500x250x100,1e-6,10]';
apref.rigid.shrinkfactors = '12x8x4x2';
apref.rigid.smoothingsigmas = '1.5x1x0.5x0.25mm';
apref.affine = apref.rigid;

apref.syn.gradientstep = '0.1,3,0';
apref.syn.metric = 'MI';
apref.syn.metricparams = '1,32,None,1';
apref.syn.convergence = '[100x70x50x20,1e-6,10]';
apref.syn.shrinkfactors = '8x4x2x1';
apref.syn.smoothingsigmas = '1x0.5x0.25x0mm';

apref.scrf.gradientstep = '0.1,3,1';
apref.scrf.metric = 'MI';
apref.scrf.metricparams = '1,32,None,1';
apref.scrf.convergence = '[50x20,1e-6,10]';
apref.scrf.shrinkfactors = '2x1';
apref.scrf.smoothingsigmas = '0.25x0mm';

apref.bootstrap.rigid = apref.rigid;
apref.bootstrap.affine = apref.affine;
apref.bootstrap.syn = apref.scrf;
apref.bootstrap.syn.convergence = '[100x70x50,1e-6,10]';
apref.bootstrap.syn.shrinkfactors = '8x4x2';
apref.bootstrap.syn.smoothingsigmas = '1x0.5x0.25mm';
