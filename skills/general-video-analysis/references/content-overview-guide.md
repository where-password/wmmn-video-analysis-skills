# Content Overview Guide

## Goal

Describe what the video communicates, not what objects happen to appear in its frames.

The base Skill is broad because it handles many kinds of video, not because it lists more visual details. The user should receive a concise content overview that works for narrative, knowledge, interview, vlog, scenery, product, review, meme, and other formats.

## User-facing scope

Show only:

1. one-sentence content judgment;
2. one content-summary paragraph;
3. content type;
4. content themes;
5. named works/characters when confidently identified;
6. content tone;
7. mocking/play targets when applicable;
8. optional, softly worded professional directions;
9. two short limitation notes.

Do not show:

- duration, resolution, FPS, codec, file size;
- shot count, cut count, cut density, median shot length;
- sampled-window timestamps, shot rows, keyframe details;
- object lists, character lists, action lists;
- key-segment breakdowns;
- camera, transition, prompt, or storyboard analysis.

Technical structure remains internal for downstream professional Skills.

## How to summarize

Ask:

- What is this video actually about?
- What does it say, show, demonstrate, tell, or present?
- What would a viewer take away from it?
- Is it a story, explanation, opinion, interview, experience, display, advertisement, or something else?

Do not infer the subject from a single visible object.

Example:

- A voice-over uses a dog sticker. The video is not about dogs; it may be about relationships, workplace frustration, or another topic in the narration.
- A person sits in a room and gestures. The gesture is not the subject unless it carries meaning in the video.
- A scenery video has no speaker. Its content can still be a landscape presentation, travel mood, or ambient visual experience.

## Original work versus remix and meme

Set `content_mode` from what the video actually does:

- `original`: a self-contained original story or presentation;
- `remix`: familiar scenes, characters, settings, or plot are replaced with another system, universe, nationality, visual style, or cast;
- `meme`: the main product is a joke, absurd contrast, reaction, or Internet-style bit;
- `adaptation`: a direct adaptation or re-edit of another work;
- `unknown`: the source relationship cannot be established from the available evidence.

A remix may look like a serious military drama on the surface. If the user says it replaces the original cast or military system with American soldiers while preserving the original plot, that is a remix/meme signal, not a reason to infer a serious theme about growth or discipline.

Do not identify a source title unless it is recognizable from the evidence or supplied by the user. It is safer to say "looks like a cross-system remix" than to guess the wrong series.

## Content theme rules

The theme must come from the video's actual content and visible purpose, not from genre conventions.

- Do not infer moral depth merely because the video contains soldiers, police, school, illness, or another serious-looking subject.
- If the video is primarily a joke, parody, remix, absurd edit, or meme, themes such as "整活", "反差", "影视二创", or "恶搞" are valid and often more accurate.
- Surface story and viewing purpose can be different. State the surface story in the summary, then name the actual theme.
- Do not turn visual identity into the theme. Race, species, character type, or visible objects are not themes by themselves.
- If the purpose is uncertain, use cautious wording and set `content_mode` to `unknown`.

For a cross-system military remix, a better theme set is:

- film/TV remix;
- cross-system replacement;
- absurd contrast or parody.

It is not automatically "growth", "discipline", "family legacy", or "personal maturity".

The same applies to other serious-looking subjects. LPL teams do not automatically imply support; military imagery does not automatically imply discipline; a fan remix does not automatically imply tribute. Use the actual stance evidence.

## Identify works, IPs, characters, and people

When the video clearly involves a known work, franchise, character, public figure, creator, or virtual persona, use the recognizable name instead of a generic description.

Record it in `ip_context`:

- `works`: franchise, series, film, novel, comic, game, song, tournament, or show;
- `characters`: fictional or virtual characters;
- `people`: real public figures, creators, artists, streamers, or performers;
- `domains`: useful broad categories such as anime, tokusatsu, novel, comic, film/TV, esports, rap, entertainment, internet creator, or VTuber;
- `confidence`: high, medium, low, or unknown;
- `evidence`: title, tag, caption, user context, logo, recognizable costume, or other concrete signal.

Use canonical names, with the Chinese name first when that is how the user recognizes it. Examples of the expected level:

- tokusatsu: 奥特曼系列, 迪迦, 贝利亚;
- anime: 火影忍者, 漩涡鸣人;
- novel: 三体, 罗辑;
- comic: 海贼王, 路飞;
- esports: LPL, a named team or player when confirmed;
- entertainment, rap, internet creator, or VTuber: the actual person or persona name when supported.

Rules:

- Name only what the evidence supports. A recognizable franchise may be enough to fill `works` while leaving `characters` or `people` empty.
- Do not flatten a known IP into "several Ultramen", "an anime character", or "a celebrity".
- Do not guess between similar costumes, recolor variants, AI-redrawn designs, or lookalike people from a single frame.
- If uncertain, use a cautious label such as "疑似" and set confidence to low.
- If no reliable IP evidence exists, leave `ip_context` empty rather than inventing one.

For the Ultraman screenshot example, title and tags support `works: ["奥特曼系列"]` and may support `characters: ["迪迦", "贝利亚"]` when the visible/context evidence matches. Other characters should remain unnamed if not confirmed.

## Stance, tone, and targets

Set `content_stance` separately from the subject:

- `supportive`: the video clearly supports or encourages;
- `critical`: the video mainly criticizes;
- `mocking`: the video mainly teases, parodies, or jokes at something;
- `neutral`: documentary, descriptive, or informational;
- `mixed`: several stances are meaningfully present;
- `unknown`: evidence is insufficient.

Set `content_tone` as observable wording or style, for example:

- serious, warm, sad, neutral record;
- playful, teasing, mocking, absurd, ironic.

For non-neutral stances, fill `tone_basis` with the visible evidence. Examples:

- adapted lyrics that complain about results;
- captions or titles that use ironic phrasing;
- editing that contrasts celebration footage with losses;
- user-provided context that identifies a parody.

Do not infer malice from teasing. Do not convert teasing into support, tribute, encouragement, growth, or a moral lesson.

`mocking_targets` is optional. Use it only when the video clearly teases a named subject, behavior, team, person, event, or institution.

### Worked example: e-sports fan remix

For a fan-made LPL MV that adapts a song and mocks four teams after losing every international match:

- do not write "出征应援" or "为选手打气";
- describe the surface content as adapted lyrics, match footage, player close-ups, and trophy shots;
- state the actual stance as teasing or mocking;
- use themes such as "LPL international performance", "fan meme-making", and "e-sports remix";
- recommend neither professional Skill unless the user separately asks for comic/AIGC production analysis or long-form lookup.

## Content type examples

Use natural, broad labels rather than a rigid taxonomy:

- narrative short / comic-style drama / animation;
- knowledge explainer / tutorial;
- interview / conversation;
- personal vlog / daily record;
- scenery / ambient video;
- product demonstration / review;
- commentary / opinion;
- comedy / meme / voice-over;
- remix / cross-system replacement;
- news / documentary;
- other.

## Routing fields

The model sets two internal booleans in `routing`:

- `comic_aigc_led`: the content is comic, animation, AIGC, or a comic/AIGC-oriented remix that could benefit from the specialized production Skill. Do not set this for a general live-action MV, vlog, product video, or e-sports montage merely because it has editing or visual effects;
- `longform_knowledge`: the content is knowledge-heavy long-form material where transcript-backed lookup would help.

Both can be true. Duration alone does not make `longform_knowledge` true. A long comic series can still be `comic_aigc_led: true` and `longform_knowledge: false`. A fan-made e-sports MV can be neither.

The renderer creates soft suggestions from these booleans:

- `comic_aigc_led` → suggest `professional-video-analysis`;
- `longform_knowledge` → suggest `long-video-index`;
- both → suggest both;
- neither → no specialist suggestion.

Suggestions remain optional. Do not invoke another Skill automatically.

## Insufficient information

If the model cannot access enough visual or transcript evidence, say so plainly and keep the overview limited. A useful limited output is better than an invented content summary.

A scenery, ambient, or silent video is not "insufficient" merely because no one speaks. Describe what it presents and what experience it offers.
