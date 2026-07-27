"""Requirements upload: the one place the browser writes a file into the repo.

A requirements doc is an *intent* artifact — the same kind `docs:` points at in
`.agentqa/config.yml` — supplied per job from the dashboard instead of committed
to the repo. The daemon's job is narrow: accept text it can vouch for, refuse
everything else with an answer the user can act on, and never let a filename
decide where a file lands.
"""
import json
import textwrap
import urllib.error
import urllib.request
from threading import Thread

import pytest

from studio import mailbox, uploads
from studio.server import make_server


@pytest.fixture
def live_server(tmp_path):
    cfgdir = tmp_path / ".agentqa"
    cfgdir.mkdir()
    (cfgdir / "config.yml").write_text(textwrap.dedent("""\
        platform: ios
        bundle_id: com.acme.app
        test_dir: AutomationTests
    """))
    srv = make_server(tmp_path, memory_scripts=None, port=0)
    Thread(target=srv.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _upload(base, filename, content):
    data = json.dumps({"filename": filename, "content": content}).encode()
    req = urllib.request.Request(base + "/api/studio/upload", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read().decode())


def _upload_err(base, filename, content):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _upload(base, filename, content)
    return exc.value.code, json.loads(exc.value.read().decode())["error"]


DOC = "# Login\n\nSuccess: the home tab bar appears.\n"


# ---- accepted ------------------------------------------------------------

def test_markdown_upload_lands_in_the_mailbox(live_server, tmp_path):
    status, body = _upload(live_server, "srd-login.md", DOC)
    assert status == 200
    stored = tmp_path / body["path"]
    assert stored.is_file()
    assert stored.read_text(encoding="utf-8") == DOC
    assert body["name"] == "srd-login.md"
    assert body["chars"] == len(DOC)


def test_upload_path_is_repo_relative(live_server):
    _, body = _upload(live_server, "srd.md", DOC)
    assert body["path"].startswith(".agentqa/studio/uploads/")
    assert not body["path"].startswith("/")


def test_txt_and_markdown_extensions_are_accepted(live_server):
    for name in ("notes.txt", "spec.markdown", "SPEC.MD"):
        status, _ = _upload(live_server, name, DOC)
        assert status == 200, name


def test_uploads_do_not_collide(live_server, tmp_path):
    a = _upload(live_server, "spec.md", "# one\n")[1]["path"]
    b = _upload(live_server, "spec.md", "# two\n")[1]["path"]
    assert a != b
    assert (tmp_path / a).read_text() == "# one\n"
    assert (tmp_path / b).read_text() == "# two\n"


def test_uploads_are_gitignored_like_the_rest_of_the_mailbox(live_server, tmp_path):
    _upload(live_server, "spec.md", DOC)
    assert (mailbox.studio_dir(tmp_path) / ".gitignore").read_text().strip() == "*"


# ---- refused, with something the user can act on -------------------------

def test_word_upload_is_refused_with_a_way_forward(live_server):
    """Word is the format requirements usually arrive in, so the refusal has to
    teach the fix rather than just say no."""
    code, err = _upload_err(live_server, "SRD.docx", "PK\x03\x04 binary junk")
    assert code == 400
    assert "Markdown" in err
    assert ".docx" in err


def test_legacy_doc_and_pdf_are_refused_the_same_way(live_server):
    for name in ("old.doc", "spec.pdf", "notes.rtf", "story.pages"):
        code, err = _upload_err(live_server, name, "junk")
        assert code == 400 and "Markdown" in err, name


def test_unknown_extension_is_refused(live_server):
    code, err = _upload_err(live_server, "script.py", "print(1)")
    assert code == 400
    assert ".md" in err


def test_empty_document_is_refused(live_server):
    code, err = _upload_err(live_server, "spec.md", "   \n\t\n")
    assert code == 400
    assert "empty" in err.lower()


def test_oversized_document_is_refused(live_server):
    code, err = _upload_err(live_server, "spec.md", "x" * (uploads.MAX_CHARS + 1))
    assert code == 400
    assert "too large" in err.lower()


def test_missing_filename_is_refused(live_server):
    code, _ = _upload_err(live_server, "", DOC)
    assert code == 400


# ---- the filename never decides where the file lands ---------------------

def test_a_traversing_filename_cannot_escape_the_uploads_dir(live_server, tmp_path):
    """The filename comes from a browser, so it is untrusted input for a path."""
    _, body = _upload(live_server, "../../../../etc/passwd.md", DOC)
    stored = (tmp_path / body["path"]).resolve()
    assert uploads.uploads_dir(tmp_path).resolve() == stored.parent
    assert not (tmp_path.parent / "passwd.md").exists()


def test_odd_characters_are_normalised_out_of_the_stored_name(live_server, tmp_path):
    original = "yêu cầu & `rm -rf` v2.md"
    _, body = _upload(live_server, original, DOC)
    stored = tmp_path / body["path"]
    assert stored.is_file()
    assert not (set(stored.name) & set(" &`;$|")), stored.name
    # The original name is still what the UI and the job record show.
    assert body["name"] == original


def test_a_nameless_stem_still_gets_a_file(live_server, tmp_path):
    _, body = _upload(live_server, "....md", DOC)
    assert (tmp_path / body["path"]).is_file()


# ---- the pure helpers ----------------------------------------------------

def test_safe_name_keeps_a_readable_stem():
    assert uploads.safe_name("Login SRD v2.md").endswith(".md")
    assert "Login" in uploads.safe_name("Login SRD v2.md")


def test_check_document_accepts_and_reports_why_it_refuses():
    assert uploads.check_document("a.md", DOC) is None
    assert "Markdown" in uploads.check_document("a.docx", DOC)
    assert uploads.check_document("a.md", "") is not None
