"""The name of each thing a build warns about, all in one place.

A warning's words are written for whoever reads them and change whenever they
can be said better. Its check is what it is about, and does not change:
two builds warning `the image ... has no caption` in different words
are still saying the same thing about the same picture,
and a comment left in the document for one is the comment for the other.

Each name is kebab-case and reads as what is wrong,
because it is printed on every comment the tool leaves,
where whoever reads the comment sees it.
Written out rather than derived from the member's name,
so a name read off a comment is one `rg` away from the code that warns it.

One name to a check: a warning said in two places, as the same thing,
shares one, and two different warnings never do.
"""

from enum import StrEnum, unique


@unique
class Check(StrEnum):
    """Which check a warning is from."""

    # Reading the document: `parse.py`.
    UNHANDLED_ELEMENT = "unhandled-element"
    SHIFT_ENTER_BLANK_SPACE = "shift-enter-blank-space"
    SHIFT_ENTER_BETWEEN_LINES = "shift-enter-between-lines"
    DATE_CHIP_WITHOUT_DATE = "date-chip-without-date"
    ARCHIVE_TODAY_SHORT_LINK = "archive-today-short-link"
    ARCHIVE_TODAY_LINK = "archive-today-link"
    OBJECT_NOT_A_PICTURE = "object-not-a-picture"
    SVG_LINE_NOT_SVG = "svg-line-not-svg"
    IMAGE_ROTATED = "image-rotated"
    SOURCE_LINE_WITHOUT_IMAGE = "source-line-without-image"
    IMAGE_STYLED_AS_HEADING = "image-styled-as-heading"
    UNFINISHED_TEXT = "unfinished-text"
    VIDEO_LINE_WITHOUT_VIDEO = "video-line-without-video"
    WARNING_LINE_WITHOUT_KIND = "warning-line-without-kind"
    CAPTION_STARTS_WITH_LABEL = "caption-starts-with-label"
    IMAGE_SOURCE_LABEL = "image-source-label"
    IMAGES_SHARE_PARAGRAPH = "images-share-paragraph"
    TEXT_BESIDE_IMAGE = "text-beside-image"
    NO_HEADER = "no-header"
    LINE_BEFORE_HEADER = "line-before-header"
    HEADER_WITHOUT_FIELDS = "header-without-fields"
    VIDEO_CAPTION_UNREADABLE = "video-caption-unreadable"
    VIDEO_CAPTION_ENDS_BEFORE_START = "video-caption-ends-before-start"
    UNKNOWN_MODIFIER = "unknown-modifier"
    LABEL_UNDERLINE_RUNS_ON = "label-underline-runs-on"
    HEADER_FIELD_RETIRED = "header-field-retired"
    HEADER_FIELD_UNKNOWN = "header-field-unknown"
    HEADER_FIELD_REPEATED = "header-field-repeated"
    NO_TITLE = "no-title"
    TITLE_IN_HEADER = "title-in-header"
    FOOTNOTE_UNREFERENCED = "footnote-unreferenced"
    SOCIAL_CARD_WITHOUT_PICTURE = "social-card-without-picture"

    # What a publication should have: `checks.py`.
    HEADER_FIELD_MISSING = "header-field-missing"
    HEADER_FIELD_EMPTY = "header-field-empty"
    HEADER_FIELD_UNFINISHED = "header-field-unfinished"
    SEO_DESCRIPTION_TOO_LONG = "seo-description-too-long"
    CONTRIBUTORS_MISSING_COMMA = "contributors-missing-comma"
    CONTRIBUTOR_CREDITED_BY_ADDRESS = "contributor-credited-by-address"
    HEADER_FIELD_OUTSIDE_HEADER = "header-field-outside-header"
    NOT_A_FIELD = "not-a-field"
    IMAGE_WITHOUT_DESCRIPTION = "image-without-description"
    ALT_TEXT_SAYS_IMAGE = "alt-text-says-image"
    CHART_WITHOUT_SVG = "chart-without-svg"
    IMAGE_WITHOUT_CAPTION = "image-without-caption"
    CREDIT_NOT_UNDERLINED = "credit-not-underlined"
    IMAGE_WITHOUT_CREDIT = "image-without-credit"
    IMAGE_UNNAMED = "image-unnamed"
    LINK_TRACKING_TAG = "link-tracking-tag"
    PDF_PAGE_OUT_OF_RANGE = "pdf-page-out-of-range"
    URL_NOT_LINKED = "url-not-linked"
    LINK_TEXT_IS_URL = "link-text-is-url"
    OPEN_SUGGESTIONS = "open-suggestions"
    OPEN_COMMENTS = "open-comments"

    # The publication's address: `site.py`.
    URL_UNDER_BRIEFS = "url-under-briefs"

    # Pictures: `images.py`.
    IMAGE_DIFFERS_FROM_SOURCE = "image-differs-from-source"
    IMAGE_SOURCE_DOWNLOAD_FAILED = "image-source-download-failed"
    IMAGE_URIS_MISSING = "image-uris-missing"
    IMAGE_WITHOUT_URI = "image-without-uri"
    VECTOR_COPY_MISSING = "vector-copy-missing"
    VECTOR_DOWNLOAD_FAILED = "vector-download-failed"
    VECTOR_CROP_FAILED = "vector-crop-failed"
    VECTOR_LOGO_FAILED = "vector-logo-failed"
    IMAGE_CROPS_TO_NOTHING = "image-crops-to-nothing"
    IMAGE_CROP_FAILED = "image-crop-failed"

    # Videos and posts: `embeds.py`.
    EMBED_NOT_LOOKED_UP = "embed-not-looked-up"
    EMBED_LOOKUP_FAILED = "embed-lookup-failed"
    EMBED_NOT_A_VIDEO = "embed-not-a-video"
    VIDEO_CAPTIONS_NOT_SHOWN = "video-captions-not-shown"
    VIDEO_WITHOUT_CAPTIONS = "video-without-captions"
    EMBED_DOWNLOAD_FAILED = "embed-download-failed"
    VIDEO_CAPTIONS_DOWNLOAD_FAILED = "video-captions-download-failed"
    VIDEO_TOO_LARGE = "video-too-large"

    # The outputs: `build.py`, `emit/typst.py`, and `archive.py`.
    FFMPEG_MISSING = "ffmpeg-missing"
    VIDEO_FRAME_FAILED = "video-frame-failed"
    CODE_BLOCK_TOO_LARGE = "code-block-too-large"
    CODE_BLOCK_NEAR_LIMIT = "code-block-near-limit"
    FOOTNOTE_UNDEFINED = "footnote-undefined"
    ARCHIVE_FAILED = "archive-failed"

    # The house style: `style.py`.
    EXTRA_SPACE_AFTER_SENTENCE = "extra-space-after-sentence"
    EXTRA_SPACE_BETWEEN_WORDS = "extra-space-between-words"
    SPACED_DASH = "spaced-dash"
    HYPHEN_IN_RANGE = "hyphen-in-range"
    STRAIGHT_APOSTROPHE = "straight-apostrophe"
    ETA_WITH_ARTICLE = "eta-with-article"
    STATION_OR_STREET_NAME = "station-or-street-name"
    UNIT_NOT_ABBREVIATED = "unit-not-abbreviated"
    HYPHENATED_UNIT = "hyphenated-unit"
    SYMBOL_SPELLED_OUT = "symbol-spelled-out"
