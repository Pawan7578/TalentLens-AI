# Render Environment Variables - Quick Reference

## Backend Service (talentlens-backend)

### Database
```
DATABASE_URL=postgresql://postgres:PASSWORD@db.bibqskupbovfewijtila.supabase.co:5432/postgres
```

### Frontend Integration
```
FRONTEND_URL=https://talentlens-ai.onrender.com
ALLOW_LOCALHOST_CORS=false
```

### AI Provider
```
AI_PROVIDER=groq
GROQ_API_KEY=gsk_XXXXXXXXXXXXX
GROQ_MODEL=llama3-8b-8192
```

### Authentication
```
JWT_SECRET=your-super-secret-32-character-jwt-secret-key
```

### Admin Account
```
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=YourSecurePassword123!
ADMIN_NAME=Admin
```

### Email Service
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=noreply@company.com
SMTP_PASSWORD=your-app-specific-password
SMTP_FROM=noreply@company.com
```

### Runtime
```
NODE_ENV=production
RENDER=true
```

## Frontend Service (talentlens-frontend)

### Backend Connection
```
VITE_API_URL=https://talentlens-backend-dnwt.onrender.com
```

## How to Set on Render

1. Log in to Render Dashboard
2. Select service (backend or frontend)
3. Go to **Settings** → **Environment**
4. Click **Add Environment Variable**
5. Enter Key and Value
6. Click **Save Changes** (auto redeploys)

## Important Notes

- 🔑 Keep secrets private (API keys, passwords)
- 🔒 Use strong passwords (min 12 characters)
- 📧 Use app-specific passwords for email (not your email password)
- 🌍 Frontend URL must match exactly with FRONTEND_URL on backend
- 🔄 Changes auto-trigger redeployment
- ✅ Check deployment logs after setting variables
