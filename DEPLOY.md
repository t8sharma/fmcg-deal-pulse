# Deployment guide

Two things to ship: **the code on GitHub** and **the demo on Streamlit Community Cloud** (free). ~10 minutes total.

---

## 1. Push the code to GitHub

From inside the `fmcg-deal-intel/` folder:

```bash
git init
git add .
git commit -m "FMCG Deal Pulse — deal-intelligence newsletter pipeline + Streamlit demo"
git branch -M main
```

Create an empty repo on GitHub (e.g. `fmcg-deal-pulse`), **without** a README/license (you already have them), then:

```bash
git remote add origin https://github.com/<your-username>/fmcg-deal-pulse.git
git push -u origin main
```

Your GitHub link is now `https://github.com/<your-username>/fmcg-deal-pulse`.
The `README.md` renders the architecture diagram and pipeline explanation automatically.

> Tip: paste the GitHub URL and (after step 2) the Streamlit URL into the **🔗 Links** table at the top of `README.md`.

---

## 2. Deploy the demo on Streamlit Community Cloud (free)

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **"Create app" → "Deploy a public app from GitHub"**.
3. Fill in:
   - **Repository:** `<your-username>/fmcg-deal-pulse`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Click **Deploy**. Streamlit installs `requirements.txt` automatically.
5. After ~1–2 minutes you get a public URL like
   `https://<your-app-name>.streamlit.app` — that's your **demo link**.

No secrets or API keys are required — the pipeline runs on keyless public RSS.

### Notes
- The app defaults to **Live news** mode and pulls fresh Google News RSS on Streamlit Cloud (which has outbound internet). If a fetch ever fails, it automatically falls back to the bundled sample dataset so the demo never breaks.
- Use the sidebar to switch to **Bundled sample (offline)** for a deterministic demo, and to tune the relevance / credibility / dedup thresholds live.

---

## 3. (Optional) Alternative hosts
- **Hugging Face Spaces** (Streamlit SDK): create a Space, set SDK = Streamlit, push the same files.
- **Render / Railway:** run `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`.

---

## 4. Regenerate the deliverable files locally
```bash
pip install -r requirements.txt
python -m pipeline.run            # writes data/outputs/{raw_data.csv,raw_data.json,newsletter.docx,newsletter.md}
```
