# lambda_handler.py
# AWS Lambda handlers for Assessment and Validation APIs

from mangum import Mangum
import os
import json

# Import your FastAPI apps
from core.api import app as assessment_app
from core.validation_system import app as validation_app, generate_calibration_report

# Wrap FastAPI apps with Mangum for Lambda compatibility
assessment_handler = Mangum(assessment_app, lifespan="off")
validation_handler = Mangum(validation_app, lifespan="off")

# Lambda handlers
def assessment(event, context):
    """
    Lambda handler for Assessment API
    Handles all /api/assessment/* routes
    """
    try:
        return assessment_handler(event, context)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "detail": str(e),
                "error_code": "INTERNAL_ERROR"
            }),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        }

def validation(event, context):
    """
    Lambda handler for Validation API
    Handles all /api/validation/* routes
    """
    try:
        return validation_handler(event, context)
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "detail": str(e),
                "error_code": "INTERNAL_ERROR"
            }),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        }

def scheduled_calibration(event, context):
    """
    Scheduled Lambda function to run daily calibration reports
    Triggered by CloudWatch Events (cron: daily at 2 AM UTC)
    """
    try:
        print("Starting scheduled calibration report...")
        
        # Generate calibration report and save to database
        report = generate_calibration_report(save_to_db=True)
        
        print(f"Calibration complete: {report.questions_needing_review} questions need review")
        
        # Optional: Send email/SNS notification if too many questions need review
        if report.questions_needing_review > report.total_questions * 0.2:
            # TODO: Send alert via SNS
            print(f"⚠️ ALERT: {report.questions_needing_review} questions need review!")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Calibration completed successfully",
                "report_id": report.report_id,
                "questions_needing_review": report.questions_needing_review,
                "total_questions": report.total_questions
            })
        }
        
    except Exception as e:
        print(f"Error in scheduled calibration: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e)
            })
        }

# Health check handler
def health_check(event, context):
    """
    Simple health check endpoint
    """
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "healthy",
            "service": "Adaptive Language Assessment",
            "version": "1.0.0",
            "environment": os.getenv("AWS_LAMBDA_FUNCTION_NAME", "local")
        }),
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        }
    }