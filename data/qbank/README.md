# Question bank format (JEE / NEET / SSC / UPSC / Board / School)

One file per exam, named `<exam>.json`: `jee`, `neet`, `ssc`, `upsc`, `brd`, `sch`.

Use it in 2 ways (both work together):
1. **Online** (recommended): upload the files to a folder you control (e.g. a GitHub repo) and set
   `QBANK_BASE_URL=https://raw.githubusercontent.com/<user>/<repo>/main/questions` in Render/.env.
   The bot downloads `<exam>.json` from there and caches it (`QBANK_CACHE_HOURS`, default 6).
2. **Local**: put the files in this folder (`data/qbank/`).

```json
{
  "questions": [
    {
      "subject": "physics",
      "level": "medium",
      "question": "Question text here",
      "options": ["option 1", "option 2", "option 3", "option 4"],
      "answer": "B",
      "explanation": "Short reason (optional)"
    }
  ]
}
```

* `subject` must match the bot's subject button, lowercase: jee/brd -> physics, chemistry, maths · neet -> physics, chemistry, biology ·
  ssc -> reasoning, gk, maths, english · upsc -> polity, history, geography, economy. ("Mixed" uses every subject.)
* `level`: `easy` / `medium` / `hard` (optional).
* `answer`: `"A"`-`"D"` (or `"correct_index": 0-3`, or the exact option text).
* Exactly 4 different options. **Don't worry about the position of the correct option** — the bot re-shuffles it every time.
* Avoid "All of the above" / "Both A and B" options (they can't be shuffled safely).
* The files in this folder are only 6-question SAMPLES — replace them with your own checked questions.
