from atsurvey import ProjectInput, compute_project
from atsurvey.core.suggest import suggest_traverses

from synth import TRUTH, observe, traverse_setups
from test_traverse import LINK, control


def test_suggests_link_traverse_with_closing_azimuth():
    setups = traverse_setups(TRUTH, LINK)
    setups.append(observe(TRUTH, "S1", ["T2", "D1", "D2"]))
    inp = ProjectInput(control_points=control(), setups=setups)
    s = suggest_traverses(inp)
    assert len(s) == 1
    assert s[0].route in (LINK, list(reversed(LINK)))
    # and the suggestion computes cleanly
    r = compute_project(inp.model_copy(update={"traverses": s}))
    assert r.traverses[0].status == "ok"
    assert r.traverses[0].end_orientation


def test_suggests_open_traverse_when_no_closure():
    route = ["T1", "T2", "S1", "S2"]
    s = suggest_traverses(
        ProjectInput(control_points=control(["T1", "T2"]), setups=traverse_setups(TRUTH, route))
    )
    assert [t.route for t in s] == [route]
    assert s[0].kind == "open"


def test_no_suggestions_without_control():
    s = suggest_traverses(ProjectInput(setups=traverse_setups(TRUTH, LINK)))
    assert s == []
