(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) {
    root.razSortPrices = api.razSortPrices;
    root.razIsStalePrice = api.razIsStalePrice;
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  function razIsStalePrice(value, now = Date.now()) {
    return Boolean(
      value?.checkedAt &&
      now - new Date(value.checkedAt).getTime() > 7 * 24 * 60 * 60 * 1000,
    );
  }

  function razValidateVerifiedObservation(row, now = Date.now()) {
    if (!row || row.verification_status !== 'verified') return null;
    const id = String(row.product_id || '');
    const price = Number(row.price);
    const currency = String(row.currency || '').toUpperCase();
    const checked = Date.parse(row.checked_at || '');
    if (
      !id ||
      !Number.isFinite(price) ||
      price < 0 ||
      !/^[A-Z]{3}$/.test(currency) ||
      !Number.isFinite(checked) ||
      checked > now
    ) return null;
    return {
      ...row,
      product_id: id,
      price,
      currency,
      checked_at: new Date(checked).toISOString(),
    };
  }

  function razSortPrices(items, priceFor, mode, currency) {
    if (mode === 'default') return [...items];
    if (!currency) return [...items];
    return [...items].sort((a, b) => {
      const av = priceFor(a), bv = priceFor(b);
      const rank = value => {
        if (!value) return 3;
        if (value.verified && !razIsStalePrice({checkedAt: value.checkedAt})) return 0;
        if (value.verified) return 1;
        return 2;
      };
      const ar = rank(av), br = rank(bv);
      if (ar !== br) return ar - br;
      if (av?.currency !== currency || bv?.currency !== currency) {
        if (av?.currency === currency && bv?.currency !== currency) return -1;
        if (av?.currency !== currency && bv?.currency === currency) return 1;
      }
      if (!av && !bv) return 0;
      if (!av) return 1;
      if (!bv) return -1;
      return mode === 'asc' ? av.price - bv.price : bv.price - av.price;
    });
  }

  return {razSortPrices, razIsStalePrice, razValidateVerifiedObservation};
});
