# 🚀 Vercel Deployment - Complete Guide

## 📦 Project Structure for Vercel

```
adaptive-assessment/
├── api/
│   ├── assessment.py          # NEW - Vercel endpoint
│   ├── validation.py          # NEW - Vercel endpoint  
│   └── __init__.py           # Empty file
├── core/
│   ├── api.py                # Your existing assessment logic (renamed)
│   ├── validation_system.py  # Your existing validation logic (renamed)
│   └── __init__.py           # Empty file
├── vercel.json               # NEW - Vercel config
├── requirements.txt          # Updated dependencies
├── .env.example             # Environment template
└── README_VERCEL.md         # This guide
```

---

## 📝 Step 1: Restructure Files

### Create `api/assessment.py` (Vercel Endpoint)
```python
# api/assessment.py
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.api import app

# Vercel serverless handler
def handler(request):
    from mangum import Mangum
    asgi_handler = Mangum(app, lifespan="off")
    return asgi_handler(request, None)
```

### Create `api/validation.py` (Vercel Endpoint)
```python
# api/validation.py
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.validation_system import app

def handler(request):
    from mangum import Mangum
    asgi_handler = Mangum(app, lifespan="off")
    return asgi_handler(request, None)
```

### Create `api/__init__.py`
```python
# api/__init__.py
# Empty file - makes this a Python package
```

### Move Your Existing Files
```bash
# Create core directory
mkdir core

# Move existing files
mv api.py core/api.py
mv validation_system.py core/validation_system.py

# Create __init__.py
touch core/__init__.py
```

---

## 📝 Step 2: Create `vercel.json`

```json
{
  "version": 2,
  "name": "adaptive-assessment",
  "builds": [
    {
      "src": "api/assessment.py",
      "use": "@vercel/python"
    },
    {
      "src": "api/validation.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/api/assessment/(.*)",
      "dest": "api/assessment.py"
    },
    {
      "src": "/api/validation/(.*)",
      "dest": "api/validation.py"
    },
    {
      "src": "/(.*)",
      "dest": "api/assessment.py"
    }
  ],
  "env": {
    "DB_HOST": "@db_host",
    "DB_USER": "@db_user", 
    "DB_PASSWORD": "@db_password",
    "DB_NAME": "@db_name",
    "DB_PORT": "@db_port"
  },
  "functions": {
    "api/**/*.py": {
      "memory": 1024,
      "maxDuration": 10
    }
  }
}
```

---

## 📝 Step 3: Update `requirements.txt`

```txt
# Core Framework
fastapi==0.104.1
uvicorn==0.24.0
mangum==0.17.0

# Database
mysql-connector-python==8.2.0

# Data Processing  
pandas==2.1.3
numpy==1.26.2

# Validation
pydantic==2.5.0
python-dotenv==1.0.0
python-multipart==0.0.6
```

---

## 📝 Step 4: Create `.vercelignore`

```
node_modules
venv
__pycache__
*.pyc
.env
.git
.pytest_cache
*.md
!README.md
```

---

## 🚀 Step 5: Deploy to Vercel

### Option A: Via Vercel CLI (Recommended)

```bash
# 1. Install Vercel CLI
npm install -g vercel

# 2. Login
vercel login

# 3. Link project (first time only)
vercel link

# 4. Add environment variables
vercel env add DB_HOST production
# Enter: your-mysql-host.com

vercel env add DB_USER production  
# Enter: admin

vercel env add DB_PASSWORD production
# Enter: your_password

vercel env add DB_NAME production
# Enter: tulkka_live

vercel env add DB_PORT production
# Enter: 3306

# 5. Deploy to production
vercel --prod

# Your API will be live at:
# https://your-project.vercel.app
```

### Option B: Via GitHub (Auto-Deploy)

```bash
# 1. Push to GitHub
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/adaptive-assessment.git
git push -u origin main

# 2. Go to vercel.com
# 3. Click "Add New Project"
# 4. Import from GitHub
# 5. Add environment variables in Vercel dashboard:
#    - DB_HOST
#    - DB_USER
#    - DB_PASSWORD
#    - DB_NAME
#    - DB_PORT

# 6. Deploy!
```

---

## 📝 Step 6: Test Your API

```bash
# Get your Vercel URL
vercel ls

# Or from dashboard after deploy
export API_URL="https://your-project.vercel.app"

# Test health check
curl $API_URL/

# Test assessment start
curl -X POST $API_URL/api/assessment/start \
  -H "Content-Type: application/json" \
  -d '{
    "student_id": 1,
    "session_type": "initial"
  }'

# Test validation
curl $API_URL/api/validation/level-distribution
```

---

## ⚙️ Step 7: Update Frontend URLs

Update your frontend to use Vercel URLs:

```javascript
// Before (local)
const API_URL = 'http://localhost:8000'

// After (production)
const API_URL = 'https://your-project.vercel.app'
```

---

## 🔧 Troubleshooting

### "Module not found: mangum"
```bash
# Add to requirements.txt
echo "mangum==0.17.0" >> requirements.txt

# Redeploy
vercel --prod
```

### "Database connection timeout"
```bash
# Check if MySQL allows connections from Vercel IPs
# MySQL must be publicly accessible or allow Vercel's IP ranges

# Test connection locally first
mysql -h YOUR_HOST -u YOUR_USER -p YOUR_DB
```

### "Function execution timed out"
```json
// Increase timeout in vercel.json
{
  "functions": {
    "api/**/*.py": {
      "maxDuration": 10
    }
  }
}
```
**Note:** Free tier max is 10 seconds. Pro tier allows 60 seconds.

### "CORS errors"
Your FastAPI apps already have CORS enabled. If issues persist:

```python
# In core/api.py and core/validation_system.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📊 Vercel Dashboard

After deployment, monitor at: https://vercel.com/dashboard

**Check:**
- ✅ Function invocations
- ✅ Bandwidth usage
- ✅ Error logs
- ✅ Performance metrics

---

## 💰 Vercel Limits (Free Tier)

| Resource | Limit |
|----------|-------|
| Bandwidth | 100 GB/month |
| Function Invocations | Unlimited |
| Function Duration | 10 seconds |
| Function Memory | 1024 MB |
| Deployments | 100/day |
| Team Members | 1 |

**If you exceed:**
- Bandwidth: $40 per 100 GB
- Need 60s timeout: Upgrade to Pro ($20/month)

---

## 🎯 What Works on Vercel

✅ **Assessment API** - All endpoints
✅ **Validation API** - Most endpoints  
✅ **Question imports** - Small CSVs (<4MB)
✅ **Calibration reports** - If fast (<10s)
✅ **Auto HTTPS/SSL**
✅ **Auto scaling**

❌ **Daily scheduled jobs** (use external cron)
❌ **Large file uploads** (>4.5MB)
❌ **Long-running tasks** (>10s)

---

## 🔄 Workarounds for Limitations

### Daily Calibration (No Cron on Vercel)

**Option 1: Use External Cron Service**
```bash
# Use cron-job.org or EasyCron
# Schedule daily GET request to:
# https://your-project.vercel.app/api/validation/calibration-report
```

**Option 2: Use GitHub Actions (Free)**

Create `.github/workflows/daily-calibration.yml`:
```yaml
name: Daily Calibration

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM UTC daily

jobs:
  calibrate:
    runs-on: ubuntu-latest
    steps:
      - name: Run Calibration
        run: |
          curl -X GET https://your-project.vercel.app/api/validation/calibration-report?save_to_db=true
```

---

## 📝 Quick Commands

```bash
# Deploy
vercel --prod

# View logs
vercel logs

# Check deployments
vercel ls

# Remove project
vercel remove

# Pull environment variables
vercel env pull

# Test locally
vercel dev
```

---

## ✅ Deployment Checklist

- [ ] Files restructured (api/ and core/ folders)
- [ ] vercel.json created
- [ ] requirements.txt updated with mangum
- [ ] Environment variables added to Vercel
- [ ] MySQL is publicly accessible
- [ ] Tables created in database
- [ ] Deployed: `vercel --prod`
- [ ] Health check working: `curl https://your-url/`
- [ ] Assessment API tested
- [ ] Questions imported (or ready to import)
- [ ] Frontend updated with Vercel URL
- [ ] GitHub Actions setup for daily calibration (optional)

---

## 🎉 You're Live!

Your API is now running on Vercel:
```
https://your-project.vercel.app/api/assessment/start
https://your-project.vercel.app/api/validation/calibration-report
```

**Next Steps:**
1. Share URL with frontend team
2. Import questions via API
3. Test with real students
4. Monitor Vercel dashboard
5. Set up external cron for daily calibration

**Need help?** Check logs: `vercel logs --follow`