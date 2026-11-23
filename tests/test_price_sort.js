const assert = require('node:assert/strict');
const {razSortPrices, razIsStalePrice} = require('../scripts/price-sort.js');

const prices = new Map([
  ['verified-high', {price: 200, currency: 'ILS', verified: true}],
  ['verified-low', {price: 100, currency: 'ILS', verified: true}],
  ['fallback', {price: 50, currency: 'ILS', verified: false}],
  ['missing', null],
]);
const items = [...prices.keys()].map(id => ({id}));
const getPrice = item => prices.get(item.id);

assert.deepEqual(
  razSortPrices(items, getPrice, 'asc').map(item => item.id),
  ['verified-low', 'verified-high', 'fallback', 'missing'],
);
assert.deepEqual(
  razSortPrices(items, getPrice, 'desc').map(item => item.id),
  ['verified-high', 'verified-low', 'fallback', 'missing'],
);
assert.equal(
  razIsStalePrice({checkedAt: '2026-01-01T00:00:00Z'}, Date.parse('2026-01-09T00:00:01Z')),
  true,
);
assert.equal(
  razIsStalePrice({checkedAt: '2026-01-05T00:00:00Z'}, Date.parse('2026-01-09T00:00:00Z')),
  false,
);
