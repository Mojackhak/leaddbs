function stimSpec = mh_fiber_stnsnr_stimspec_from_table(rows, label, varargin)
% Build an STN/SNr stimulation spec from workbook-style or normalized rows.

parser = inputParser;
parser.FunctionName = 'mh_fiber_stnsnr_stimspec_from_table';
parser.addParameter('Model', mh_fiber_stnsnr_default_vta_model_key(), ...
    @(x) ischar(x) || isstring(x));
parser.parse(varargin{:});
opts = parser.Results;

if ~istable(rows)
    error('mh_fiber_stnsnr_stimspec_from_table:InvalidRows', ...
        'STN/SNr stimulation rows must be a table.');
end

columns = { ...
    select_column(rows, {'Side', 'side'}, 'side'), ...
    select_column(rows, {'LeadContact', 'lead_contact', 'leadContact'}, 'lead contact'), ...
    select_column(rows, {'Voltage', 'voltage'}, 'voltage'), ...
    select_column(rows, {'PulseWidth', 'pulse_width', 'pulseWidth'}, 'pulse width'), ...
    select_column(rows, {'Frequency', 'frequency'}, 'frequency')};

stimSpec = mh_fiber_stimspec_from_table(rows(:, columns), 'case', ...
    'Label', label, ...
    'Model', char(string(opts.Model)), ...
    'Space', mh_vta_default_config_space(), ...
    'Unit', 'V');
end

function column = select_column(rows, candidates, description)
names = string(rows.Properties.VariableNames);
for i = 1:numel(candidates)
    candidate = string(candidates{i});
    if any(names == candidate)
        column = char(candidate);
        return;
    end
end
error('mh_fiber_stnsnr_stimspec_from_table:MissingColumn', ...
    'STN/SNr stimulation rows are missing the %s column.', description);
end
