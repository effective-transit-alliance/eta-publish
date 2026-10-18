// What `svgo` does to the logo, for `logo.py`.
//
// Its default optimizations, which drop what Inkscape leaves behind for itself,
// merge paths, apply transforms to the coordinates they move,
// and write path data compactly, with every number rounded to two decimals:
// a hundredth of a unit in a logo 40 units across, finer than any screen draws it.
//
// Styles become attributes first: Inkscape writes a `stroke-width` into the style
// of shapes that have no stroke, and while it is there `svgo` leaves their transforms alone,
// which kept the icons thousands of units across and their coordinates as long.
//
// The `width` and `height` are dropped, since a chart says how big to draw it;
// the `viewBox`, which is what lets it scale, `svgo` keeps.
export default {
  multipass: true,
  floatPrecision: 2,
  plugins: [
    "convertStyleToAttrs",
    "preset-default",
    "removeDimensions",
  ],
};
