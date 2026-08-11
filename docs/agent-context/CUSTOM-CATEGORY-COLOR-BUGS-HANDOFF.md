# Handoff: Custom Category / Color Picker bugs to fix

## ⚠️ UNRESOLVED: user re-tested and reports none of the fixes below are visible

After the "FIXED" changes documented in Bugs 1/2/3 below were made, verified
by reading the diff (`update_map`'s body is byte-identical to `origin/main`
except its docstring; `app/pages/home.py`'s `color_picker_modal`/
`custom_group_modal` are `dbc.Offcanvas`, not `dbc.Modal`), and exercised
against a live `python app/app.py` dev server (layout JSON fetched over
HTTP showed the new component tree, full callback chain driven directly and
asserted correct), **the user ran the app again and reported: still modals
for both panels, no ability to choose a color at all, and the map still
cannot zoom.**

This is a real, unresolved discrepancy between what the source code on disk
says and what the user is observing. Re-reading the working tree at the time
of writing this note confirms the fixes are still present on disk
(`git status`/`git diff` show the expected changes, nothing reverted). Given
that, the most likely explanations - **in priority order to check first** -
are environmental, not further code bugs:

1. **A previously-started server process is still serving old code.** This
   app is launched with `app.run(debug=False, port=port)`
   (`app/app.py`, bottom) - Dash's hot-reload/dev-tools are off, so a
   process started before these edits will keep serving the old layout
   until it's killed and restarted. Confirm the user fully stopped and
   restarted their `python app/app.py` (or `server.py`) process, not just
   refreshed the browser tab against an already-running old process.
2. **Docker image is stale.** Per `CLAUDE.md`, this app is normally
   deployed via Docker Compose (`docker build` only copies `./app` into the
   image at build time). If the user is testing through
   `docker compose up`/a built image rather than running `python
   app/app.py` directly against this checkout, the image needs a full
   rebuild (`docker build`/`docker compose build`) to pick up any of these
   source changes - editing the files on disk does nothing for an
   already-built image.
3. **Browser cache / stale tab.** A hard refresh (Ctrl+Shift+R / disable
   cache in devtools) rules this out; also confirm the browser is pointed
   at the same host:port the freshly-restarted process is actually
   listening on (no second stale instance bound to the same or a different
   port).
4. **Wrong checkout/working directory.** Confirm the user is running the
   app from this same repo path (`C:\deployment\wq_spatial_app\00_SPATIAL_WQ`)
   and not a second clone/copy elsewhere on disk.

**Action for the next agent (or before re-attempting any fix):** get the
exact command the user uses to launch the app and confirm which of the
above applies before touching the code further - re-diagnosing/re-patching
code that's already correct on disk wastes a cycle if the real issue is
that the user's running instance never picked it up. If, after ruling out
1-4, the user is *still* seeing old behavior against a freshly restarted
process on this exact checkout, that's a genuine new bug and needs fresh
investigation from scratch (don't assume the "FIXED" sections below are
actually working just because they were verified in this session's own dev
server run).

---

Context: the Dynamic Category Creation & Color Picker feature (custom
per-category color overrides + user-created plotting-group columns, see
`app/app.py`, `app/pages/home.py`, `app/src/data_manager.py`,
`app/src/data_process.py`) was implemented and unit-tested (110/110 tests
green), but real usage surfaced three UX/behavioral bugs. **Bugs 1 and 3 are
now fixed** (see status notes inline below); **bug 2's core ask - a
hex-entry + hue/saturation-square color widget - is still open** and needs a
scope decision before implementation.

---

## Bug 1: Map view resets/breaks whenever a color override is applied — **FIXED (reverted)**

The user reported the regression was worse than "snaps back after
recoloring" - the map couldn't be zoomed/panned at all, "locked in one view
no matter what." Rather than broaden the relayout-preservation check (the
option originally proposed below), `update_map` was reverted to be
byte-identical to its pre-feature form (`git diff origin/main --
app/app.py` on the function body shows only a docstring diff): the
`Input("custom-color-overrides", "data")` was removed entirely. Color
overrides now apply to the map the next time it naturally rebuilds (group
dropdown change or new upload), not instantly - if instant map recoloring
is wanted back later, it needs a different mechanism (e.g. a
`Patch`/clientside partial-property update instead of a full new Input
triggering a full figure rebuild) rather than re-adding that Input.

**Original analysis (superseded by the revert above, kept for context):**

**Symptom reported:** "the map seems broken, whatever custom bounds were
implemented are not good, revert."

**Root cause:** `update_map` (`app/app.py:627-684`) got a new
`Input("custom-color-overrides", "data")` (line 632) so the map recolors
instantly when the user applies/resets a color override. But the existing
pan/zoom-preservation logic only re-applies `relayoutData` when the
*triggering* input was the group dropdown:

```python
# app/app.py:674
if ctx_call == "map-group-dropdown" and relayoutData:
    ...
    fig.update_layout(relayoutData)
```

Since `ctx.triggered_id` is `"custom-color-overrides"` (not
`"map-group-dropdown"`) when a color is applied/reset, this branch is
skipped and the rebuilt figure falls back to whatever default
center/zoom/bounds `plotting.make_map`/`px.scatter_map` computes - i.e. the
view snaps back and loses the user's current pan/zoom every time they touch
the color picker. This is a regression introduced by this feature, not a
pre-existing map problem.

**Recommended fix:** broaden the relayout-preservation check to cover any
trigger that isn't a fresh dataset load, e.g.:

```python
if ctx_call in ("map-group-dropdown", "custom-color-overrides") and relayoutData:
```

or more robustly, preserve relayout on every trigger except the initial
`meta-data` load (new upload), since a genuinely new dataset is the only
case where resetting the view to fit the new data actually makes sense. If
this refactor introduces more risk than it's worth, reverting the
`custom-color-overrides` Input from `update_map` and instead having
`apply_color_overrides`/`reset_color_overrides` write directly into
`meta-data`'s `dict_generic_colors` (still non-destructively, just without
adding a whole new trigger to `update_map`) is the simpler, lower-risk
option - worth weighing against the plan's original "non-destructive
override, separate from `dict_generic_colors`" design decision before
picking an approach.

---

## Bug 2: Color picker only shows "Reset to defaults" / "Apply" - no visible per-category controls, and the control itself doesn't match what was asked for — **PARTIALLY FIXED, core ask still open**

**Fixed:** the picker (and the custom-group-creation panel) were converted
from `dbc.Modal` to `dbc.Offcanvas` (`placement="end", backdrop=False,
scrollable=True`) per the user's explicit request for a "right aligned
vertical ribbon that pops out" instead of a blocking modal - this also
resolves bug 3's blocking problem (see below). The dropdown-must-be-selected
discoverability issue (problem 1, originally) is unchanged/not yet
addressed - still worth auto-selecting a default group on open.

**Still open - the actual widget:** each row still renders a bare native
`dcc.Input(type="color", ...)` swatch (`_color_swatch_row`,
`app/app.py`). This has NOT been replaced with the requested hex-text-entry
+ hue/saturation-square-and-slider picker - that's a real scope increase
(custom Dash component or a vendored JS color-picker library) and needs a
decision with the user before building, per the original analysis below.

**Symptom reported:** "the re-mapping of color categories does not work as
intended, I am only given a 'reset to defaults' and 'apply' option, there
should be something like a side by side list where each category is listed
and next to it is a text entry box and then a color wheel... can you use the
color selector VS Code has? It's like a square with a slider for hue +
saturation."

**Two separate problems here:**

1. **Discoverability/rendering:** `color-picker-modal`
   (`app/pages/home.py`) opens with the group dropdown unselected
   (`populate_color_picker_group_dropdown` returns `value=None` -
   `app/app.py:496-511`), so `color-picker-value-list` stays empty
   (`populate_color_picker_value_list`, `app/app.py:535-560`, only fires on
   `color-picker-group-dropdown`'s `value` `Input`) until the user manually
   picks a group from the dropdown. If there's only one plotting group, or
   the user doesn't notice the dropdown, the modal reads as "just two
   buttons and nothing else." At minimum, auto-select the first plotting
   group on open (or the currently-active `map-group-dropdown` value) so
   rows are visible immediately.

2. **Wrong control entirely:** each row currently renders one native
   `dcc.Input(type="color", ...)` (`_color_swatch_row`, `app/app.py:513-527`)
   - a bare HTML5 color swatch that, when clicked, opens the *browser's*
   native OS color panel, not an inline widget. That's a single control with
   no hex text entry alongside it. What was asked for is two things per row:
   a **hex text entry field** (so a user can type/paste a known hex value)
   **and** a **hue/saturation-square + hue-slider picker** (VS Code-style),
   shown inline, not gated behind a native browser dialog.

   Dash's built-in component set (`dash.html`, `dash.dcc`,
   `dash_bootstrap_components`) has nothing like this - it needs either:
   - a small custom Dash component (JS, likely `Set/GetCanvas`+drag-events
     for the saturation/hue square, an HTML range `<input>` or custom
     gradient bar for hue), or
   - a `clientside_callback`-driven approach using a JS color-picker library
     (check `app/requirements.txt`/any JS deps already vendored before
     pulling in a new one - CLAUDE.md's "don't add unsolicited
     dependencies" guidance applies, so this should be a deliberate,
     flagged decision, not a silent addition), or
   - a pragmatic middle ground: hex text `dcc.Input` + a plain HTML5
     `<input type="color">` swatch side by side (still native picker for the
     swatch, but at least adds the requested text-entry field) as a
     stopgap, with the full hue/saturation-square as a follow-up.

   Recommend raising this design choice with the user (via
   `AskUserQuestion` or similar) before building, since it's a real scope
   increase (custom component work) versus the original plan's assumption
   that a native `<input type="color">` would suffice.

**Also verify while fixing:** once rows render, confirm `apply_color_overrides`
(`app/app.py:566-599`) correctly reads every row's current value via the
pattern-matched `State({"type": "color-swatch-input", "value": ALL}, ...)` -
this logic doesn't change based on which widget renders the color, but the
row-rendering helper (`_color_swatch_row`) and its `id={"type":
"color-swatch-input", "value": str(value)}` pattern will need to be
preserved (or deliberately migrated) if the widget is swapped out.

---

## Bug 3: Custom category assignment is unusable past the first selection — **FIXED**

Both root causes were fixed:
- `custom-group-modal` is now a non-blocking `dbc.Offcanvas`
  (`backdrop=False`) instead of a `dbc.Modal` with `backdrop="static"`, so
  the map/plots stay clickable while it's open.
- `open_blank_custom_group_modal` and `populate_custom_group_from_selection`
  (`app/app.py`) now take `State("custom-group-draft", "data")` and merge
  into/preserve it instead of resetting to `{}` on every call. The draft
  only actually clears on Cancel or Finish.

Verified end-to-end via direct callback invocation (not just unit tests):
lasso → commit "MyCategory" → lasso a different selection → commit
"SecondCategory" → both categories present in the finalized column. See
`git log`/session transcript for the smoke-test script used, or re-derive
similarly if a regression test is added later.

**Original analysis (root causes, kept for reference):**

**Symptom reported:** "the assigning of new categories is clunky at best,
ideally you could highlight, lock in, highlight next group, lock, etc.
instead you highlight once then are stuck."

**Two compounding root causes:**

1. **The modal blocks the map/plots it needs you to interact with.**
   `custom-group-modal` (`app/pages/home.py`) is a `dbc.Modal` with
   `backdrop="static"`. Bootstrap modals render a full-page backdrop over
   everything behind them while open - the map and PCA/PaCMAP plots are
   behind that backdrop and **not clickable** while the modal is open. So
   the intended flow (lasso on map → modal opens pre-populated → commit
   category → lasso *again* for the next category → commit again) is
   structurally impossible as built: the user can't lasso a second
   selection without first closing the modal, and closing it is only wired
   to `custom-group-cancel-button`/`custom-group-finalize-button`, both of
   which end the whole custom-group-creation session rather than just
   "step out to reselect."

2. **Every new selection wipes previously committed categories.** Both
   `open_blank_custom_group_modal` (`app/app.py:850`, returns `draft={}`)
   and `populate_custom_group_from_selection` (`app/app.py:922`, also
   returns `draft={}`) unconditionally reset `custom-group-draft` to an
   empty dict. So even if the modal *could* be reopened between selections,
   any categories already committed via `commit_category_to_draft`
   (`app/app.py:938+`) would be discarded the moment the user triggered a
   new selection. This is a straightforward bug independent of the modal's
   backdrop problem: both callbacks should merge into/preserve the existing
   draft (via a `State("custom-group-draft", "data")` they currently don't
   read) rather than clobbering it, e.g.:

   ```python
   State("custom-group-draft", "data")
   ...
   def populate_custom_group_from_selection(..., existing_draft):
       existing_draft = existing_draft or {}
       ...
       return True, options, selected_entity_ids, existing_draft, _render_custom_group_preview(existing_draft)
   ```

**Recommended fix, in order of impact:**
- Stop resetting the draft on every (re)selection - preserve it across
  `open_blank_custom_group_modal`/`populate_custom_group_from_selection`
  calls (bug independent of the design question below).
- Redesign the interaction so the user isn't forced to close a
  selection-blocking modal between categories. Options, roughly in
  increasing effort:
  - Make `custom-group-modal` non-blocking: drop `backdrop="static"`,
    consider `backdrop=False` or moving the "name category + commit" UI out
    of a `dbc.Modal` entirely into an always-visible sidebar/offcanvas panel
    (`dbc.Offcanvas` is a natural fit - stays open, doesn't backdrop the
    main content) so the user can lasso on the map while the panel is open
    and see the draft update live.
  - If keeping a modal, add an explicit "select more" affordance that
    closes the modal, lets the user lasso, and reopens it merging into the
    existing draft (basically automating "close → lasso → click Create
    Group From Selection again" but without the draft-wipe bug above) -
    more clicks than an offcanvas panel but a smaller structural change.
- Once fixed, re-verify the intended hybrid flow end-to-end: lasso → modal/
  panel pre-populates → edit selection → commit category A → lasso a
  different set of points → commit category B (A must still be listed in
  the preview) → Finish & Create Group → confirm both categories landed in
  the new column.

---

## Suggested verification after fixes

- Manual: repeat the flow above in a live browser session (not just direct
  callback invocation) since bug 3 in particular is a modal/backdrop
  interaction problem that direct-callback smoke tests can't catch.
- Re-run `PYTHONPATH=. pytest test/` (`conda run -n daily_driver` per the
  project's Python-env convention) after each fix - none of these are
  covered by the existing unit tests, so consider adding regression tests
  once the fixes land (e.g. a test asserting
  `populate_custom_group_from_selection` preserves a non-empty incoming
  draft; a test asserting `update_map`'s relayout data survives a
  `custom-color-overrides`-triggered rebuild).
