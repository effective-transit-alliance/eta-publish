// What `svgo` does to the logo, for `scripts/build-logo.sh`.
//
// Only what Inkscape leaves behind for itself:
// its editor state, its comment, and the IDs nothing references.
// Nothing here changes what is drawn.
export default {
  plugins: [
    "removeXMLProcInst",
    "removeComments",
    "removeMetadata",
    "removeEditorsNSData",
    "cleanupIds",
    "removeUnusedNS",
  ],
};
