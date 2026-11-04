"""Terminal-cell measurement, slicing and wrapping (SGR escapes cost no cells).

Wide characters occupy two cells; combining marks stay with their base. All
layout code uses these helpers, including matplotlib's text metrics.
"""
import re

from wcwidth import wcwidth, wcswidth

SGR = re.compile(r"\x1b\[[0-9;:]*m")
RESET = "\x1b[0m"
CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
TERMINAL_ESCAPES = re.compile(r"(?:\x1b\]|\x9d).*?(?:\x07|\x1b\\|\x9c)|(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]", re.DOTALL)

SUP = dict(zip("0123456789-+−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺⁻"))
def sup(t): return "".join(SUP[ch] for ch in t) if all(ch in SUP for ch in t) else "^" + t


def clean_text(s):
    """Sanitize artist text, preserving layout newlines/tabs and readable math."""
    s = CONTROLS.sub(lambda m: m.group() if m.group() in "\n\t" else "", TERMINAL_ESCAPES.sub("", s))
    if s.count("$") >= 2 and s.count("$") % 2 == 0:  # mathtext: drop the markup, keep the words
        s = re.sub(r"\\?mathdefault", "", s)
        s = re.sub(r"\^\{([^}]*)\}|\^(.)", lambda m: sup(m.group(1) if m.group(1) is not None else m.group(2)), s)
        for a, b in [("\\times", "×"), ("\\cdot", "·"), ("\\alpha", "α"), ("\\beta", "β"), ("\\mu", "µ"),
                     ("\\sigma", "σ"), ("\\pm", "±"), ("\\degree", "°"), ("_{", "_"), ("\\", "")]:
            s = s.replace(a, b)
        s = s.replace("$", "").replace("{", "").replace("}", "")
    return s.replace("−", "-")


def summary_text(s):
    """Sanitize an unquoted source label for a single summary field."""
    return " / ".join(clean_text(s).splitlines()).replace("\t", " ").replace(":", r"\:")


class DisplayCapacityError(ValueError):
    """A valid display cannot fit an indivisible character or key entry."""


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
        # ponytail: keep terminal emoji sequences intact, not full Unicode grapheme segmentation.
        # Measure the complete cluster; modifiers can have positive standalone width.
        flag_pair = len(plain) == 1 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in plain + char)
        modifier = 0x1F3FB <= ord(char) <= 0x1F3FF or char in "\ufe0f\u20e3" or 0xE0020 <= ord(char) <= 0xE007F
        if cells > 0 and plain and not plain.endswith("\u200d") and not flag_pair and not modifier:
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
                raise DisplayCapacityError("a character is wider than cols")
            lines.append(slice_cells(paragraph, 0, cut).rstrip())
            paragraph = slice_cells(paragraph, cut).lstrip()
    return lines


def pack_entries(label, entries, cols):
    """Wrap a colour key between entries, never inside a numeric range."""
    lines = wrap(label, cols) if label else []
    current = lines.pop() if lines else ""
    for entry in entries:
        if width(entry) > cols:
            raise DisplayCapacityError(f"color-key entry needs {width(entry)} cells, cols={cols}")
        candidate = current + ("  " if current else "") + entry
        if width(candidate) > cols:
            lines.append(current)
            current = entry
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
