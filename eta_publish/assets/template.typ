// ETA report house style.
//
// The emitted `.typ` is a document body that imports this,
// so a change to how reports look is a change to one file rather than to every report.

// No image in the body is taller than this:
// the reports are illustrated at whatever size someone dropped the picture in at,
// and a tall one filled the page on its own.
// The title picture is not capped here: it is sized to the page it has, below.
#let max_image_height = 5.7in

// An image at the width it is given, unless that makes it too tall,
// in which case the height is what is set and the width follows from it.
// `layout` supplies the width to measure against, which differs between
// a figure in the body and one in the title block.
#let capped_image(path, ..args) = layout(size => {
  let full = image(path, width: size.width, ..args)
  if measure(full).height <= max_image_height {
    full
  } else {
    align(center, image(path, height: max_image_height, ..args))
  }
})

#let report(
  // Plain text, for the PDF's metadata, which holds nothing else.
  title: "",
  // The same words with the document's formatting, for the title page.
  headline: none,
  dateline: none,
  contributors: (),
  contributors_note: none,
  hero: none,
  // The standfirst: the document's `Subtitle`-styled paragraph.
  subtitle: none,
  // What a reader of a draft has to be told before reading it.
  // Empty for a published report, which is the state a reader assumes.
  phase: "",
  // What the build has to say about this report, on a page of its own in
  // front of everything, because it is read by whoever is about to publish.
  // A report with nothing wrong with it has no such page,
  // so what publishes still opens on its cover.
  warnings: (),
  body,
) = {
  set document(title: title)
  set page(
    paper: "us-letter",
    margin: (x: 1.4in, y: 1.2in),
    // Footnotes land at the bottom of the page they are cited on,
    // which is the whole reason these reports are typeset
    // rather than printed from the web page.
    footer: context {
      set align(center)
      set text(size: 9pt, fill: luma(40%))
      counter(page).display("1")
    },
  )
  set text(font: ("Libertinus Serif", "Linux Libertine", "Georgia"), size: 11pt, lang: "en")
  set par(justify: true, leading: 0.65em, spacing: 1.2em)
  show link: set text(fill: rgb("#1a4d7a"))

  set heading(numbering: none)
  show heading.where(level: 1): it => {
    set text(size: 15pt, weight: "bold")
    block(above: 1.8em, below: 0.8em, it)
  }
  show heading.where(level: 2): it => {
    set text(size: 12.5pt, weight: "bold")
    block(above: 1.4em, below: 0.6em, it)
  }
  show heading.where(level: 3): it => {
    set text(size: 11pt, weight: "bold", style: "italic")
    block(above: 1.2em, below: 0.5em, it)
  }

  set footnote.entry(separator: line(length: 35%, stroke: 0.5pt + luma(60%)))
  show footnote.entry: set text(size: 8.5pt)
  // Flush left with a space after the number, the way a note is usually set.
  // Typst's own entry indents only its first line, by `indent`,
  // so each note read as a paragraph rather than a note,
  // and puts nothing between the number and the note.
  show footnote.entry: it => {
    let loc = it.note.location()
    let number = numbering(it.note.numbering, ..counter(footnote).at(loc))
    // Still the link back to the reference that the default makes it, but not
    // colored as one, which it was not before either.
    par(first-line-indent: 0em)[#link(loc, text(fill: black, super(number)))~#it.note.body]
  }

  show figure.caption: set text(size: 9pt, fill: luma(35%))
  // Ranged left, as the page sets it.
  // Typst centres a caption by default, which reads as a title under the
  // picture rather than as the sentence about it that it is.
  show figure.caption: it => block(width: 100%, align(left, it))
  show figure: set block(above: 1.6em, below: 1.6em)

  if warnings.len() > 0 {
    // Not in the outline: the contents list what the report contains,
    // and this page is the build talking about it rather than part of it.
    heading(level: 1, outlined: false, [Warnings])
    [Each of these is something to fix in the document before it is published.]
    list(..warnings)
    pagebreak()
  }

  // The title page: a title and a picture, and nothing else on it.
  // The picture is with the title rather than after the contents,
  // because the document puts it under the headline.
  //
  // Its height is whatever the title leaves, rather than a number tuned to one
  // report: a `block(height: 1fr)` is the rest of the page, `layout` inside one
  // is told how much that came to, and a headline that runs to three lines
  // takes its space out of the picture instead of pushing it onto the next page.
  block(height: 100%, width: 100%, stack(
    dir: ttb,
    block(width: 100%)[
      #set align(left)
      // Filled rather than outlined, and labelled: this says the report is a
      // draft, and a reader who misses it reads a draft as published.
      #if phase != "" [
        #block(
          fill: rgb("#c0202a"),
          radius: 2pt,
          inset: (x: 7pt, y: 5pt),
          below: 0.9em,
          text(size: 13pt, weight: "bold", fill: white)[Phase: #phase],
        )
      ]
      #text(size: 21pt, weight: "bold")[#if headline != none { headline } else { title }]
      #if subtitle != none [
        #v(0.6em)
        #text(size: 11.5pt, fill: luma(35%), style: "italic")[#subtitle]
      ]
      #if dateline not in (none, "") [
        #v(0.6em)
        #text(size: 10pt, fill: luma(35%))[#dateline]
      ]
      #v(0.4em)
      #line(length: 100%, stroke: 0.8pt)
    ],
    // A figure's own spacing above it is dropped at the top of a block,
    // which put the rule under the dateline flush against the top of the picture
    // and made it read as a line drawn across the image.
    v(1.2em),
    if hero != none {
      block(height: 1fr, width: 100%, layout(size => {
        let placed = block(width: size.width, hero)
        let height = measure(placed).height
        if height <= size.height or height == 0pt {
          placed
        } else {
          // Caption and all: shrinking only the picture
          // would leave the caption at a size the rest of the report does not use.
          let factor = size.height / height * 100%
          scale(placed, x: factor, y: factor, origin: top + center, reflow: true)
        }
      }))
    },
  ))

  // A page each for the cover and the contents, whatever their length:
  // a report that opened mid-outline read as though it had already started.
  // Explicit rather than `weak`: the break is wanted even when the page is short.
  pagebreak()

  // The report is too long to find a section by turning pages.
  // Typst builds this from the headings, so it cannot disagree with them.
  outline(title: [Table of Contents], depth: 3, indent: auto)

  pagebreak()

  body

  // Credited at the end, not under the title:
  // nine names above the first paragraph read as a masthead rather than a credit.
  if contributors.len() > 0 {
    heading(level: 1, [Contributors])
    if contributors_note != none [#contributors_note]
    list(..contributors)
  }

}
