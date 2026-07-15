import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia; the theme-detection script (loaded from index.html in a
// real browser) and any component code path that queries prefers-color-scheme need a stub.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}
