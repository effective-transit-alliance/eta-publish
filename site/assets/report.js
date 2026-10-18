(() => {
  const GAP = 8;
  // Long enough to cross the gap into the box, short enough that a box left
  // behind is gone before the reader wonders why it is still there.
  const HOLD = 200;
  // About how long a phone waits before calling a touch a long press.
  const PRESS = 500;
  const closing = new WeakMap();
  // Where an open box came from: while it is open it is a child of `body`
  // rather than of the reference that owns it.
  const home = new WeakMap();
  const built = new WeakMap();
  // A citation's box is built the first time it is wanted, out of the entry it
  // already points at, rather than emitted beside every link. The report cites
  // 113 sources and a copy of each one's address next to each of its citations
  // is 17 KB of a fragment that has 400 KB to fit in. The section is the form
  // that always works; this is the shortcut for a reader who has a pointer.
  const sourceTip = (cited) => {
    const already = built.get(cited) || cited.querySelector(".source-tip");
    if (already) return already;
    const ref = cited.querySelector(".source-ref a");
    const entry =
      ref && document.getElementById(ref.getAttribute("href").slice(1));
    if (!entry) return null;
    const tip = document.createElement("span");
    tip.className = "source-tip";
    tip.setAttribute("aria-hidden", "true");
    // Everything the entry says except the ways back into the text, which from
    // here would lead to the sentence the reader is already reading.
    // The archive goes after the address here: the list puts it first to line
    // it up with the others, and a box has no others to line up with.
    const copy = entry.cloneNode(true);
    // The number first, a link to the entry, so the box is a way there too.
    tip.append(
      ref.cloneNode(true),
      " ",
      copy.querySelector(".source-url"),
      " ",
      copy.querySelector(".source-archived"),
    );
    // Every link in the box is a copy of one the entry has, and the entry is a
    // jump away: the keyboard walks past the copy rather than stopping at it.
    for (const link of tip.querySelectorAll("a")) link.tabIndex = -1;
    cited.append(tip);
    built.set(cited, tip);
    return tip;
  };
  const refOf = (e) => {
    // Not inside a note's box, which is already a box: a citation in there is
    // a copy of one in the note, and its entry is a jump away from both.
    const cited = e.target.closest?.(".eta-report .cited:not(.footnote-tip *)");
    return cited || e.target.closest?.(".eta-report .footnote-ref");
  };
  const tipOf = (e) => {
    // The box itself, which while open is no longer inside the reference:
    // without this the pointer moving into it reads as leaving, and a box the
    // reader is pointing at closes under them.
    const open = e.target.closest?.(".footnote-tip, .source-tip");
    if (open) return open;
    const ref = refOf(e);
    if (!ref) return null;
    if (ref.classList.contains("cited")) return sourceTip(ref);
    return built.get(ref) || ref.querySelector(".footnote-tip");
  };
  const hovers = () => matchMedia("(hover: hover)").matches;
  const place = (event) => {
    // The stylesheet shows this on hover only where the device hovers, and a
    // tap raises hover on a touch screen. Asking the same question here keeps
    // the two from disagreeing.
    if (!hovers()) return;
    const tip = tipOf(event);
    if (!tip) return;
    clearTimeout(closing.get(tip));
    // Already open: the pointer has only moved within the box or back onto
    // the reference, and measuring again would answer the same.
    if (tip.style.position === "fixed") return;
    show(tip);
  };
  const show = (tip) => {
    const from = tip.parentElement;
    const ref = from.getBoundingClientRect();
    // Moved out to the report for as long as it is open, because a box is only
    // as opaque as what it is inside: a figure caption is set at `opacity: .75`
    // and a box within one is composited at .75 too, so the caption shows
    // through the words. An ancestor with `overflow` would clip it, and one
    // with a transform would be what `position: fixed` resolved against.
    //
    // To the report rather than to `body`, because every rule that styles a box
    // is written `.eta-report .source-tip`: outside that div the box keeps its
    // place on the screen and loses its background, which is worse than the
    // caption showing through it.
    home.set(tip, from);
    // Found by its reference while away, or leaving it closes nothing.
    built.set(from, tip);
    // Into the lightbox instead, from a caption in it: the box would be behind
    // the dialog anywhere else.
    (from.closest(".lightbox, .eta-report") || document.body).append(tip);
    // Laid out where it can be measured, and not yet shown there: the handler
    // runs before the frame is painted.
    tip.style.cssText =
      "display:block;visibility:hidden;position:fixed;left:0;top:0;transform:none";
    const box = tip.getBoundingClientRect();
    const below = ref.bottom + GAP;
    const above = ref.top - GAP - box.height;
    // Under it unless that runs off the bottom, and over it only where the
    // box fits: with neither edge free, under is the one that can be scrolled to.
    const top =
      below + box.height <= innerHeight - GAP || above < GAP ? below : above;
    const middle = ref.left + ref.width / 2 - box.width / 2;
    const left = Math.min(Math.max(middle, GAP), innerWidth - box.width - GAP);
    tip.style.cssText = `display:block;position:fixed;left:${left}px;top:${top}px;transform:none`;
  };
  // Handed back to the stylesheet, so that a box measured against one scroll
  // position is not still carrying those numbers at the next one, and put back
  // where it belongs so the reference owns it again. After a pause, because the
  // pointer leaves the reference on its way into the box.
  const release = (event) => {
    // A finger lifting leaves too, and a pressed box stays until a tap.
    if (!hovers()) return;
    const tip = tipOf(event);
    if (!tip) return;
    clearTimeout(closing.get(tip));
    closing.set(
      tip,
      setTimeout(() => close(tip), HOLD),
    );
  };
  const close = (tip) => {
    tip.style.cssText = "";
    home.get(tip)?.append(tip);
  };
  // Where the device does not hover, a long press on a reference opens its
  // box, and a tap anywhere outside the box closes it. Android says a press
  // is long with `contextmenu`; iOS says nothing, so a timer says it there.
  let held = null;
  let pressing = 0;
  let pressed = false;
  const hold = (target) => {
    clearTimeout(pressing);
    const tip = tipOf({ target });
    if (!tip || tip === held) return;
    if (held) close(held);
    show(tip);
    held = tip;
    pressed = true;
  };
  document.addEventListener(
    "touchstart",
    (event) => {
      if (hovers()) return;
      pressed = false;
      if (held && !held.contains(event.target)) {
        close(held);
        held = null;
      }
      if (event.target.closest?.(".footnote-tip, .source-tip") || !refOf(event))
        return;
      clearTimeout(pressing);
      pressing = setTimeout(() => hold(event.target), PRESS);
    },
    { passive: true },
  );
  for (const name of ["touchend", "touchmove", "touchcancel"]) {
    document.addEventListener(name, () => clearTimeout(pressing), {
      passive: true,
    });
  }
  document.addEventListener("contextmenu", (event) => {
    if (
      hovers() ||
      event.target.closest?.(".footnote-tip, .source-tip") ||
      !refOf(event)
    )
      return;
    event.preventDefault();
    hold(event.target);
  });
  // The press that opened the box is not also a tap on the link.
  document.addEventListener(
    "click",
    (event) => {
      if (!pressed) return;
      pressed = false;
      event.preventDefault();
      event.stopPropagation();
    },
    true,
  );
  // An embed is a card until the reader asks for the player: the card is a
  // link to the post, and the click is what swaps it for the platform's own
  // frame. Nothing of the platform's loads before then.
  let frames = 0;
  document.addEventListener("click", (event) => {
    if (
      event.button ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    const card = event.target.closest?.(
      ".eta-report .embed[data-player] .embed-card",
    );
    if (!card) return;
    const figure = card.closest(".embed");
    // YouTube's player refuses a page that sends no `Referer`, with "Error
    // 153", and a page opened as a file sends none: there the card stays the
    // link to the video it already is, opened in a new tab so the report stays.
    event.preventDefault();
    if (
      location.protocol === "file:" &&
      figure.classList.contains("embed-youtube")
    ) {
      open(card.href, "_blank", "noopener");
      return;
    }
    const frame = document.createElement("iframe");
    // Bluesky's frame says how tall its post is only to a frame that gave it
    // an id to say it with.
    const id = String(++frames);
    const player = figure.dataset.player;
    frame.src = figure.classList.contains("embed-bluesky")
      ? `${player}?id=${id}`
      : player;
    frame.dataset.frame = id;
    frame.title = figure.dataset.title || "";
    frame.className = "embed-frame";
    frame.allow = "autoplay; encrypted-media; fullscreen; picture-in-picture";
    frame.allowFullscreen = true;
    card.replaceWith(frame);
    frame.focus();
  });
  // A post is as tall as what it says, which only the frame knows: X and
  // Bluesky each send it up in their own words.
  addEventListener("message", (event) => {
    let data = event.data;
    if (typeof data === "string") {
      try {
        data = JSON.parse(data);
      } catch {
        return;
      }
    }
    for (const frame of document.querySelectorAll(".eta-report .embed-frame")) {
      if (frame.contentWindow !== event.source) continue;
      const resize = data?.["twttr.embed"];
      const height =
        resize?.method === "twttr.private.resize"
          ? resize.params?.[0]?.height
          : data?.height;
      if (Number.isFinite(height) && height > 0)
        frame.style.height = `${height}px`;
    }
  });
  // An underline in the headline is drawn as a swoosh, one curve under each
  // line the underlined words fall on, measured rather than styled: a curve
  // the stylesheet hangs off the words is one curve, and words that wrap
  // need one per line. Drawn again whenever the headline changes shape,
  // which is what moves the words from one line to another.
  const swoosh = (title) => {
    for (const old of title.querySelectorAll(".swoosh")) old.remove();
    // Underlined words that wrap are kept to one line when they fit on one,
    // moving them down together, as one curve rather than two short ones.
    for (const words of title.querySelectorAll("u")) {
      words.style.whiteSpace = "";
      if (words.getClientRects().length < 2) continue;
      words.style.whiteSpace = "nowrap";
      if (words.getBoundingClientRect().width > title.clientWidth)
        words.style.whiteSpace = "";
    }
    const box = title.getBoundingClientRect();
    for (const words of title.querySelectorAll("u")) {
      for (const line of words.getClientRects()) {
        const curve = document.createElement("span");
        curve.className = "swoosh";
        curve.setAttribute("aria-hidden", "true");
        curve.style.left = `${line.left - box.left}px`;
        curve.style.top = `${line.bottom - box.top}px`;
        curve.style.width = `${line.width}px`;
        title.append(curve);
      }
    }
    title.classList.add("swooshed");
  };
  // After the page has been read rather than now: in the fragment this script
  // comes before the report it is for.
  const swooshAll = () => {
    for (const title of document.querySelectorAll(".eta-report #title")) {
      if (!title.querySelector("u")) continue;
      swoosh(title);
      new ResizeObserver(() => swoosh(title)).observe(title);
      // A web font arriving rewraps the words without always resizing the
      // headline.
      document.fonts?.ready.then(() => swoosh(title));
    }
  };
  // A picture opens in a lightbox, at `#/media/` and the figure's id, so that it can
  // be linked to and the browser's back and forward open and close it. The
  // address is the state: everything here changes the address and then shows
  // whatever it says. Stepping to the next picture replaces the entry rather
  // than adding one, so back closes the box rather than walking the pictures.
  // Built out of the figure the link is in, so the markup carries nothing
  // more: without the script the link is to the original, as it was.
  // Wikipedia's form, `File:` and all.
  const MEDIA = "#/media/File:";
  // A picture, a drawing (an SVG, which is its own original), or a video:
  // not an embed, whose player is the platform's.
  const mediaOf = (figure) =>
    figure.querySelector(
      ":scope > .full-size picture, :scope > img, :scope > video",
    );
  const figures = () =>
    [...document.querySelectorAll(".eta-report figure[id]")].filter(mediaOf);
  // The file the figure shows, as the original's name, extension and all, the
  // way Wikipedia names one: what the address says, and what the reader would
  // save it as.
  const originalOf = (figure) => {
    const media = mediaOf(figure);
    return (
      figure.querySelector(":scope > .full-size")?.href ||
      media.currentSrc ||
      media.src ||
      media.querySelector("img").src
    );
  };
  const fileOf = (figure) =>
    decodeURIComponent(new URL(originalOf(figure)).pathname.split("/").pop());
  let lightbox = null;
  let shown = null;
  const go = (figure, replace) => {
    const url = figure
      ? MEDIA + encodeURIComponent(fileOf(figure))
      : location.pathname + location.search;
    history[replace ? "replaceState" : "pushState"](
      { lightbox: !!figure },
      "",
      url,
    );
    render();
  };
  const step = (by) => {
    const all = figures();
    const at = all.indexOf(shown);
    if (at >= 0) go(all[(at + by + all.length) % all.length], true);
  };
  const dismiss = () => {
    // Back, when the box was opened here, so the entry it added goes rather
    // than a second one piling up behind it; a new entry when the reader
    // arrived at the box's address, so that back opens it again.
    if (history.state?.lightbox) history.back();
    else {
      const figure = shown;
      go(null);
      figure?.scrollIntoView({ block: "center" });
    }
  };
  // The picture's element fills the stage and the picture is fitted inside it,
  // so the dark space either side of a tall one is the element too.
  // Not a video's, whose controls run the width of the element, past the frame.
  const beside = (el, event) => {
    const width = el.naturalWidth;
    const height = el.naturalHeight;
    if (el.tagName !== "IMG" || !width || !height) return false;
    const r = el.getBoundingClientRect();
    const scale = Math.min(r.width / width, r.height / height);
    return (
      Math.abs(event.clientX - r.left - r.width / 2) > (width * scale) / 2 ||
      Math.abs(event.clientY - r.top - r.height / 2) > (height * scale) / 2
    );
  };
  const build = (root) => {
    const box = document.createElement("dialog");
    box.className = "lightbox";
    box.innerHTML =
      '<div class="lightbox-bar"><span class="lightbox-count"></span>' +
      '<button type="button" class="lightbox-close" aria-label="Close" autofocus>\u00d7</button></div>' +
      '<div class="lightbox-stage"><button type="button" class="lightbox-prev" aria-label="Previous picture">\u2039</button>' +
      '<button type="button" class="lightbox-next" aria-label="Next picture">\u203a</button></div>' +
      '<div class="lightbox-caption"></div>';
    box.querySelector(".lightbox-close").onclick = dismiss;
    box.querySelector(".lightbox-prev").onclick = () => step(-1);
    box.querySelector(".lightbox-next").onclick = () => step(1);
    // The backdrop and the space around the picture close it, as a click
    // outside a box does.
    box.addEventListener("click", (event) => {
      const { target } = event;
      if (
        target === box ||
        target.classList.contains("lightbox-stage") ||
        beside(target, event)
      ) {
        // Not also the link to the original the picture is.
        event.preventDefault();
        dismiss();
      }
    });
    // Escape closes a dialog by itself, which the address would not hear of.
    box.addEventListener("cancel", (event) => {
      event.preventDefault();
      dismiss();
    });
    box.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") step(-1);
      else if (event.key === "ArrowRight") step(1);
    });
    root.append(box);
    return box;
  };
  const render = () => {
    // Without `File:` too, as the first addresses were written.
    const id = decodeURIComponent(
      location.hash.match(/^#\/media\/(?:File:)?(.+)/)?.[1] || "",
    );
    const all = figures();
    // By its file, or by its id, as an address written by hand might.
    const figure =
      id && (all.find((f) => fileOf(f) === id) || all.find((f) => f.id === id));
    if (!figure) {
      shown = null;
      // Out of the page, which is what stops a video playing in it.
      lightbox?.querySelector(".lightbox-media")?.remove();
      if (lightbox?.open) lightbox.close();
      return;
    }
    if (figure === shown && lightbox.open) return;
    shown = figure;
    lightbox ||= build(figure.closest(".eta-report"));
    const stage = lightbox.querySelector(".lightbox-stage");
    stage.querySelector(".lightbox-media")?.remove();
    const original = mediaOf(figure);
    const copy = original.cloneNode(true);
    let media = document.createElement("div");
    if (copy.tagName === "VIDEO") {
      // Its warning still before it, which is what the warning is for.
      const warning = figure.querySelector(":scope > .embed-warning");
      if (warning) media.append(warning.cloneNode(true));
      media.append(copy);
      // Carried on from where the page's copy was, which stops.
      copy.currentTime = original.currentTime;
      if (!original.paused) {
        original.pause();
        copy.autoplay = true;
      }
    } else {
      // The largest copy the page has, chosen for the whole window now rather
      // than the column; clicking it opens the original.
      for (const source of copy.querySelectorAll("source, img"))
        source.sizes = "100vw";
      const img = copy.tagName === "IMG" ? copy : copy.querySelector("img");
      img.removeAttribute("fetchpriority");
      img.removeAttribute("loading");
      media = document.createElement("a");
      media.href = originalOf(figure);
      media.target = "_blank";
      media.rel = "noopener";
      media.append(copy);
    }
    media.classList.add("lightbox-media");
    stage.prepend(media);
    lightbox.setAttribute(
      "aria-label",
      original.alt || copy.querySelector?.("img")?.alt || "Picture",
    );
    for (const button of lightbox.querySelectorAll(
      ".lightbox-prev, .lightbox-next",
    )) {
      button.hidden = all.length < 2;
    }
    lightbox.querySelector(".lightbox-count").textContent =
      all.length > 1 ? `${all.indexOf(figure) + 1} / ${all.length}` : "";
    const caption = lightbox.querySelector(".lightbox-caption");
    caption.replaceChildren(
      ...[...figure.querySelectorAll(":scope > figcaption")].map((c) =>
        c.cloneNode(true),
      ),
    );
    // A copy, so not where a backlink lands or a fragment points.
    for (const el of caption.querySelectorAll("[id]")) el.removeAttribute("id");
    for (const el of caption.querySelectorAll(".source-tip")) el.remove();
    if (!lightbox.open) lightbox.showModal();
  };
  document.addEventListener("click", (event) => {
    if (
      event.button ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    const link = event.target.closest?.(
      ".eta-report figure[id] > :is(.full-size, img), .eta-report .lightbox-open",
    );
    if (!link || link.closest(".lightbox")) return;
    event.preventDefault();
    go(link.parentElement);
  });
  addEventListener("popstate", render);
  addEventListener("hashchange", render);
  const ready = () => {
    // A click on a video is the player's, so a video opens by a button of its own.
    for (const video of document.querySelectorAll(
      ".eta-report figure[id] > video",
    )) {
      const open = document.createElement("button");
      open.type = "button";
      open.className = "lightbox-open";
      open.ariaLabel = "Open larger";
      open.textContent = "\u2922";
      video.before(open);
    }
    swooshAll();
    render();
  };
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", ready);
  else ready();
  for (const name of ["pointerover", "focusin"])
    document.addEventListener(name, place);
  for (const name of ["pointerout", "focusout"])
    document.addEventListener(name, release);
})();
