// What `svgo` does to the logo, for `scripts/build-logo.sh`.
//
// Its default optimizations, which drop what Inkscape leaves behind for itself,
// turn styles into attributes, merge paths, and write path data compactly,
// with every number rounded to two decimals:
// a hundredth of a unit in a logo 40 units across, finer than any screen draws it.
//
// The `width` and `height` are dropped, since a chart says how big to draw it;
// the `viewBox`, which is what lets it scale, `svgo` keeps.
export default {
  multipass: true,
  floatPrecision: 2,
  plugins: [
    "preset-default",
    "removeDimensions",
  ],
};
