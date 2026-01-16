#!/bin/bash
set -e

echo "Deploying Adaptive Assessment to AWS Lambda..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please create .env file from .env.example"
    exit 1
fi

# Load environment variables
export $(cat .env | xargs)

# Install Node.js dependencies
echo "Installing Node.js dependencies..."
npm install

# Install Python dependencies locally for testing
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Run tests (optional)
# echo "Running tests..."
# pytest tests/

# Deploy to AWS
echo "Deploying to AWS Lambda..."
serverless deploy --stage prod

# Get endpoint URLs
echo ""
echo "Deployment complete!"
echo ""
echo "API Endpoints:"
serverless info --stage prod | grep endpoint

echo ""
echo "Next steps:"
echo "1. Import questions: curl -X POST {API_URL}/api/validation/import -F 'file=@questions.csv'"
echo "2. Test assessment: curl {API_URL}/api/assessment/start -d '{\"student_id\": 1}'"
echo "3. View logs: npm run logs"