# .env Configuration Guide - Development vs Production

## 📋 Quick Setup

### For Local Development:
```bash
cp backend/.env.template backend/.env
cp frontend/.env.template frontend/.env
# Edit .env files and fill in your values
```

### For Production (Render):
Use environment variables in Render dashboard (not .env files)

---

## 🔄 Configuration Comparison

| Setting | Development | Production |
|---------|-------------|-----------|
| `NODE_ENV` | `development` | `production` |
| `PORT` | `10000` | `$PORT` (Render) |
| `DATABASE_URL` | Local Supabase | Render env var |
| `FRONTEND_URL` | `http://localhost:5173` | `https://talentlens-ai.onrender.com` |
| `ALLOW_LOCALHOST_CORS` | `true` | `false` |
| `JWT_SECRET` | Dev key | Strong random key |
| `ADMIN_PASSWORD` | `Admin@123` | Strong password |
| `VITE_API_URL` | `http://localhost:10000` | Backend service URL |

---

## 🔐 Backend `.env` Template

```ini
# Environment
NODE_ENV=development
RENDER=false

# Server
PORT=10000

# Database (Supabase)
DATABASE_URL=postgresql://postgres:PASSWORD@db.bibqskupbovfewijtila.supabase.co:5432/postgres

# JWT Authentication
JWT_SECRET=your-32-character-random-secret-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# AI Provider (Groq)
AI_PROVIDER=groq
GROQ_API_KEY=gsk_YOUR_KEY
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_MODEL=llama3-8b-8192

# CORS
FRONTEND_URL=http://localhost:5173
ALLOW_LOCALHOST_CORS=true
CORS_ORIGINS=

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@company.com

# Admin Account
ADMIN_EMAIL=admin@company.com
ADMIN_NAME=Admin
ADMIN_PASSWORD=Admin@123

# File Uploads
UPLOAD_DIR=uploads
```

---

## 🎨 Frontend `.env` Template

```ini
# Backend API
VITE_API_URL=http://localhost:10000

# Debug
VITE_DEBUG=false
```

---

## 🚀 Production Environment Variables (Render)

### Set these in Render Dashboard → Service → Environment:

#### Backend Service:
```
DATABASE_URL = postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres
FRONTEND_URL = https://talentlens-ai.onrender.com
NODE_ENV = production
RENDER = true
ALLOW_LOCALHOST_CORS = false

AI_PROVIDER = groq
GROQ_API_KEY = gsk_XXXXX
GROQ_MODEL = llama3-8b-8192

JWT_SECRET = your-strong-random-secret-key
ADMIN_EMAIL = admin@company.com
ADMIN_PASSWORD = strong-secure-password

SMTP_HOST = smtp.gmail.com
SMTP_PORT = 587
SMTP_USER = your-email@gmail.com
SMTP_PASSWORD = app-specific-password
SMTP_FROM = noreply@company.com

UPLOAD_DIR = uploads
```

#### Frontend Service:
```
VITE_API_URL = https://talentlens-backend-dnwt.onrender.com
VITE_DEBUG = false
```

---

## 🔑 Getting Required Values

### Supabase
1. Go to [Supabase Dashboard](https://app.supabase.com)
2. Select your project
3. Settings → Database → Connection String
4. Copy the URI (not Connection Pooler)
5. Format: `postgresql://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres`

### Groq API Key
1. Go to [Groq Console](https://console.groq.com)
2. Create API key
3. Copy the key (starts with `gsk_`)

### Gmail App Password
1. Go to [Google Account](https://myaccount.google.com)
2. Security → App passwords
3. Select "Mail" and "Windows Computer"
4. Copy the generated password

### JWT Secret (Generate random)
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## ✅ Verification Checklist

### Local Development
- [ ] `.env` file created in `backend/` with all values
- [ ] `.env` file created in `frontend/` with API URL
- [ ] `npm run dev` starts frontend at `http://localhost:5173`
- [ ] Backend runs on `http://localhost:10000`
- [ ] Login works with admin credentials
- [ ] `/health` endpoint returns `{"status": "healthy"}`

### Production (Render)
- [ ] All environment variables set in Render dashboard
- [ ] Backend service rebuilds after variable changes
- [ ] Frontend service rebuilds after variable changes
- [ ] Login works at `https://talentlens-ai.onrender.com`
- [ ] Health check passes: `https://backend-url/health`
- [ ] No CORS errors in browser console

---

## 🆘 Common Issues

### "invalid connection option pgbouncer"
✅ Already fixed in code - app strips this parameter

### CORS Error blocking login
- Check `FRONTEND_URL` matches your domain exactly
- Verify `ALLOW_LOCALHOST_CORS=false` in production
- Check logs: `✅ CORS configured with X origins`

### Database connection timeout
- Verify `DATABASE_URL` has correct password
- Check Supabase status
- Verify port is 5432 (not 6543)

### API key errors
- Verify `GROQ_API_KEY` is correct
- Check key hasn't expired on Groq console
- Verify `AI_PROVIDER=groq`

---

## 🔒 Security Reminders

⚠️ **DO NOT**:
- Commit `.env` to Git
- Share API keys or passwords
- Use weak passwords
- Use regular email passwords for SMTP

✅ **DO**:
- Store secrets in environment variables only
- Use app-specific passwords for email
- Rotate secrets periodically
- Keep backups of credentials securely
