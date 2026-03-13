#!/bin/bash
echo "🚀 Deploying DealHunt Backend..."

# Pull latest changes
git checkout stable
git pull origin stable

# Install dependencies (if needed)
pip install -r requirements.txt

# Restart application
if command -v pm2 &> /dev/null; then
    echo "📦 Restarting PM2..."
    pm2 restart dealhunt-backend
elif command -v docker-compose &> /dev/null; then
    echo "🐳 Restarting Docker..."
    docker-compose restart backend
else
    echo "⚠️  Please restart your application manually"
fi

echo "✅ Deployment complete!"
echo "📊 Scheduler will start automatically"
echo "🔄 Jobs will run on their schedule"
