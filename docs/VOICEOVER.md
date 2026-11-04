# Voiceover lines for the 3-minute demo video

One line per clip, in order. Generate one audio file per line, named as shown, so it drops onto the matching screen clip (`clipNN_*.mp4`, recorded by `scripts/record_demo.js`). The words match `docs/DEMO-PITCH.md`; **change both together**.

Pace: about 150 words a minute (2.5 words a second). Warm, plain, unhurried. Leave about 0.3 s of silence at the start and end of each file.

**Pronunciation**
- **PJ:** "pee-jay".
- **988:** "nine-eight-eight".
- **Muse Spark / Muse Wonder:** "myooz".
- **kappa:** "KAP-uh".
- **Rosa:** "ROH-sah".

**Label:** if the voice is synthetic, put "AI-generated voice" in the video's end card or description.

| File | Clip | Target | Line |
|---|---|---|---|
| `vo01_problem` | clip01_problem | 0:00–0:20 (~19 s) | Healthcare is built for the doctor's office, not for you. Benefits are buried, bills are wrong, denials take weeks of calls, and the work lands on families: 53 million Americans are unpaid caregivers, many of them adult kids on hold for a parent. |
| `vo02_product` | clip02_product | 0:20–0:35 (~12 s) | This is PJ Health. You tell PJ what you need, and PJ's crew of AI agents does the calls, the forms, the appeals and the follow-ups. You just decide and sign. |
| `vo03_mom` | clip03_mom | 0:35–0:55 (~17 s) | Alex cares for their mom, Rosa: 78, Medicare Advantage, lives alone, fell this spring. Rosa gave Alex power of attorney, so Alex can sign for her. PJ found nine benefits she isn't using, like rides her plan already covers. One tap: "Do it, PJ." |
| `vo04_appeal` | clip04_appeal | 0:55–1:40 (~42 s) | Her plan denied home physical therapy. Alex snaps a photo of the letter. Muse Spark reads the reason, the plan's four rules and the real deadline, then phones her doctor's office for a letter: works the menu, waits on hold, says it's an AI, refuses to give out her address. Muse Wonder maps her records to each rule; Spark writes the appeal. Then the insurer goes first: open-weights Muse Spark plays the plan's reviewer and tries to deny it. Spark answers every objection. What can't be fixed becomes a plain to-do. Nothing leaves until Alex signs, and if the plan still says no, PJ files the outside review. |
| `vo05_gym` | clip05_gym | 1:40–2:15 (~33 s) | Healthcare can't run on vibes, so we built a proving ground. Six hundred simulated hostile offices: data fishers, fake "HIPAA verification", AI refusers, Spanish-first lines, voicemail. The caller stayed 100% safe and reached the right outcome every time. Two judges from different deployments agree at a kappa of about 0.85. The reader gets 99% of fields right from clean photos and 91% from bad ones. And every failure the gym or the judges found, we fixed and re-ran on fresh offices. |
| `vo06_swarm` | clip06_swarm | 2:15–2:35 (~13 s) | Need an appointment? PJ checks the real public directories, then calls 15 offices at once and holds the best slot for a yes: 15 live Muse Spark calls in under a minute. |
| `vo07_close` | clip07_close | 2:35–3:00 (~22 s) | Same crew for wrong bills, rides, equipment and cut home care hours. Crisis words get 988 before any model sees them. Everything that faces the patient runs on Meta's models; open weights play the adversary. Consent gates, a red team at 100%, 160 tests. PJ Health: your healthcare, owned by you. |

Total: about 400 words, about 2:40 of speech, leaving room for pauses on clicks.

**If a line runs long:** `vo04_appeal` is the longest; its screen clip runs about 2:15 raw, so speed up the wait between "clicked Start" and "crew finished" (see `clips.json`). If the whole video is over 3:00, cut `vo06_swarm` to: "Need an appointment? PJ calls 15 offices at once and holds the best slot."
