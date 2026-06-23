cd('/Users/mojackhu/Github/leaddbs');
addpath(genpath('/Users/mojackhu/Github/leaddbs'));

cfg = mh_fiber_default_config( ...
    '/Users/mojackhu/Desktop/ASD/derivatives/leaddbs/sub-001', ...
    'clinical_L4R4_5V_L2R2_3V');

mh_fiber_run(cfg);
