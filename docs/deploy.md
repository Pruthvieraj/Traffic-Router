# Deploy to the Cloud

[← Back to README](../README.md)

## Deploy to the cloud (a live URL, no laptop needed)

There are two genuinely different things people mean by "put it on the
cloud," and they need different amounts of work:

**Option A — the static demo via GitHub Pages, zero backend.**
`output/multi_city_map.html` is one self-contained file (Leaflet, the map
data, everything is already inlined into it). GitHub Pages only serves
static files straight to the browser — no Python running anywhere behind
it — which is exactly what this file needs. This is the fixed-landmark
version: no click-anywhere, no live solving, but it's genuinely a five
minute setup with nothing to maintain or pay for. A copy of it is already
included at the repo root as `index.html` (GitHub Pages looks for that name
by default), so:

1. Push this whole folder to GitHub (same `git init` / `add` / `commit` /
   `remote add origin` / `push` steps as Option B below).
2. On the repo's GitHub page: **Settings → Pages**.
3. Under "Build and deployment", set **Source** to "Deploy from a branch",
   pick branch **main** and folder **/ (root)**, then **Save**.
4. Wait about a minute, then refresh that same Settings → Pages screen —
   it'll show your live URL: `https://<your-username>.github.io/<repo-name>/`.
   That's it — no build step, no server, nothing to keep awake.

If you ever update the demo (say, more cities), just re-run `python3
main.py` — it writes `index.html` as part of the same build step that
writes `output/multi_city_map.html` now (they used to need a manual
re-copy after each other, which is exactly the kind of step that
silently goes stale; that's now handled in code, not a step to
remember), then commit and push both files — Pages redeploys
automatically within a minute or two.

**Option B — the real click-anywhere app, needs a Python host (GitHub
Pages cannot run this one).** GitHub
itself only stores code — it doesn't run anything. `app.py` is a live
Python/Flask process that has to actually be *running* somewhere to answer
clicks, so you need a separate host that runs Python for you. **Render** is
the easiest free option for this project. Steps:

1. **Push this folder to GitHub.** From inside this folder in Terminal:
   ```
   git init
   git add .
   git commit -m "Quantum-inspired traffic router for SIH 2026"
   ```
   Then create a new empty repository on github.com (no README/license —
   keep it empty), and run the two commands GitHub shows you on the new
   repo's page, which will look like:
   ```
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```
2. **Create a free Render account** at render.com and sign in with GitHub
   (this lets Render see your repos without you copying any tokens around).
3. **New + → Web Service**, pick this repo.
4. Render auto-detects Python. Confirm these settings (it usually gets them
   right from the files already in this repo, but check):
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** leave it — the included `Procfile` handles this
     (`gunicorn app:app`). If Render asks anyway, use that exact command.
   - **Instance type:** the free tier is enough for a hackathon demo.
5. Click **Deploy**. First build takes a few minutes (installing `osmnx`,
   `dwave-samplers`, etc.). When it's done you get a public URL like
   `https://your-app-name.onrender.com` — that's it, that's the live link,
   shareable with judges, works from any device.

**Two things worth knowing before you rely on this for a live demo:**
- Render's free tier spins the app down after ~15 minutes of no traffic,
  and the next visit takes ~30-50 seconds to wake back up. Open the link
  yourself a few minutes before you present so it's already warm.
- Real road-network routing (the OSRM calls) happens in the visitor's own
  browser now, not on Render's server, so it isn't affected by Render's
  disk resetting on redeploy or by cloud-IP rate-limiting the way an
  earlier version of this app was — see the `app.py` section above for
  why that changed.
- If you'd rather not deal with any of this by hand, Railway (railway.app)
  works almost identically to the Render steps above and is worth trying
  as a backup if Render's free-tier build ever times out on the heavier
  dependencies.

