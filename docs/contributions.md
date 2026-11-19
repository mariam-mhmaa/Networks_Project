# Contributions and provenance

This table uses the repository's recorded author identities, rather than
guessing personal names. The final submission can replace the handles with
the team's confirmed full names. Contributions are specific tasks, not percentages.

| Recorded contributor | Work evidenced by repository history |
|---|---|
| `roaawaleedahmed5-pixel` | Original production-station UART/SLIP/ATR/CRC work, standalone production/session/retry clients, native and hardware diagnostic material; contributor baseline commit `58622a0` |
| `mariam_mhmaa` | Initial inspection-station hotspot/Wi-Fi work and board association evidence; local environment exclusion and production main-task stack configuration |
| `RadwanNour` | Original toy-workshop operator screen, theme/artwork/animations, browser adapter, mock gateway, tests and interface handoff; original UI commit `a7de4fa` |
| `Ainour` | Integrated gateway/application architecture; completed B application and bounded recovery; shared station lifecycle; A/B integration; operator API, controls, history, aliases and raw serial recording; integration fixes, software tools and hardware-evidence review |

Git history remains in the development repository. The source ZIP excludes
`.git` metadata; this does not remove history from the repository.

## Third-party code

The shared station engine and retained inspection vendor tree contain **cJSON
1.7.19**, copyright Dave Gamble and cJSON contributors, under the MIT licence.
Preserve the source copyright headers and both supplied `LICENSE` files:

- `shared/station/vendor/cjson/LICENSE`
- `stations/inspection/main/vendor/cjson/LICENSE`

The vendor source and licence bytes are not edited by submission cleanup.
Their upstream provenance was documented in contributor vendor notes, retained
in the external pre-cleanup backup.

## Assignment authority

`reference/MCT431 Project Fall 26.pdf` is the official assignment.
`reference/MCT431_Milestone1_Team_Development_Guide.docx` is the original
team proposal, not an override of implemented/approved requirements.

Older planning/handoff/session documents and superseded development output
are preserved in the external pre-cleanup backup and Git history. Current
contracts are the six documents linked from the root README. Original evidence
bytes, dates, identities and measurements must not be rewritten to suggest
they came from a later implementation or a different hardware run.
