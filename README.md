# Cin7 Uploader

A web application for uploading CSV files and creating sales orders in Cin7.

## Features

- CSV file upload and parsing
- Column mapping configuration
- Data validation against Cin7 API
- Sales order creation in Cin7
- User authentication and authorization
- Client management
- Mapping templates
- **Email webhook automation** - Receive emails with CSV attachments via Missive webhooks
- **Order-level queue view** - Track individual order processing results (successful and failed)

## Tech Stack

### Backend
- Flask (Python)
- SQLAlchemy (Database ORM)
- Flask-JWT-Extended (Authentication)
- PostgreSQL

### Frontend
- React
- Tailwind CSS
- Radix UI components

## Setup

### Prerequisites
- Python 3.9+
- Node.js 16+
- PostgreSQL database

### Backend Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables in `.env`:
```
DATABASE_URL=postgresql://user:password@localhost:5432/database
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret-key
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
CORS_ORIGINS=http://localhost:3000
```

3. Run database migrations:
```bash
cd migrations
python run_migration.py
```

4. Start the Flask server:
```bash
python app.py
```

The backend will run on `http://localhost:5001`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm start
```

The frontend will run on `http://localhost:3000`

## Project Structure

```
cin7-uploader/
├── app.py                 # Flask application entry point
├── config.py              # Configuration settings
├── database.py            # Database models and setup
├── extensions.py           # Flask extensions
├── wsgi.py                # WSGI entry point for production
├── requirements.txt       # Python dependencies
├── cin7_sales/           # Cin7 API client and sales order logic
├── routes/                # Flask route handlers
├── migrations/            # Database migrations
├── scripts/              # Utility scripts
├── utils/                 # Utility functions
└── frontend/             # React frontend application
    ├── src/
    │   ├── components/   # React components
    │   ├── contexts/     # React contexts
    │   └── lib/          # Utility libraries
    └── public/
```

## Development

The application uses Flask for the backend API and React for the frontend. The frontend proxies API requests to the backend during development.

## Production

For production deployment, build the React frontend:
```bash
cd frontend
npm run build
```

The Flask app will serve the built frontend files from the `frontend/build` directory.

### Google Cloud Run Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions.

Quick deploy:
```bash
./deploy.sh
```

Or manually:
```bash
# Build and push
docker build -t gcr.io/YOUR_PROJECT_ID/cin7-uploader .
docker push gcr.io/YOUR_PROJECT_ID/cin7-uploader

# Deploy
gcloud run deploy cin7-uploader \
  --image gcr.io/YOUR_PROJECT_ID/cin7-uploader \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### Email Webhook Configuration

After deployment, configure Missive to send webhooks to:
```
https://your-service-url.run.app/api/webhooks/email
```

The webhook will:
- Extract client name from email subject (e.g., "Chida Chida" from "Scheduled Report -> Chida Chida Daily Sales Orders")
- Download CSV attachment
- Process orders individually to Cin7
- Track results in the Queue view (`/queue`)

## License

[Add your license here]

