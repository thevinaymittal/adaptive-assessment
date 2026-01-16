#!/usr/bin/env python3
"""
Local testing script for Lambda functions
"""

import json
import os
from lambda_handler import assessment, validation

def test_assessment_start():
    """Test starting an assessment"""
    event = {
        "httpMethod": "POST",
        "path": "/api/assessment/start",
        "body": json.dumps({
            "student_id": 1,
            "session_type": "initial",
            "self_reported_level": "B1"
        }),
        "headers": {
            "Content-Type": "application/json"
        }
    }
    
    context = {}
    response = assessment(event, context)
    
    print("Assessment Start Response:")
    print(json.dumps(json.loads(response['body']), indent=2))
    return response

def test_health_check():
    """Test health check endpoint"""
    event = {
        "httpMethod": "GET",
        "path": "/",
        "headers": {}
    }
    
    context = {}
    response = assessment(event, context)
    
    print("Health Check Response:")
    print(json.dumps(json.loads(response['body']), indent=2))

if __name__ == "__main__":
    # Load .env
    from dotenv import load_dotenv
    load_dotenv()
    
    print("🧪 Testing Lambda functions locally...\n")
    
    try:
        test_health_check()
        print("\n" + "="*50 + "\n")
        # Uncomment when DB is ready
        # test_assessment_start()
    except Exception as e:
        print(f" Error: {e}")