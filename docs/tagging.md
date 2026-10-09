# A recipe for labeling benchmark tests

How we label tests so that the labels can be trusted, checked and rebuilt. It is how
omni_parse_bench's tests got their tags (the definitions are `vocab.TAG_DEFINITIONS`), and applies to
any labeling of test items: the content a test checks, a page's kind, a test's difficulty, a form
field's role.

1. [The rules](#the-rules): the nine rules of the recipe; and
2. [The pieces to build once](#the-pieces-to-build-once): what a labeling needs beyond its vocabulary.

## The rules

1. Keep the label apart from the check. A test says what it compares and how; a label says what that
   content is. Grading never reads labels, so a wrong label can change which tests a query selects,
   never a verdict.

2. Label the smallest unit a label is true of, and combine by a stated rule. For tags the unit is the
   span (one piece of content a test compares), and a test's tags are the union of its spans' tags.
   Which places on the page count as a span's content follows from how its test passes: every place
   its text is printed for a `present` test, only the places in a table for a `table_cell` test.

3. Use one closed vocabulary, each label with a definition of what it is, what counts and what
   doesn't. That one text is what the models, the docs and the reviewer see; prompts are generated from
   it, never paraphrased. Most model errors trace to a definition that is silent on a case, so the
   first fix is to the definition.

4. Order the evidence from most to least certain, and stop at the first answer:
   - computed, where the label is its own definition (a script from Unicode, a font size, a rotation
     we made);
   - sources (publisher markup, form widgets, templates, build records);
   - a model panel.

   Each step answers yes, no or undecided, and undecided falls through to the next. A heuristic stays
   only while it is simple and checkable; once it needs a special case for a special case, the case
   goes to the models and to a person instead.

5. Keep the evidence independent of what it is checked against. Labels come from the page alone, never
   from what the test claims or from the tests' old content types. Those are the references the
   labels are compared with afterwards, and a disagreement points at a wrong label, a wrong
   definition or a wrong test, each worth finding.

6. Use a blind panel of two models, a third model on their splits, and a person for the rest. Each
   model sees the same images and the same definition and nothing else (not the benchmark, the test,
   the suite or other labels). The panel agrees: that is the label. The panel splits, or a model
   answers "can't tell" or says the marked place is wrong: the third model is asked, and a rule fixed
   per label from reviewed splits settles it. By default the third model must give the same answer as
   the panel model that was right more often; where that model gives no answer and the other two
   agree, their answer stands. `multi_column` and `language` take a majority of the three instead;
   `degraded` and `tiny` take that panel model's answer alone, since it was right wherever the panel
   split on them. A split no rule settles goes to a person. The models must not be ones whose results
   are reported. The prompt's form matters as much as its content:
   - say exactly what is marked and how (one box per place, one per line where text wraps);
   - ask for the reason first and the answer last;
   - name the answers after the property (`in_table`, `not_in_table`), so a "yes" can't be read as
     "yes, the text is here";
   - let the model say the marked place is wrong (`not_here`).

7. Measure every step, not only the models.
   - The audit: the blind panel is also asked about decisions made by sources and heuristics, and
     never changes them; agreement per step says which can be trusted.
   - The sample: a person checks a fixed random sample of decided items, which measures the accuracy
     of what nobody else looked at.
   - The references: disagreements with the tests' claims, and, as flags, with the tests' old
     content types.

8. Make it reproducible. The labels are a pure function of the inputs: the data, the sources, the
   vocabulary, the code, the pinned models, the answer cache and the person's corrections, applied
   last. Answers are cached under a hash of everything the model was shown, so changing one definition
   asks again only the questions it touches. Each label's record says how it was made and from what
   evidence (where the text was found, its font size, the language identifier's confidence).

9. Pilot on a small, diverse set, and fix causes, not cases. Sort the failures by cause (finding the
   content, judging it, the definition, the test itself) and fix each in the most general place: the
   definition, then the prompt, then the code. Rerun from the cache. On the tags' pilot, five rounds of
   this took the undecided count from 237 to 25, mostly by fixing causes rather than adding rules.

## The pieces to build once

- a review page: one item per screen, the images the models saw, every decision with how it was made
  and both models' answers and reasons, keyboard answers that save as corrections at once;
- the panel client and its cache, keyed by what the model was shown;
- the audit (an option of the labeling run) and the sample (a section of the review page); and
- the record of how each label was made.

What changes from one labeling to the next is the vocabulary and its definitions, the sources
available, and the unit labeled.
