"""Terminal-cell measurement, slicing and wrapping (SGR escapes cost no cells).

Wide characters occupy two cells; combining marks stay with their base. All
layout code uses these helpers, including matplotlib's text metrics.
"""
import re

from wcwidth import wcwidth, wcswidth

SGR = re.compile(r"\x1b\[[0-9;:]*m")
RESET = "\x1b[0m"


def width(text):
    """Display cells in a single line, ignoring ANSI SGR styling."""
    return sum(size for _, size in clusters(str(text)))


def clusters(text):
    """Yield (text, cells), keeping zero-width marks/escapes with their base."""
    pending, plain = "", ""
    i = 0
    while i < len(text):
        escape = SGR.match(text, i)
        if escape:
            pending += escape.group()
            i = escape.end()
            continue
        char = text[i]
        cells = wcwidth(char)
        # Zero-width joiners/variation selectors and flag pairs can change
        # the width of their base; measure the complete cluster, not each codepoint.
        flag_pair = len(plain) == 1 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in plain + char)
        if cells > 0 and plain and not plain.endswith("\u200d") and not flag_pair:
            yield pending, max(0, wcswidth(plain))
            pending, plain = "", ""
        if cells >= 0:
            pending += char
            plain += char
        i += 1
    if pending:
        yield pending, max(0, wcswidth(plain))


def slice_cells(text, start=0, stop=None):
    """Cell-aligned slice; never emit half a wide character or an SGR escape.

    Styling preceding the slice is replayed, and styled slices are reset so
    wrapping/truncation cannot leak colour into subsequent terminal output.
    """
    stop = width(text) if stop is None else max(0, stop)
    pos, out, style = 0, [], ""
    for token, size in clusters(text):
        if pos >= start and pos + size <= stop:
            if not out and style:
                out.append(style)
            out.append(token)
        style += "".join(SGR.findall(token))
        pos += size
        if pos > stop:
            break
    result = "".join(out)
    return result + RESET if SGR.search(result) else result


def truncate(text, cols):
    if width(text) <= cols:
        return text
    return slice_cells(text, 0, max(0, cols - 1)) + ("…" if cols else "")


def wrap(text, cols):
    """Wrap prose by display cells, preserving explicit newlines and words."""
    if cols < 1:
        raise ValueError("cols must be positive")
    lines = []
    for paragraph in text.split("\n"):
        paragraph = "".join(token for token, _ in clusters(paragraph))
        if not paragraph:
            lines.append("")
        while paragraph:
            if width(paragraph) <= cols:
                lines.append(paragraph)
                break
            head = slice_cells(paragraph, 0, cols)
            # Prefer a word boundary, but split long words/CJK by cells.
            plain = SGR.sub("", head)
            cut = width(plain[:plain.rfind(" ")]) if " " in plain else width(head)
            if cut < 1:
                cut = width(head)
            if cut < 1:
                raise ValueError("a character is wider than cols")
            lines.append(slice_cells(paragraph, 0, cut).rstrip())
            paragraph = slice_cells(paragraph, cut).lstrip()
    return lines


def pack_entries(label, entries, cols):
    """Wrap a colour key between entries, never inside a numeric range."""
    lines = wrap(label, cols) if label else []
    current = lines.pop() if lines else ""
    for entry in entries:
        if width(entry) > cols:
            raise ValueError(f"color-key entry needs {width(entry)} cells, cols={cols}")
        candidate = current + ("  " if current else "") + entry
        if width(candidate) > cols:
            lines.append(current)
            current = entry
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
