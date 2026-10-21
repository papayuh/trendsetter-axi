import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
RENDER_TESTS = ["test_render.py", "test_fidelity.py"]


def test_fake_renderer_fails_the_suite():
    """A renderer that returns "x" must not pass: every rendering test fails, none is satisfied by non-empty output."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider", *(str(HERE / f) for f in RENDER_TESTS)],
                       env={**os.environ, "TSAXI_FAKE_RENDERER": "x"}, cwd=HERE.parent, capture_output=True, text=True, timeout=300)
    assert r.returncode != 0, r.stdout
    failed = set(re.findall(r"^FAILED \S+::(\w+)", r.stdout, re.M))
    defined = {n for f in RENDER_TESTS for n in re.findall(r"^def (test_\w+)", (HERE / f).read_text(), re.M)}
    # test_gallery_ids never renders anything
    assert defined - failed == {"test_gallery_ids"}, sorted(defined - failed)
