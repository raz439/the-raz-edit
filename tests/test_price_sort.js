const assert = require('node:assert/strict');
const {razSortPrices, razIsStalePrice, razValidateVerifiedObservation} = require('../scripts/price-sort.js');

const prices = new Map([
  ['verified-high', {price: 200, currency: 'ILS', verified: true}],
  ['verified-low', {price: 100, currency: 'ILS', verified: true}],
  ['fallback', {price: 50, currency: 'ILS', verified: false}],
  ['missing', null],
]);
const items = [...prices.keys()].map(id => ({id}));
const getPrice = item => prices.get(item.id);

assert.deepEqual(
  razSortPrices(items, getPrice, 'asc', '').map(item => item.id),
  items.map(item => item.id),
);
assert.deepEqual(
  razSortPrices(items, getPrice, 'asc', 'ILS').map(item => item.id),
  ['verified-low', 'verified-high', 'fallback', 'missing'],
);
assert.deepEqual(
  razSortPrices(items, getPrice, 'desc', 'ILS').map(item => item.id),
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

const mixed = new Map([
  ['ils', {price: 200, currency: 'ILS', verified: true, checkedAt: '2026-01-08T00:00:00Z'}],
  ['gbp', {price: 10, currency: 'GBP', verified: true, checkedAt: '2026-01-08T00:00:00Z'}],
  ['missing', null],
]);
const mixedItems = [...mixed.keys()].map(id => ({id}));
assert.deepEqual(
  razSortPrices(mixedItems, item => mixed.get(item.id), 'asc', 'ILS').map(item => item.id),
  ['ils', 'gbp', 'missing'],
);

const now = Date.parse('2026-01-09T00:00:00Z');
assert.equal(
  razValidateVerifiedObservation({
    product_id: 'p',
    price: 100,
    currency: 'ils',
    checked_at: '2026-01-08T00:00:00Z',
    verification_status: 'verified',
  }, now)?.currency,
  'ILS',
);
assert.equal(
  razValidateVerifiedObservation({
    product_id: 'p',
    price: 100,
    currency: 'ILS',
    checked_at: '2026-01-10T00:00:00Z',
    verification_status: 'verified',
  }, now),
  null,
);
assert.equal(
  razValidateVerifiedObservation({
    product_id: 'p',
    price: 100,
    currency: 'ILS',
    checked_at: '2026-01-08T00:00:00Z',
    verification_status: 'failed',
  }, now),
  null,
);
