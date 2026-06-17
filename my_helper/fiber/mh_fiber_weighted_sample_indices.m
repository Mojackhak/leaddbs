function indices = mh_fiber_weighted_sample_indices(weights, sampleCount, randomSeed)
% Sample indices without replacement using non-negative weights.

weights = double(weights(:));
sampleCount = min(max(0, round(sampleCount)), numel(weights));
if nargin >= 3 && ~isempty(randomSeed)
    rng(double(randomSeed), 'twister');
end

indices = zeros(sampleCount, 1);
available = true(numel(weights), 1);
weights(~isfinite(weights) | weights < 0) = 0;

for i = 1:sampleCount
    candidateWeights = weights;
    candidateWeights(~available) = 0;
    totalWeight = sum(candidateWeights);
    if totalWeight <= 0
        remaining = find(available);
        pick = remaining(randi(numel(remaining)));
    else
        threshold = rand() * totalWeight;
        cumulative = cumsum(candidateWeights);
        pick = find(cumulative >= threshold, 1, 'first');
    end
    indices(i) = pick;
    available(pick) = false;
end
end
