function sideIdx = mh_util_side_to_index(sideCode, errorId)
% Convert Lead-DBS side code to side index: R=1, L=2.

if nargin < 2 || strlength(string(errorId)) == 0
    errorId = 'mh_util_side_to_index:InvalidSide';
end

switch upper(char(string(sideCode)))
    case 'R'
        sideIdx = 1;
    case 'L'
        sideIdx = 2;
    otherwise
        error(errorId, 'Invalid side: %s', char(string(sideCode)));
end
end
