function message = mh_fiber_compact_message(message, maxChars)
% Collapse whitespace and truncate long diagnostic messages.

if nargin < 2 || isempty(maxChars)
    maxChars = 500;
end
message = char(string(message));
message = regexprep(message, '\s+', ' ');
if numel(message) > maxChars
    message = [message(1:maxChars), '...'];
end
end
