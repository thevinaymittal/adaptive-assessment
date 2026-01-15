from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, validator
from typing import List, Dict, Optional
import pandas as pd
import mysql.connector
from mysql.connector import pooling
import json
import io
import os
from datetime import datetime
from collections import defaultdict
import numpy as np

# ==================== CONFIGURATION ====================

db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "pool_name": "validation_pool",
    "pool_size": 5
}

connection_pool = pooling.MySQLConnectionPool(**db_config)

# ==================== MODELS ====================

class QuestionValidationMetrics(BaseModel):
    question_id: int
    total_attempts: int
    correct_attempts: int
    accuracy_rate: float
    avg_time_seconds: float
    student_levels_attempted: Dict[str, int]
    expected_level: str
    recommended_level: Optional[str] = None
    confidence_score: float
    needs_review: bool = False
    
class CalibrationReport(BaseModel):
    report_id: Optional[int] = None
    total_questions: int
    questions_needing_review: int
    misclassified_questions: List[Dict]
    level_accuracy: Dict[str, float]
    recommendations: List[str]
    generated_at: datetime

class BulkImportResult(BaseModel):
    import_id: int
    total_rows: int
    successful_imports: int
    failed_imports: int
    errors: List[Dict]
    imported_question_ids: List[int]

# ==================== DATABASE UTILITIES ====================

def get_db_connection():
    return connection_pool.get_connection()

def execute_query(query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        
        if fetch_one:
            result = cursor.fetchone()
        elif fetch_all:
            result = cursor.fetchall()
        else:
            conn.commit()
            result = cursor.lastrowid
        
        return result
    except mysql.connector.Error as err:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(err)}")
    finally:
        cursor.close()
        conn.close()

# ==================== CSV VALIDATION ====================

REQUIRED_COLUMNS = [
    'question_text',
    'question_type',
    'difficulty_level',
    'skill_focus',
    'option_1',
    'option_2',
    'correct_answer'
]

VALID_QUESTION_TYPES = ['multiple_choice', 'fill_blank', 'ordering', 'audio_response']
VALID_DIFFICULTY_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
VALID_SKILL_TYPES = ['grammar', 'vocabulary', 'reading', 'listening']

def validate_csv_row(row: pd.Series, row_num: int) -> Dict:
    """Validate a single CSV row"""
    errors = []
    
    if pd.isna(row['question_text']) or not str(row['question_text']).strip():
        errors.append(f"Row {row_num}: question_text is empty")
    
    if row['question_type'] not in VALID_QUESTION_TYPES:
        errors.append(f"Row {row_num}: Invalid question_type. Must be one of {VALID_QUESTION_TYPES}")
    
    if row['difficulty_level'] not in VALID_DIFFICULTY_LEVELS:
        errors.append(f"Row {row_num}: Invalid difficulty_level. Must be one of {VALID_DIFFICULTY_LEVELS}")
    
    if row['skill_focus'] not in VALID_SKILL_TYPES:
        errors.append(f"Row {row_num}: Invalid skill_focus. Must be one of {VALID_SKILL_TYPES}")
    
    # Collect options
    options = []
    for i in range(1, 7):
        col = f'option_{i}'
        if col in row and pd.notna(row[col]) and str(row[col]).strip():
            options.append(str(row[col]).strip())
    
    if len(options) < 2:
        errors.append(f"Row {row_num}: At least 2 options required")
    
    # Validate correct answer
    correct_answer = str(row['correct_answer']).strip() if pd.notna(row['correct_answer']) else ''
    if not correct_answer:
        errors.append(f"Row {row_num}: correct_answer is empty")
    elif correct_answer not in options:
        errors.append(f"Row {row_num}: correct_answer '{correct_answer}' not found in options")
    
    return {
        'row_num': row_num,
        'errors': errors,
        'options': options,
        'is_valid': len(errors) == 0
    }

# ==================== BULK IMPORT WITH DB LOGGING ====================

def import_questions_from_csv(df: pd.DataFrame, uploaded_by: str = 'admin') -> BulkImportResult:
    """Import questions from validated DataFrame and log to database"""
    
    # Create import record
    import_query = """
        INSERT INTO question_import_history
        (uploaded_by, total_rows, import_status)
        VALUES (%s, %s, %s)
    """
    import_id = execute_query(import_query, (uploaded_by, len(df), 'processing'))
    
    successful = 0
    failed = 0
    errors = []
    imported_ids = []
    
    for idx, row in df.iterrows():
        row_num = idx + 2
        validation = validate_csv_row(row, row_num)
        
        if not validation['is_valid']:
            failed += 1
            errors.append({
                'row': row_num,
                'errors': validation['errors']
            })
            
            # Log error to database
            execute_query(
                """
                INSERT INTO question_import_errors
                (import_id, row_num, error_message)
                VALUES (%s, %s, %s)
                """,
                (import_id, row_num, json.dumps(validation['errors']))
            )
            continue
        
        try:
            options = validation['options']
            options_json = json.dumps(options)
            explanation = str(row['explanation']).strip() if pd.notna(row.get('explanation')) else None
            
            question_query = """
                INSERT INTO adaptive_assessment_questions
                (question_text, question_type, difficulty_level, skill_focus, 
                 options, correct_answer, explanation, imported_from_batch_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            question_id = execute_query(question_query, (
                str(row['question_text']).strip(),
                row['question_type'],
                row['difficulty_level'],
                row['skill_focus'],
                options_json,
                str(row['correct_answer']).strip(),
                explanation,
                import_id
            ))
            
            successful += 1
            imported_ids.append(question_id)
            
        except Exception as e:
            failed += 1
            errors.append({
                'row': row_num,
                'errors': [f"Database error: {str(e)}"]
            })
            
            execute_query(
                """
                INSERT INTO question_import_errors
                (import_id, row_num, error_message)
                VALUES (%s, %s, %s)
                """,
                (import_id, row_num, str(e))
            )
    
    # Update import record
    execute_query(
        """
        UPDATE question_import_history
        SET successful_imports = %s,
            failed_imports = %s,
            import_status = %s,
            completed_at = %s
        WHERE id = %s
        """,
        (successful, failed, 'completed', datetime.now(), import_id)
    )
    
    return BulkImportResult(
        import_id=import_id,
        total_rows=len(df),
        successful_imports=successful,
        failed_imports=failed,
        errors=errors,
        imported_question_ids=imported_ids
    )

# ==================== QUESTION CALIBRATION WITH DB STORAGE ====================

def analyze_question_performance(question_id: int, save_to_db: bool = True) -> QuestionValidationMetrics:
    """Analyze how a question performs and optionally save metrics to DB"""
    
    question = execute_query(
        """
        SELECT id, difficulty_level, skill_focus
        FROM adaptive_assessment_questions
        WHERE id = %s
        """,
        (question_id,),
        fetch_one=True
    )
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    responses = execute_query(
        """
        SELECT 
            r.is_correct,
            r.time_taken_seconds,
            s.final_detected_level,
            r.difficulty_at_question
        FROM student_assessment_responses r
        JOIN student_assessment_sessions s ON r.session_id = s.id
        WHERE r.question_id = %s AND s.completed_at IS NOT NULL
        """,
        (question_id,),
        fetch_all=True
    )
    
    if not responses:
        metrics = QuestionValidationMetrics(
            question_id=question_id,
            total_attempts=0,
            correct_attempts=0,
            accuracy_rate=0.0,
            avg_time_seconds=0.0,
            student_levels_attempted={},
            expected_level=question['difficulty_level'],
            confidence_score=0.0,
            needs_review=True
        )
        
        if save_to_db:
            save_question_metrics(metrics)
        
        return metrics
    
    # Calculate metrics
    total_attempts = len(responses)
    correct_attempts = sum(1 for r in responses if r['is_correct'])
    accuracy_rate = (correct_attempts / total_attempts) * 100
    avg_time = sum(r['time_taken_seconds'] for r in responses) / total_attempts
    
    # Analyze by student level
    level_distribution = defaultdict(int)
    level_accuracy = defaultdict(lambda: {'correct': 0, 'total': 0})
    
    for r in responses:
        student_level = r['final_detected_level']
        if student_level:
            level_distribution[student_level] += 1
            level_accuracy[student_level]['total'] += 1
            if r['is_correct']:
                level_accuracy[student_level]['correct'] += 1
    
    expected_level = question['difficulty_level']
    expected_level_idx = VALID_DIFFICULTY_LEVELS.index(expected_level)
    
    # Calculate confidence score
    weighted_scores = []
    for level, stats in level_accuracy.items():
        level_idx = VALID_DIFFICULTY_LEVELS.index(level)
        level_acc = stats['correct'] / stats['total']
        
        if level_idx >= expected_level_idx:
            weighted_scores.append(level_acc)
        else:
            weighted_scores.append(1 - level_acc)
    
    confidence_score = np.mean(weighted_scores) * 100 if weighted_scores else 0
    
    # Determine if needs review
    needs_review = False
    recommended_level = None
    
    if accuracy_rate > 85 and total_attempts > 10:
        if expected_level_idx > 0:
            needs_review = True
            recommended_level = VALID_DIFFICULTY_LEVELS[expected_level_idx - 1]
    
    elif accuracy_rate < 40 and total_attempts > 10:
        needs_review = True
        if expected_level_idx < len(VALID_DIFFICULTY_LEVELS) - 1:
            recommended_level = VALID_DIFFICULTY_LEVELS[expected_level_idx + 1]
    
    metrics = QuestionValidationMetrics(
        question_id=question_id,
        total_attempts=total_attempts,
        correct_attempts=correct_attempts,
        accuracy_rate=round(accuracy_rate, 2),
        avg_time_seconds=round(avg_time, 2),
        student_levels_attempted=dict(level_distribution),
        expected_level=expected_level,
        recommended_level=recommended_level,
        confidence_score=round(confidence_score, 2),
        needs_review=needs_review
    )
    
    if save_to_db:
        save_question_metrics(metrics)
    
    return metrics

def save_question_metrics(metrics: QuestionValidationMetrics):
    """Save question validation metrics to database"""
    
    query = """
        INSERT INTO question_validation_metrics
        (question_id, total_attempts, correct_attempts, accuracy_rate,
         avg_time_seconds, student_levels_attempted, expected_level,
         recommended_level, confidence_score, needs_review)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            total_attempts = VALUES(total_attempts),
            correct_attempts = VALUES(correct_attempts),
            accuracy_rate = VALUES(accuracy_rate),
            avg_time_seconds = VALUES(avg_time_seconds),
            student_levels_attempted = VALUES(student_levels_attempted),
            recommended_level = VALUES(recommended_level),
            confidence_score = VALUES(confidence_score),
            needs_review = VALUES(needs_review),
            last_calculated_at = CURRENT_TIMESTAMP
    """
    
    execute_query(query, (
        metrics.question_id,
        metrics.total_attempts,
        metrics.correct_attempts,
        metrics.accuracy_rate,
        metrics.avg_time_seconds,
        json.dumps(metrics.student_levels_attempted),
        metrics.expected_level,
        metrics.recommended_level,
        metrics.confidence_score,
        metrics.needs_review
    ))

def generate_calibration_report(save_to_db: bool = True) -> CalibrationReport:
    """Generate comprehensive calibration report and save to database"""
    
    questions = execute_query(
        "SELECT id FROM adaptive_assessment_questions",
        fetch_all=True
    )
    
    misclassified = []
    needs_review_count = 0
    level_stats = defaultdict(lambda: {'total': 0, 'accurate': 0})
    
    for q in questions:
        try:
            metrics = analyze_question_performance(q['id'], save_to_db=save_to_db)
            
            level_stats[metrics.expected_level]['total'] += 1
            
            if metrics.needs_review:
                needs_review_count += 1
                misclassified.append({
                    'question_id': metrics.question_id,
                    'current_level': metrics.expected_level,
                    'recommended_level': metrics.recommended_level,
                    'accuracy_rate': metrics.accuracy_rate,
                    'confidence_score': metrics.confidence_score,
                    'total_attempts': metrics.total_attempts
                })
            else:
                level_stats[metrics.expected_level]['accurate'] += 1
                
        except Exception as e:
            continue
    
    # Calculate level accuracy
    level_accuracy = {}
    for level, stats in level_stats.items():
        if stats['total'] > 0:
            level_accuracy[level] = round((stats['accurate'] / stats['total']) * 100, 2)
        else:
            level_accuracy[level] = 0.0
    
    # Generate recommendations
    recommendations = []
    
    if needs_review_count > len(questions) * 0.2:
        recommendations.append(f"⚠️ HIGH PRIORITY: {needs_review_count} questions ({round(needs_review_count/len(questions)*100, 1)}%) need review")
    
    for level, accuracy in level_accuracy.items():
        if accuracy < 70:
            recommendations.append(f"Level {level} has only {accuracy}% well-calibrated questions - needs expert review")
    
    if not recommendations:
        recommendations.append("✓ Question bank is well-calibrated!")
    
    report = CalibrationReport(
        total_questions=len(questions),
        questions_needing_review=needs_review_count,
        misclassified_questions=sorted(misclassified, key=lambda x: x['confidence_score']),
        level_accuracy=level_accuracy,
        recommendations=recommendations,
        generated_at=datetime.now()
    )
    
    if save_to_db:
        report_id = save_calibration_report(report)
        report.report_id = report_id
    
    return report

def save_calibration_report(report: CalibrationReport) -> int:
    """Save calibration report to database"""
    
    query = """
        INSERT INTO calibration_reports
        (total_questions, questions_needing_review, misclassified_questions,
         level_accuracy, recommendations, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    
    report_id = execute_query(query, (
        report.total_questions,
        report.questions_needing_review,
        json.dumps(report.misclassified_questions),
        json.dumps(report.level_accuracy),
        json.dumps(report.recommendations),
        report.generated_at
    ))
    
    return report_id

# ==================== QUESTION RECLASSIFICATION LOGGING ====================

def log_reclassification(question_id: int, old_level: str, new_level: str, reclassified_by: str, reason: str = None):
    """Log question reclassification to database"""
    
    query = """
        INSERT INTO question_reclassification_history
        (question_id, old_level, new_level, reclassified_by, reason)
        VALUES (%s, %s, %s, %s, %s)
    """
    
    execute_query(query, (question_id, old_level, new_level, reclassified_by, reason))

# ==================== API ENDPOINTS ====================

app = FastAPI(title="Question Validation & Import System")

@app.post("/api/validation/import", response_model=BulkImportResult)
async def bulk_import_questions(file: UploadFile = File(...), uploaded_by: str = 'admin'):
    """
    Bulk import questions from CSV
    
    Required CSV columns:
    - question_text
    - question_type (multiple_choice, fill_blank, etc.)
    - difficulty_level (A1, A2, B1, B2, C1, C2)
    - skill_focus (grammar, vocabulary, reading, listening)
    - option_1, option_2, option_3, option_4, option_5, option_6
    - correct_answer
    - explanation (optional)
    """
    
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required columns: {missing_cols}"
            )
        
        result = import_questions_from_csv(df, uploaded_by)
        
        return result
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="CSV file is empty")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

@app.get("/api/validation/question/{question_id}", response_model=QuestionValidationMetrics)
def validate_single_question(question_id: int, save_to_db: bool = True):
    """Analyze performance metrics for a specific question"""
    return analyze_question_performance(question_id, save_to_db=save_to_db)

@app.get("/api/validation/calibration-report", response_model=CalibrationReport)
def get_calibration_report(save_to_db: bool = True):
    """Generate comprehensive calibration report for entire question bank"""
    return generate_calibration_report(save_to_db=save_to_db)

@app.get("/api/validation/calibration-history")
def get_calibration_history(limit: int = 10):
    """Get historical calibration reports"""
    
    reports = execute_query(
        """
        SELECT id, total_questions, questions_needing_review, 
               level_accuracy, recommendations, generated_at
        FROM calibration_reports
        ORDER BY generated_at DESC
        LIMIT %s
        """,
        (limit,),
        fetch_all=True
    )
    
    for report in reports:
        report['level_accuracy'] = json.loads(report['level_accuracy']) if isinstance(report['level_accuracy'], str) else report['level_accuracy']
        report['recommendations'] = json.loads(report['recommendations']) if isinstance(report['recommendations'], str) else report['recommendations']
    
    return {
        'total_reports': len(reports),
        'reports': reports
    }

@app.get("/api/validation/questions-needing-review")
def get_questions_needing_review(min_attempts: int = 10):
    """Get list of questions that need expert review"""
    
    # Get from database (cached metrics)
    metrics = execute_query(
        """
        SELECT qvm.*, q.question_text, q.difficulty_level, q.skill_focus,
               q.options, q.correct_answer
        FROM question_validation_metrics qvm
        JOIN adaptive_assessment_questions q ON qvm.question_id = q.id
        WHERE qvm.needs_review = TRUE AND qvm.total_attempts >= %s
        ORDER BY qvm.confidence_score ASC
        """,
        (min_attempts,),
        fetch_all=True
    )
    
    for m in metrics:
        m['options'] = json.loads(m['options']) if isinstance(m['options'], str) else m['options']
        m['student_levels_attempted'] = json.loads(m['student_levels_attempted']) if isinstance(m['student_levels_attempted'], str) else m['student_levels_attempted']
    
    return {
        'total_questions_needing_review': len(metrics),
        'questions': metrics
    }

@app.put("/api/validation/reclassify/{question_id}")
def reclassify_question(question_id: int, new_level: str, reclassified_by: str = 'admin', reason: str = None):
    """Reclassify a question to a different CEFR level"""
    
    if new_level not in VALID_DIFFICULTY_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid level. Must be one of {VALID_DIFFICULTY_LEVELS}")
    
    # Get old level
    question = execute_query(
        "SELECT difficulty_level FROM adaptive_assessment_questions WHERE id = %s",
        (question_id,),
        fetch_one=True
    )
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    old_level = question['difficulty_level']
    
    # Update question
    execute_query(
        "UPDATE adaptive_assessment_questions SET difficulty_level = %s WHERE id = %s",
        (new_level, question_id)
    )
    
    # Log reclassification
    log_reclassification(question_id, old_level, new_level, reclassified_by, reason)
    
    # Recalculate metrics
    analyze_question_performance(question_id, save_to_db=True)
    
    return {
        "message": f"Question {question_id} reclassified from {old_level} to {new_level}",
        "question_id": question_id,
        "old_level": old_level,
        "new_level": new_level
    }

@app.get("/api/validation/reclassification-history/{question_id}")
def get_reclassification_history(question_id: int):
    """Get reclassification history for a question"""
    
    history = execute_query(
        """
        SELECT id, old_level, new_level, reclassified_by, reason, reclassified_at
        FROM question_reclassification_history
        WHERE question_id = %s
        ORDER BY reclassified_at DESC
        """,
        (question_id,),
        fetch_all=True
    )
    
    return {
        'question_id': question_id,
        'total_reclassifications': len(history),
        'history': history
    }

@app.get("/api/validation/level-distribution")
def get_level_distribution():
    """Get distribution of questions across CEFR levels and skills"""
    
    distribution = execute_query(
        """
        SELECT difficulty_level, skill_focus, COUNT(*) as count
        FROM adaptive_assessment_questions
        GROUP BY difficulty_level, skill_focus
        ORDER BY difficulty_level, skill_focus
        """,
        fetch_all=True
    )
    
    level_totals = defaultdict(int)
    skill_totals = defaultdict(int)
    total = 0
    
    for item in distribution:
        level_totals[item['difficulty_level']] += item['count']
        skill_totals[item['skill_focus']] += item['count']
        total += item['count']
    
    gaps = []
    for level in VALID_DIFFICULTY_LEVELS:
        for skill in VALID_SKILL_TYPES:
            count = next((d['count'] for d in distribution if d['difficulty_level'] == level and d['skill_focus'] == skill), 0)
            if count < 5:
                gaps.append(f"{level} {skill}: only {count} questions (need 5+ per level/skill)")
    
    return {
        'total_questions': total,
        'distribution': distribution,
        'level_totals': dict(level_totals),
        'skill_totals': dict(skill_totals),
        'gaps': gaps,
        'recommendations': gaps if gaps else ["✓ Good coverage across all levels and skills"]
    }

@app.get("/api/validation/import-history")
def get_import_history(limit: int = 20):
    """Get import history with error details"""
    
    imports = execute_query(
        """
        SELECT id, uploaded_by, total_rows, successful_imports, 
               failed_imports, import_status, created_at, completed_at
        FROM question_import_history
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
        fetch_all=True
    )
    
    for imp in imports:
        # Get errors for this import
        errors = execute_query(
            """
            SELECT row_num, error_message
            FROM question_import_errors
            WHERE import_id = %s
            ORDER BY row_num
            """,
            (imp['id'],),
            fetch_all=True
        )
        imp['errors'] = errors
    
    return {
        'total_imports': len(imports),
        'imports': imports
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)