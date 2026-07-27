"""The conversation panel's pure decision functions, exercised through node.

Two bugs live here, both invisible to the daemon's Python tests:

* Choice options arrived as `{label, value}` objects and the renderer stringified
  them — every button read `[object Object]` **and replied with that literal
  string**, so the agent got an answer no branch of the flow could match.
* The conversation box is a flex column with a capped height. Its entries kept
  the default `flex-shrink: 1`, so a long conversation was squeezed to fit the
  box instead of overflowing it: cards clipped their own content, the box never
  scrolled, and the newest card could not be reached.
"""
import json

from studio.tests.jsprobe import APP_JS, call, needs_node

pytestmark = needs_node

TEXT = ["text"]
OPT = ["text", "optionLabel", "optionValue"]


# ---- text(): nothing in the UI may ever render as "[object Object]" --------

def test_text_passes_strings_through():
    assert call(TEXT, [], 'text("hello")') == "hello"


def test_text_renders_object_as_json_not_object_object():
    out = call(TEXT, [], 'text({label: "Cold launch", value: "cold"})')
    assert out != "[object Object]"
    assert "Cold launch" in out


def test_text_renders_array_readably():
    assert call(TEXT, [], 'text(["a", "b"])') != "[object Object]"


def test_text_is_empty_for_nullish():
    assert call(TEXT, [], '[text(null), text(undefined)]') == ["", ""]


def test_text_keeps_falsy_scalars():
    assert call(TEXT, [], '[text(0), text(false)]') == ["0", "false"]


def test_esc_escapes_and_never_yields_object_object():
    out = call(["text", "esc"], [], 'esc({label: "<b>&</b>"})')
    assert out != "[object Object]"
    assert "<b>" not in out and "&lt;b&gt;" in out


# ---- option shapes: show the label, reply with the value ------------------

def test_string_option_is_its_own_label_and_value():
    assert call(OPT, [], '[optionLabel("Allow"), optionValue("Allow")]') == ["Allow", "Allow"]


def test_object_option_shows_label_and_submits_value():
    expr = '[optionLabel({label: "Cold launch → Home", value: "cold_launch"}),' \
           ' optionValue({label: "Cold launch → Home", value: "cold_launch"})]'
    assert call(OPT, [], expr) == ["Cold launch → Home", "cold_launch"]


def test_option_with_only_a_value_labels_itself_with_it():
    assert call(OPT, [], '[optionLabel({value: "deny"}), optionValue({value: "deny"})]') == ["deny", "deny"]


def test_option_with_only_a_label_submits_the_label():
    assert call(OPT, [], '[optionLabel({label: "Deny"}), optionValue({label: "Deny"})]') == ["Deny", "Deny"]


def test_unknown_option_shape_stays_readable():
    """An option the protocol does not describe must still show something a
    human can act on — an unlabelled button is worse than visible JSON."""
    out = call(OPT, [], 'optionLabel({who: "knows"})')
    assert out != "[object Object]" and "knows" in out


def test_numeric_option_survives():
    assert call(OPT, [], '[optionLabel(3), optionValue(3)]') == ["3", "3"]


# ---- sticky-bottom scrolling ---------------------------------------------

def test_at_bottom_when_parked_at_the_end():
    assert call(["isAtBottom"], ["STICK_THRESHOLD_PX"], "isAtBottom(500, 500, 1000)") is True


def test_at_bottom_within_the_threshold():
    """A few pixels off the end still counts as "following" — sub-pixel
    scroll positions are normal and must not drop the reader out of stick."""
    assert call(["isAtBottom"], ["STICK_THRESHOLD_PX"], "isAtBottom(480, 500, 1000)") is True


def test_not_at_bottom_when_reading_history():
    assert call(["isAtBottom"], ["STICK_THRESHOLD_PX"], "isAtBottom(0, 500, 1000)") is False


def test_content_shorter_than_the_box_is_at_bottom():
    assert call(["isAtBottom"], ["STICK_THRESHOLD_PX"], "isAtBottom(0, 500, 400)") is True


# ---- naming a job that arrived as a file ---------------------------------

IDEA = ["text", "deriveIdea"]


def test_typed_idea_always_wins():
    assert call(IDEA, [], 'deriveIdea("guest checkout", "srd.md", "# Login\\n")') == "guest checkout"


def test_empty_idea_falls_back_to_the_documents_heading():
    """Attaching a spec and hitting Start with an empty box is the obvious way
    to use this, so it has to produce a job name — the spec's own title."""
    assert call(IDEA, [], 'deriveIdea("", "srd-v2.md", "# Sign in with a valid account\\n\\nbody")') \
        == "Sign in with a valid account"


def test_heading_deeper_in_the_document_is_used():
    assert call(IDEA, [], 'deriveIdea("  ", "srd.md", "\\n\\n## Checkout flow\\nbody")') == "Checkout flow"


def test_headingless_document_falls_back_to_the_filename():
    assert call(IDEA, [], 'deriveIdea("", "guest_checkout-spec.md", "no headings here")') \
        == "guest checkout spec"


def test_nothing_at_all_stays_empty():
    """An empty box and no file must not queue a nameless job."""
    assert call(IDEA, [], 'deriveIdea("", "", "")') == ""


# ---- naming the card: an `ask` is not a `clarify` -------------------------
#
# The regression: card labels were keyed by `kind`, but the protocol gives
# `clarify` and `ask` the same `kind: "form"`. So the agent's system-dialog
# question — "a tracking prompt appeared, allow/deny/dismiss?" — arrived at the
# dashboard wearing the word "Clarify". A tester watching for the agent to ask
# about a permission prompt saw what looked like a stray requirements card and
# reported the permission request as not showing up at all.
#
# The renderer *did* carry a special case for this, but it tested
# `subtype === "permission"` — a subtype protocol.py's whitelist rejects, so the
# branch could never run. Hence the consistency test at the end of this block.

LABEL = ["cardLabel"]
LABEL_CONSTS = ["CARD_SUBTYPE_LABEL", "CARD_KIND_LABEL"]


def label_of(subtype, kind="form"):
    return call(LABEL, LABEL_CONSTS, 'cardLabel({subtype: %s, kind: "%s"})'
                % (json.dumps(subtype), kind))


def test_ask_card_is_not_labelled_clarify():
    """The exact bug. Two different questions must not share one name."""
    assert label_of("ask") != "Clarify"


def test_ask_card_names_the_system_dialog():
    """The tester has to know the agent is blocked on a dialog the phone put up,
    not on a requirements question, because the two need different answers."""
    assert "system" in label_of("ask").lower()


def test_clarify_card_still_reads_clarify():
    assert label_of("clarify") == "Clarify"


def test_build_and_review_keep_their_labels():
    assert label_of("build", "confirm") == "Build step"
    assert label_of("review", "review") == "Review"


def test_unknown_subtype_falls_back_to_the_kind_label():
    """A subtype added to the protocol before the UI learns its name must still
    render as something — falling back to the kind beats a blank chip."""
    assert label_of("brand-new-thing") == "Clarify"


def test_missing_subtype_falls_back_to_the_kind_label():
    assert call(LABEL, LABEL_CONSTS, 'cardLabel({kind: "confirm"})') == "Build step"


def test_unknown_kind_shows_itself_rather_than_nothing():
    assert call(LABEL, LABEL_CONSTS, 'cardLabel({kind: "mystery"})') == "mystery"


def test_every_protocol_subtype_has_a_label():
    """The guard for the class of bug this block came from: the renderer named a
    subtype ("permission") the protocol never emits, so its branch was dead and
    nobody noticed. Labels and the protocol whitelist must agree."""
    from studio.protocol import QUESTION_SUBTYPES

    labelled = set(call([], ["CARD_SUBTYPE_LABEL"], "Object.keys(CARD_SUBTYPE_LABEL)"))
    assert not QUESTION_SUBTYPES - labelled, (
        "question subtypes with no card label: %s" % sorted(QUESTION_SUBTYPES - labelled))
    assert not labelled - QUESTION_SUBTYPES, (
        "card labels for subtypes the protocol rejects: %s" % sorted(labelled - QUESTION_SUBTYPES))


# ---- the CSS invariant the scroll bug came from --------------------------

def test_convo_entries_are_not_allowed_to_shrink():
    """Guards the exact regression: as flex items with the default
    `flex-shrink: 1`, entries were compressed to fit the capped box (and
    `.msg-card`'s `overflow: hidden` let them shrink to nothing), so the box
    never overflowed and never scrolled. They must keep their natural height."""
    css = (APP_JS.parent / "style.css").read_text(encoding="utf-8")
    rule = [ln for ln in css.split("\n") if ln.strip().startswith(".convo > *")]
    assert rule, ".convo > * rule is missing — conversation entries will shrink again"
    assert "flex: 0 0 auto" in rule[0]
