# Brahma workspace design

## Product direction

An investigation is a working document, not a dashboard of decorative cards.
Give the subject and decision context a stable position, keep evidence readable,
and make uncertainty as visible as the score.

- Local Geist variable font, white working surfaces, neutral navigation, restrained green actions.
- A full-width risk summary replaces the narrow assessment sidebar.
- Three evidence views separate media, risk signals, and source records without discarding data.
- Ranked term buttons replace the word cloud. Counts and bars support comparison; type size does not imply severity.
- Language annotations use expandable articles with readable line lengths, not a nested scrolling table.
- Article metadata moves under the headline on small screens. Filters become an explicit disclosure.
- The existing analysis report retains its overview, team, evidence, and challenge views.

## Motion

Motion communicates state changes. There is no idle animation or entrance sequence on initial load.

- Panel transitions: 180 ms with a 6px offset.
- Expanded details: 140 ms.
- Updated evidence rows: staggered within a 240 ms total budget.
- Horizontal data fills animate their scale, not their layout width.
- Reduced-motion preferences and backgrounding cancel animations. Content remains visible if animation is unavailable.
- No animation takes focus or waits before an action is usable.

## Research and references

These references informed the design. No remote skill installer or project hook was run.

1. [Impeccable](https://github.com/pbakaus/impeccable): critique, simplify, harden, then polish; avoid generic card-heavy interfaces.
2. [Anthropic frontend-design skill](https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md): domain-specific composition and purposeful, action-driven motion.
3. [Reddit discussion of frontend design skills](https://www.reddit.com/r/ClaudeCode/comments/1qg7slp/which_claude_skills_for_frontend_design_are_good/): community experiences are mixed; a skill is not a substitute for concrete design constraints and visual review.
4. [Linear's interface refresh](https://linear.app/now/behind-the-latest-design-refresh): predictable actions, quieter chrome, reduced visual noise, and clearer hierarchy.
5. [IBM Carbon motion guidance](https://v10.carbondesignsystem.com/guidelines/motion/overview/): short, productive motion for repeated working interactions.

The implementation keeps Brahma's existing vanilla frontend and local asset delivery.
The Geist license is retained in `static/vendor/GEIST-LICENSE.txt`.

## Accuracy constraints

- Sample investigations remain explicitly labeled and are not live screening.
- An unavailable source is not rendered as a clean result.
- Term counts are article counts, deduplicated within an article.
- Category counts can overlap; they are not exclusive shares of a whole.
- Media language flags are not factual verification.
- Every existing external-link safety and escaping boundary must remain intact.
