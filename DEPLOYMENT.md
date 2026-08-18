# 🚀 Deployment Guide: DocFetch AI

This guide walks you through deploying **DocFetch AI** with **Frontend on Vercel** and **Backend on Render / Railway / Cloud Run**.

---

## 🏗 Architecture Overview

- **Frontend (Vite + React SPA)**: Hosted on **Vercel** (Global CDN, fast load times, automatic SSL).
- **Backend (FastAPI + LangGraph + PyTorch)**: Hosted on **Render**, **Railway**, or **Fly.io** (supports persistent container execution with ML models).

---

## 1️⃣ Deploy Frontend on Vercel

### Step A: Push Code to GitHub
Make sure your latest code is committed and pushed to your GitHub repository:
```bash
git add .
git commit -m "Configure Vercel and production deployment"
git push origin main
```

### Step B: Import Project in Vercel
1. Go to [vercel.com](https://vercel.com) and log in with GitHub.
2. Click **"Add New..."** ➔ **"Project"**.
3. Select your repository.
4. In the configuration settings:
   - **Root Directory**: Click *Edit* and select `frontend`.
   - **Framework Preset**: `Vite` (automatically detected).
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
5. **Environment Variables**:
   Add the following environment variable:
   - `VITE_API_BASE_URL`: `https://your-backend-url.onrender.com` *(or your deployed backend URL)*
6. Click **Deploy**.

---

## 2️⃣ Deploy Backend on Render (Free / Recommended)

Because Python RAG applications use embedding libraries (`sentence-transformers`, `faiss`, `torch`), they run best on a Docker-capable container service like Render or Railway.

### Deploying on Render:
1. Go to [render.com](https://render.com) and sign in with GitHub.
2. Click **"New +"** ➔ **"Web Service"**.
3. Connect your repository.
4. Settings:
   - **Name**: `docfetch-backend`
   - **Runtime**: `Python 3` (or `Docker`)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
5. **Environment Variables**:
   Add the variables from your `.env` file:
   - `GROQ_API_KEY`: `your_groq_api_key`
   - `GOOGLE_API_KEY`: `your_gemini_api_key`
   - `TAVILY_API_KEY`: `your_tavily_key`
   - `QDRANT_URL`: `your_qdrant_url`
   - `QDRANT_API_KEY`: `your_qdrant_key`
   - `MONGODB_URL`: `your_mongodb_atlas_url`
   - `MONGODB_DB_NAME`: `adaptive_rag`
   - `ALLOW_JWT_FALLBACK`: `true`
   - `CORS_ORIGINS`: `https://your-frontend.vercel.app`
6. Click **"Create Web Service"**.
7. Copy your Render URL (e.g., `https://docfetch-backend.onrender.com`) and paste it as `VITE_API_BASE_URL` in your Vercel project settings.

---

## 3️⃣ Firebase Authentication Settings

1. In the **Firebase Console** ([console.firebase.google.com](https://console.firebase.google.com)):
2. Go to **Authentication** ➔ **Settings** ➔ **Authorized Domains**.
3. Add your Vercel domain:
   - `your-app-name.vercel.app`

---

## 4️⃣ Testing Your Live Deployment

1. Visit `https://your-app-name.vercel.app` in your browser.
2. Log in with Google or Email.
3. Test model switching and query generation.
