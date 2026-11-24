# Contributing

## Changelog

`CHANGELOG.md` records every release. Add your change to its `## [Unreleased]` section in the same pull request.

- **Score impact.** A pull request that can change a verdict or a score adds a line under a `### Score impact`
  heading in `Unreleased`. That covers the scorer, normalization, the views, the test types, the summary's
  numbers, and the dataset expectations. Say which test types or folds change, and the direction (more or fewer
  passes). Give the counts from a regrade of saved predictions if you have them, or say they were not measured.
  If no verdict can change, say so.
- Put other changes under `Added`, `Changed`, `Fixed`, `Removed` or `Data and format`, one line each, with the
  pull request number.
- At release time, the `Unreleased` entries move under the new version's heading, with its tag date. Say whether
  the published leaderboard was regraded.
