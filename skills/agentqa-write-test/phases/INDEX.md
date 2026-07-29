# Phase index

Load exactly one phase file for `current_phase`. Never preload later phases.

| Phase | File | Required output | CLI families in any loaded block |
|---|---|---|---|
| 1 | `phase-1-map-clarify.md` | requirement note + code map | codegraph, memory-index, checkpoint |
| 2 | `phase-2-explore.md` | live-grounded flow/screen notes | phase2-wrapper, agent-device, checkpoint |
| 3 | `phase-3-identifiers.md` | additive identifiers verified live | git/build, Appium hierarchy, wrapper/checkpoint |
| 4 | `phase-4-write-green.md` | approved green targeted test | prechecks, pytest, hierarchy; failure blocks load separately |
| 5 | `phase-5-capture.md` | deduped/linted durable memory | phase2-wrapper, memory-lint-wrapper, checkpoint |

After a phase calls `complete`, return to the controller. The controller alone
calls `validate`, `advance`, `finalize`, or `abort`.

When checkpoint `platform` is `android`, also load `../references/android.md`.
For iOS, do not load it.
