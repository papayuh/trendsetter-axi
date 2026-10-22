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
    c = subprocess.run([sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:cacheprovider", *(str(HERE / f) for f in RENDER_TESTS)],
                       cwd=HERE.parent, capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stdout
    defined = {m.group(1) for line in c.stdout.splitlines() if (m := re.match(r"\S+::(\w+)", line))}
    # test_gallery_ids never renders anything
    assert defined - failed == {"test_gallery_ids"}, sorted(defined - failed)
