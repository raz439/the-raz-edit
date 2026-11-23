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

  function razSortPrices(items, priceFor, mode) {
    return [...items].sort((a, b) => {
      if (mode === 'default') return 0;
      const av = priceFor(a), bv = priceFor(b);
      if (av?.verified !== bv?.verified) return av?.verified ? -1 : 1;
      if (!av && !bv) return 0;
      if (!av) return 1;
      if (!bv) return -1;
      return mode === 'asc' ? av.price - bv.price : bv.price - av.price;
    });
  }

  return {razSortPrices, razIsStalePrice};
});
