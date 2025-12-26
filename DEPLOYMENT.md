# Deployment Guide for Google Cloud Run

## Prerequisites

1. Google Cloud Project with billing enabled
2. Cloud Run API enabled
3. Container Registry API enabled
4. Cloud Build API enabled (if using automated builds)
5. PostgreSQL database (Cloud SQL or external)

## Environment Variables

### Easy Setup Options

1. **Admin UI (Recommended)**: Go to Admin → Deployment tab, paste your `.env` file, and copy the generated command
2. **Upload Script**: Run `./scripts/upload_env_to_cloudrun.sh .env` from the project root
3. **Manual**: Use gcloud commands (see below)

### Required Variables

Set these in Cloud Run service configuration:

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Flask secret key (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `JWT_SECRET_KEY` - JWT signing key (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `FLASK_ENV=production`

### CORS Configuration
- `CORS_ORIGINS` - Comma-separated list of allowed origins (e.g., `https://yourdomain.com,https://www.yourdomain.com`)

### Google OAuth (if using)
- `GOOGLE_CLIENT_ID` - Google OAuth client ID
- `GOOGLE_CLIENT_SECRET` - Google OAuth client secret
- `GOOGLE_REDIRECT_URI` - OAuth callback URL (e.g., `https://your-service.run.app/api/auth/google/callback`)
- `FRONTEND_URL` - Frontend URL (e.g., `https://yourdomain.com`)

### Supabase (if using)
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_JWT_SECRET`
- `SUPABASE_SERVICE_ROLE_KEY`

### Email (if using)
- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USE_TLS`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`

## Deployment Steps

### Option 1: Manual Deployment with gcloud

1. **Build and push the image:**
   ```bash
   # Set your project ID
   export PROJECT_ID=your-project-id
   
   # Build the image
   docker build -t gcr.io/$PROJECT_ID/cin7-uploader .
   
   # Push to Container Registry
   docker push gcr.io/$PROJECT_ID/cin7-uploader
   ```

2. **Deploy to Cloud Run:**
   ```bash
   gcloud run deploy cin7-uploader \
     --image gcr.io/$PROJECT_ID/cin7-uploader \
     --platform managed \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars FLASK_ENV=production \
     --memory 2Gi \
     --cpu 2 \
     --timeout 300 \
     --max-instances 10 \
     --min-instances 0
   ```

3. **Set environment variables:**

   **Option A: Use the Admin UI (Recommended)**
   - Go to Admin → Deployment tab
   - Paste your `.env` file content
   - Copy the generated gcloud command and run it
   - Or use the provided script: `./scripts/upload_env_to_cloudrun.sh .env`

   **Option B: Use the upload script:**
   ```bash
   ./scripts/upload_env_to_cloudrun.sh .env
   ```
   
   **Option C: Manual gcloud command:**
   ```bash
   gcloud run services update cin7-uploader \
     --region us-central1 \
     --update-env-vars DATABASE_URL=your-db-url,SECRET_KEY=your-secret-key,JWT_SECRET_KEY=your-jwt-key,CORS_ORIGINS=https://yourdomain.com
   ```

### Option 2: Automated Deployment with Cloud Build

1. **Enable Cloud Build:**
   ```bash
   gcloud services enable cloudbuild.googleapis.com
   ```

2. **Submit build:**
   ```bash
   gcloud builds submit --config cloudbuild.yaml
   ```

3. **Set environment variables** (same as Option 1, step 3)

## Database Migrations

Run migrations after deployment:

```bash
# Connect to Cloud Run service
gcloud run services proxy cin7-uploader --region us-central1 --port 8080

# Or use Cloud SQL Proxy if using Cloud SQL
# Then run migrations locally pointing to production DB
```

Or create a migration script that runs on startup (not recommended for production).

## Webhook URL

After deployment, your webhook URL will be:
```
https://cin7-uploader-xxxxx-uc.a.run.app/api/webhooks/email
```

Or if using a custom domain:
```
https://yourdomain.com/api/webhooks/email
```

Configure this URL in Missive webhook settings.

## Health Check

The app should respond to:
- `GET /` - Frontend
- `GET /api/auth/me` - Health check endpoint (requires auth)

## Monitoring

- View logs: `gcloud run services logs read cin7-uploader --region us-central1`
- Monitor in Cloud Console: Cloud Run → cin7-uploader → Logs

## Scaling

Default settings:
- Min instances: 0 (scales to zero)
- Max instances: 10
- Memory: 2Gi
- CPU: 2
- Timeout: 300 seconds

Adjust based on your needs:
```bash
gcloud run services update cin7-uploader \
  --region us-central1 \
  --memory 4Gi \
  --cpu 4 \
  --max-instances 20
```

## Troubleshooting

1. **Check logs:**
   ```bash
   gcloud run services logs read cin7-uploader --region us-central1 --limit 50
   ```

2. **Test locally with production config:**
   ```bash
   export FLASK_ENV=production
   export DATABASE_URL=your-db-url
   gunicorn --bind 0.0.0.0:8080 wsgi:app
   ```

3. **Verify environment variables are set:**
   ```bash
   gcloud run services describe cin7-uploader --region us-central1
   ```

