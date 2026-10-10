# Phonetics

Takes a `.mov` or `.mp4` and writes out what's in its sound: the words, spelled the way they came out, and every other sound spelled the way the style guide spells it. Moans, grunts, breath, the throat, skin on skin, wet, the bed, the sheets, the room. Each one is placed in time, tagged with what made it, and measured.

Every spelling comes from the style guide's pool (`style-guide/references/sounds.md` and `room-sounds.md`). The tool picks a pool form and applies the notation from `sounds.md` section 1. It never builds a sound out of letters on its own. A sound the pool has no spelling for is listed by name and left unspelled.

## Install

Install ffmpeg (`brew install ffmpeg` on a Mac), then:

```
cd phonetics
pip install -r requirements.txt
```

The first run downloads three models, about 2.5 GB in all: Whisper for the words, an AudioSet classifier for what kind of sound it is, and a phoneme recogniser for the mouth shape.

## Run

```
python transcribe.py clip.mov
python transcribe.py clip.mp4 --high Megan --low Ed
python transcribe.py clip.mov --start 62 --end 95 -o scene.md
python transcribe.py clip.mp4 --no-words --json
```

It writes `clip.sounds.md` next to the video unless `-o` names another file.

| Flag | What it does |
|---|---|
| `--high NAME`, `--low NAME` | Names for the higher and lower voice. Default "high voice" and "low voice". |
| `--split-hz HZ` | Pitch that splits the two voices. Default 165 Hz. Raise it for two higher voices, lower it for two lower ones. |
| `--start S`, `--end S` | Read only that stretch, in seconds. Times in the output stay clip times. |
| `--model` | Whisper size: `tiny`, `base`, `small` (default), `medium`, `large-v3`. Bigger is slower and hears words better. |
| `--language` | Spoken language. Default `en`. `auto` to detect. |
| `--no-words` | Skip the words. Sounds only, faster. |
| `--min-word-prob P` | Words Whisper is less sure of than this are heard as sound instead. Default 0.45. |
| `--json` | Also write every measurement to `<out>.json`. |

On a CPU a 16-second clip takes about a minute and a half. Use `--start` and `--end` on long videos.

## What comes out

**On the page.** One line per moment, in time order. A spoken line is in quotes, spelled the way it came out, and a sound made inside the line breaks it where it landed. A run of three or more like sounds is one line. Each line names what made it.

```
`00:00.6` **high voice** — "Don't stop! Right there!"
`00:03.5` **high voice** — —*AWH!*— · peak moan
`00:04.9` **low voice** — —*Unh—Unh—UNH*— · 3 sounds over 1.0 s, to 00:05.8
`00:06.3` **breath** — —*hh-hh-hh-hh*— · 4 sounds over 0.9 s, to 00:07.3
`00:07.8` **skin, rhythmic** — —*plap-plap-plap*— · 8 hits, one every 0.45 s, to 00:11.0
`00:11.7` **high voice** — —*Mmmmh*— · hum, mouth shape from formants
`00:12.9` **low voice** — "Come here"
`00:14.5` **high voice** — —*OHH?!*— · moan, mouth shape from formants, pitch rising
```

That's the test clip from `tests/make_clip.py`: synthetic voices and noise, so the classifier is unsure of most of it and the formants carry the mouth shapes. Real voices give it more to go on.

**Every sound, measured.** A table of every single sound: when, how long, what made it, what the classifier heard and how sure it was, the phonemes, the spelling, how loud, the pitch and which way it moved, and why a mark went on (cut off, rising, swallowed, breath before the voice).

**Heard, not spelled.** Sounds the pool has no spelling for (a sniff, a sneeze, a door), with a count.

## How a sound becomes a spelling

1. **Find it.** Every stretch louder than the room that isn't a word. A stretch with dips in it is split at the dips, so three grunts in a row are three sounds. Sharp hits are found separately on the percussive part of the sound, so a slap under a moan still turns up.
2. **Say what it is.** The AudioSet classifier names the kind (moan, groan, grunt, whimper, gasp, pant, sigh, slap, squish, creak, rustle...). Pitch says which voice. A hit with an instant attack and no pitch is skin even when the classifier isn't sure.
3. **Mouth shape.** The phoneme recogniser says which vowel or hum it's made of: ah, oh, ooh, uh, eh, ih, mm, nn. When it hears nothing it knows, the formants decide.
4. **Pick the pool form.** Kind and mouth shape pick the form: an open loud held vowel is a peak moan —*AWH*—, a short low cut-off uh is a thrust grunt —*unh*—, closed lips are a hum —*mmh*—, a short sharp high open vowel is a cry —*ah!*—.
5. **Notation**, from `sounds.md` section 1:
   - **Length** stretches the letter the pool stretches, three letters at most: *ah → ahh → ahhh*.
   - **Volume** sets the case, against the loudest 5% of the clip: *oh → Oh → OH*.
   - **A sharp loud attack** gets a *!*, one or two per run.
   - **Pitch rising** 2.5 semitones or more gets *?*, or *?!* when loud.
   - **Stopping dead** from near its peak in 30 ms gets an em dash: *ah—*.
   - **Getting 8 dB louder** inside one sound: *ah—AH!*
   - **Quiet with closed lips** is swallowed: *(mm)*.
   - **Breath before the voice** and **air after it** use the pool's *hah, hoh, hnnh, huhh* and *ahh-hh, ohh-h*.
6. **Runs.** Three or more like sounds close together join into one run. They're joined with hyphens when they're short and tight (*hh-hh-hh-hh*) and em dashes when they carry (*UNH—UNH—UNH*). Short breaths in a row are a pant. Rhythmic skin is hips, *plap*, and turns *fwap* once the hits sound wet. The voice and the body are two tracks and never go in one string.
7. **On the page.** Every sound goes in italics between em dashes: —*glk*—.

Spoken words get the style guide's line rules. A loud word is in caps and a quiet line is lowercase. A word held long is stretched, using the pool's own *pleaase, fuuuck, yesss, goood* where they fit. One word leaned on gets italics, and a pause inside a line gets an ellipsis.

## What it can't hear

- **Who.** It hears two voices by pitch, high and low. Two voices close in pitch get mixed up; move `--split-hz`.
- **Where the wet is.** It hears wet, and a mouth when the classifier hears it as one. It can't tell a mouth from a pussy from a hand.
- **Kissing.** The classifier has no kiss, so *smk*, *mp* and *mch* never come out.
- **Under the words.** A sound made in the middle of a word is part of the word. Hits inside words are left alone.
- **Exact timing of words.** Whisper's word edges are loose. The tool tightens them, but a sound right against a word can get trimmed.
- **Anything the pool doesn't spell.** That's listed, not spelled.

The labels and spellings are a first pass from the sound alone. Read them against the picture.

## Tests

```
python tests/test_pool.py                       # every spelling is in the pool
python tests/test_notation.py                   # the notation rules
python tests/test_notation.py clip.sounds.md    # also checks a written transcript
python tests/make_clip.py out_dir               # builds a test .mp4 and .mov with known sounds
```

`test_pool.py` finds the style guide in the synced skills folder, or set `STYLE_GUIDE_DIR`.
