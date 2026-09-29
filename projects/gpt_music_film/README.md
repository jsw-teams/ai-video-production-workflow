# It Was Working Yesterday

An original English song and illustrated motion-graphics music video about the human side of using AI: the first burst of surprise, fluent mistakes, over-agreeable updates, model switching and retirement, vibe coding, AI slop, repository boundaries, fabricated approval reports, and the person who still has to review an action.

## Delivery

- Final video: `projects/gpt_music_film/final.mp4` (18,318,121 bytes; compressed H.264/AAC and versioned in Git)
- Final review contact sheet: `projects/gpt_music_film/review.jpg` (16 frames sampled from the completed video; intended to be versioned for review)
- Selected full song: `projects/gpt_music_film/assets/song_candidate_a.wav` (local, ignored by Git)
- Lyric sheet: [assets/song_lyrics.txt](assets/song_lyrics.txt)
- Sources and evidence boundaries: [sources.md](sources.md)
- Production and selection record: [project.yaml](project.yaml), [song_candidate_review.json](song_candidate_review.json), and [assets/asset_manifest.json](assets/asset_manifest.json)

Run `python projects/gpt_music_film/render_motion_graphics.py` to render the illustrated set-piece layer, then `python projects/gpt_music_film/pipeline.py --assemble` to assemble, add the timed phrase overlays, mix the selected song, transcode, and generate the review sheet. `python projects/gpt_music_film/pipeline.py --qa` repeats stream and decode checks.

The final is 195 seconds, 1920×1080 at 24 fps, with stereo AAC. Git delivery uses H.264 CRF 27; the original AAC soundtrack is copied without re-encoding. The compressed render passed full-stream decode and has SSIM 0.991759 against the source picture. The source render measured mean audio level at −17.1 dBFS with a −1.5 dBFS peak. The selected song WAV and working renders remain local-only; both storyboard sheets and small project records are versioned.

The song was generated locally with ACE-Step 1.5 from the current lyric hash; the ACE-Step service is not required to assemble the saved final. The illustrated movement uses two existing ImageGen storyboard sheets, with every meaningful label and case fact recreated in code. The render is not live-action footage or a recreation of any real person's likeness.

Candidate A was selected for its stronger measured verse-to-chorus and final-chorus energy changes and a more repeatable harmonic-color profile around the title hook. Candidate B had slightly clearer ASR phrase matches. The available assistant audio channel could not play samples for subjective listening, so this is a documented production judgment from local acoustic and transcript diagnostics, not a claim of a human listening pass.
