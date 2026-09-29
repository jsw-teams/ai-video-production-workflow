# A Date on the Calendar

An English illustrated documentary short for viewers familiar with Taiwan, Singapore, and the United States. The film asks why a public date is chosen, follows revolution, declaration, and separation through distinct historical examples, then returns to transit, event crews, meals, work, and the option to stay away. Its central observation is that sharing a public date does not give everyone the same private day.

## Delivery

- Film: `projects/guoqing/final.mp4` (75.958 seconds, 1920×1080, 24 fps, 12,211,934 bytes)
- Review contact sheet: `projects/guoqing/review.jpg`
- The compressed H.264/AAC film and storyboard sheets are versioned in Git; downloaded audio and working renders remain local-only.
- Rebuild from the repository root: `python projects/guoqing/prepare_storyboards.py`, then `python projects/guoqing/pipeline.py`

The film uses three original ImageGen 2×2 watercolor-and-ink storyboard sheets, cropped into twelve illustrated frames. FFmpeg adds restrained camera movement, paper-like date labels, readable English subtitles, and the edit. Git delivery is encoded as H.264 CRF 27; the original AAC track is copied without re-encoding. These images are editorial illustrations, not archival material, documentary evidence, or identifiable people.

The voiceover is offline Windows System.Speech. Sound combines the voice with three Freesound CC0 previews: generic city ambience, an event crowd, and one distant firework. This render has no music bed. Downloaded audio and working renders remain local-only; the compressed final film, storyboard sheets, source, scripts, captions, and production notes are versioned.

Historical wording and sound attribution are documented in [sources.md](sources.md). The U.S. date refers to congressional adoption of the Declaration on July 4, 1776; the parchment signing began later. Singapore's Act took effect August 9, 1965. The Taiwan wording follows the Office of the President's account of October 10 and the Wuchang Uprising. The film makes no political-system comparison and does not present one private response as universal.
