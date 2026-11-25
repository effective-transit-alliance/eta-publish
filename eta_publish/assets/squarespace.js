// What Squarespace's site script, `site-bundle.js`, reads from a page before it runs,
// which a live page sets before it, and `report.squarespace.html` sets here.

// The site's settings, of which the script needs only these two
// to make the header what etany.org's is: fixed, and scrolling back,
// so hidden as the reader scrolls down and shown again as they scroll up.
// Without `Static`, the script stops at its first line and does nothing.
// As a live page gives them, on 2026-11-25.
window.Static = {
    SQUARESPACE_CONTEXT: {
        tweakJSON: {
            "tweak-fixed-header": "true",
            "tweak-fixed-header-style": "Scroll Back",
        },
    },
};

// A stand-in for `Y`, the event bus a live page has from the YUI library it loads,
// with each method the script calls on it, each doing nothing.
// It is here for one thing: the script sets up a shop's product Quick View
// by calling `Y.Global.on` with no check that `Y` is there,
// and without it logs `Error initializing QuickView`, which a live page does not.
// The site has no shop, so nothing it sets up there is ever used.
// Every other use checks for `Y.Global` and is skipped without it;
// with it, the header and each section subscribe to events with `on` and `after`,
// and the header announces its height with `fire`.
// Nothing else on this page publishes or listens on that bus,
// so with each doing nothing, the header hides, shows, and opens its menu exactly as without it.
window.Y = {
    Global: {
        on() {},
        after() {},
        fire() {},
        detach() {},
    },
};
