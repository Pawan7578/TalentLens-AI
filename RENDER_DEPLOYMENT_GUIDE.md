# 🚀 TalentLens AI - Render Deployment Setup Guide

## Prerequisites
- Supabase account with PostgreSQL database
- Render account linked to GitHub
- GitHub repository with TalentLens AI code

## Step 1: Prepare Supabase Connection Details

### Get Connection String from Supabase:
1. Log in to [Supabase Dashboard](https://app.supabase.com)
2. Go to **Settings** → **Database** → **Connection String**
3. Click **URI** tab
4. Copy the connection string
5. Replace `[YOUR-PASSWORD]` with your actual password

Example format:
```
postgresql://postgres:PASSWORD@db.bibqskupbovfewijtila.supabase.co:5432/postgres
```

**Note:** Use Session mode (port 5432) not Transaction mode (port 6543)

## Step 2: Configure Environment Variables on Render

### For Backend Service:

Go to **Services** → **talentlens-backend** → **Environment**

Add these variables:

| Key | Value | Example |
|-----|-------|---------|
| `DATABASE_URL` | Your Supabase connection string | `postgresql://postgres:pass@db.host.supabase.co:5432/postgres` |
| `FRONTEND_URL` | Your frontend deployment URL | `https://talentlens-ai.onrender.com` |
| `AI_PROVIDER` | AI provider selection | `groq` |
| `GROQ_API_KEY` | Your Groq API key | `gsk_XXXXXXXXXXXXX` |
| `GROQ_MODEL` | Groq model name | `llama3-8b-8192` |
| `JWT_SECRET` | Secure random string (min 32 chars) | `your-super-secret-jwt-key` |
| `ADMIN_EMAIL` | Admin account email | `admin@company.com` |
| `ADMIN_PASSWORD` | Admin account password (secure!) | `SecurePassword123!` |
| `ADMIN_NAME` | Admin display name | `Admin` |
| `SMTP_HOST` | Email provider hostname | `smtp.gmail.com` |
| `SMTP_PORT` | Email provider port | `587` |
| `SMTP_USER` | Email sender address | `noreply@company.com` |
| `SMTP_PASSWORD` | Email app password | (not regular password) |
| `SMTP_FROM` | From: address in emails | `noreply@company.com` |
| `ALLOW_LOCALHOST_CORS` | Allow localhost in production | `false` |
| `NODE_ENV` | Environment type | `production` |

### For Frontend Service:

Go to **Services** → **talentlens-frontend** → **Environment**

Add this variable:

| Key | Value | Example |
|-----|-------|---------|
| `VITE_API_URL` | Backend API URL | `https://talentlens-backend-dnwt.onrender.com` |

## Step 3: Test Database Connection

### From browser console, visit:
```
https://your-backend.onrender.com/health
```

Should return:
```json
{
  "status": "healthy",
  "service": "TalentLens AI Backend",
  "ai_provider": "groq",
  "database": "connected"
}
```

If `database: "disconnected"`, check logs:
1. Click **talentlens-backend** service
2. Go to **Logs** tab
3. Look for database connection errors

## Step 4: Test CORS & Login

1. Visit frontend: `https://talentlens-ai.onrender.com`
2. Try to login with admin credentials
3. Check browser console for errors

If CORS error appears:
- Verify `FRONTEND_URL` is set correctly on backend
- Check logs for: `✅ CORS configured with X origins`
- Verify frontend `VITE_API_URL` matches backend service URL

## Step 5: Monitor Logs

### Backend Logs:
```
✅ CORS configured
✅ Database connection successful
🚀 Initialization complete
```

### Frontend Build Output:
```
✓ build complete
Routes configured
```

## Troubleshooting

### Error: "invalid connection option pgbouncer"
- ✅ **Already Fixed** - App automatically removes this parameter
- Uses connection pooling at app level

### Error: CORS policy
- Check `FRONTEND_URL` environment variable
- Verify frontend domain matches exactly
- Check `ALLOW_LOCALHOST_CORS=false` for production

### Error: "database connection failed"
- Verify `DATABASE_URL` has correct password
- Check Supabase is running (`System Health` in dashboard)
- Verify password doesn't contain special characters (URL encode if needed)
- Try removing query parameters from DATABASE_URL

### Error: "Application startup timeout"
- Usually means database connection taking too long
- Check Render logs for connection attempts
- Scale down other web services if resource-constrained

## Security Notes

⚠️ **DO NOT**:
- Commit `.env` file to git
- Share GROQ_API_KEY or JWT_SECRET
- Use weak passwords for ADMIN_PASSWORD

✅ **DO**:
- Use strong, unique passwords
- Store secrets in Render environment variables
- Rotate secrets periodically
- Use app passwords for email (not email password)

## Getting Help

Check logs in this order:
1. **Browser Console** - Frontend errors
2. **Render Logs** - Backend startup & runtime errors
3. **Supabase Dashboard** - Database status
4. **Health Endpoint** - `https://backend-url/health`

## Helpful Links
- [Supabase Connection Strings](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Render Environment Variables](https://render.com/docs/environment-variables)
- [Groq API Documentation](https://console.groq.com/docs)
