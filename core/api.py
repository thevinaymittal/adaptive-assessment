
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Literal
from datetime import datetime
from enum import Enum
import mysql.connector
from mysql.connector import pooling
import os
import json
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIGURATION ====================

app = FastAPI(
    title="Adaptive Language Assessment API",
    description="Adaptive testing system of Tulkka for English proficiency assessment (CEFR A1-C2)",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "language_school"),
    "pool_name": "assessment_pool",
    "pool_size": 10,
    "pool_reset_session": True
}

connection_pool = pooling.MySQLConnectionPool(**db_config)

# ==================== ENUMS & CONSTANTS ====================

class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

class SkillType(str, Enum):
    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"
    READING = "reading"
    LISTENING = "listening"

class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    ORDERING = "ordering"
    AUDIO_RESPONSE = "audio_response"

class SessionType(str, Enum):
    INITIAL = "initial"
    PERIODIC_RETEST = "periodic_retest"

CEFR_LEVELS_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]
SKILL_TYPES_ORDER = ["grammar", "vocabulary", "reading", "listening"]

# ==================== DATABASE MODELS ====================

class Question(BaseModel):
    id: int
    question_text: str
    question_type: QuestionType
    difficulty_level: CEFRLevel
    skill_focus: SkillType
    options: List[str]
    correct_answer: str
    next_question_if_correct: Optional[int] = None
    next_question_if_incorrect: Optional[int] = None
    average_time_seconds: Optional[int] = None

class StudentResponse(BaseModel):
    question_id: int
    student_answer: str
    time_taken_seconds: int

class AssessmentSession(BaseModel):
    id: int
    student_id: int
    session_type: SessionType
    started_at: datetime
    completed_at: Optional[datetime] = None
    final_detected_level: Optional[CEFRLevel] = None
    confidence_score: Optional[float] = None
    questions_answered: int = 0
    correct_answers: int = 0
    total_time_seconds: int = 0

# ==================== REQUEST/RESPONSE MODELS ====================

class StartAssessmentRequest(BaseModel):
    student_id: int
    session_type: SessionType = SessionType.INITIAL
    self_reported_level: Optional[CEFRLevel] = None

class StartAssessmentResponse(BaseModel):
    session_id: int
    first_question: Question
    total_questions: int = 10
    message: str = "Assessment started successfully"

class SubmitAnswerRequest(BaseModel):
    session_id: int
    question_id: int
    student_answer: str
    time_taken_seconds: int = Field(..., ge=0, description="Time taken in seconds")

    @validator('student_answer')
    def validate_answer(cls, v):
        if not v or not v.strip():
            raise ValueError("Answer cannot be empty")
        return v.strip()

class SubmitAnswerResponse(BaseModel):
    is_correct: bool
    correct_answer: Optional[str] = None
    next_question: Optional[Question] = None
    current_level: CEFRLevel
    questions_remaining: int
    is_complete: bool = False
    final_results: Optional[Dict] = None

class AssessmentResults(BaseModel):
    session_id: int
    student_id: int
    detected_level: CEFRLevel
    confidence_score: float
    questions_answered: int
    correct_answers: int
    total_time_seconds: int
    accuracy_percentage: float
    level_breakdown: Dict[str, Dict[str, int]]
    self_reported_level: Optional[CEFRLevel] = None
    level_difference: Optional[int] = None
    started_at: datetime
    completed_at: datetime

class QuestionCreateRequest(BaseModel):
    question_text: str
    question_type: QuestionType
    difficulty_level: CEFRLevel
    skill_focus: SkillType
    options: List[str] = Field(..., min_items=2, max_items=6)
    correct_answer: str
    next_question_if_correct: Optional[int] = None
    next_question_if_incorrect: Optional[int] = None

# ==================== DATABASE UTILITIES ====================

def get_db_connection():
    """Get database connection from pool"""
    return connection_pool.get_connection()

def execute_query(query: str, params: tuple = None, fetch_one: bool = False, fetch_all: bool = False):
    """Execute database query with connection pooling"""
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

# ==================== ADAPTIVE ALGORITHM ENGINE ====================

class AdaptiveEngine:
    """
    Adaptive testing algorithm based on Item Response Theory (IRT) principles
    tailored for language assessment with CEFR levels
    """
    
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.current_level = CEFRLevel.B1  # Start at intermediate
        self.responses = []
        self.skill_index = 0
        self.questions_asked = 0
        self.max_questions = 10
        
    def get_level_index(self, level: CEFRLevel) -> int:
        """Get numeric index for CEFR level"""
        return CEFR_LEVELS_ORDER.index(level)
    
    def increase_difficulty(self, level: CEFRLevel) -> CEFRLevel:
        """Move up one CEFR level"""
        idx = self.get_level_index(level)
        if idx < len(CEFR_LEVELS_ORDER) - 1:
            return CEFRLevel(CEFR_LEVELS_ORDER[idx + 1])
        return level
    
    def decrease_difficulty(self, level: CEFRLevel) -> CEFRLevel:
        """Move down one CEFR level"""
        idx = self.get_level_index(level)
        if idx > 0:
            return CEFRLevel(CEFR_LEVELS_ORDER[idx - 1])
        return level
    
    def get_next_skill(self) -> SkillType:
        """Rotate through skills for balanced assessment"""
        skill = SKILL_TYPES_ORDER[self.skill_index % len(SKILL_TYPES_ORDER)]
        self.skill_index += 1
        return SkillType(skill)
    
    def get_next_question(self) -> Optional[Question]:
        """
        Adaptive algorithm to select next question based on student performance
        """
        if self.questions_asked >= self.max_questions:
            return None
        
        # First question: always B1 grammar (warm-up)
        if self.questions_asked == 0:
            question = self._fetch_question(CEFRLevel.B1, SkillType.GRAMMAR)
        else:
            # Adjust difficulty based on last response
            if self.responses:
                last_response = self.responses[-1]
                if last_response['is_correct']:
                    self.current_level = self.increase_difficulty(self.current_level)
                else:
                    self.current_level = self.decrease_difficulty(self.current_level)
            
            # Get next skill to test
            skill = self.get_next_skill()
            question = self._fetch_question(self.current_level, skill)
        
        self.questions_asked += 1
        return question
    
    def _fetch_question(self, level: CEFRLevel, skill: SkillType) -> Optional[Question]:
        """Fetch a question from database matching level and skill"""
        query = """
            SELECT id, question_text, question_type, difficulty_level, 
                   skill_focus, options, correct_answer,
                   next_question_if_correct, next_question_if_incorrect,
                   average_time_seconds
            FROM adaptive_assessment_questions
            WHERE difficulty_level = %s AND skill_focus = %s
            ORDER BY RAND()
            LIMIT 1
        """
        
        result = execute_query(query, (level.value, skill.value), fetch_one=True)
        
        if result:
            # Parse JSON options
            result['options'] = json.loads(result['options']) if isinstance(result['options'], str) else result['options']
            return Question(**result)
        
        # Fallback: get any question at this level
        query_fallback = """
            SELECT id, question_text, question_type, difficulty_level, 
                   skill_focus, options, correct_answer,
                   next_question_if_correct, next_question_if_incorrect,
                   average_time_seconds
            FROM adaptive_assessment_questions
            WHERE difficulty_level = %s
            ORDER BY RAND()
            LIMIT 1
        """
        result = execute_query(query_fallback, (level.value,), fetch_one=True)
        
        if result:
            result['options'] = json.loads(result['options']) if isinstance(result['options'], str) else result['options']
            return Question(**result)
        
        return None
    
    def record_response(self, question: Question, student_answer: str, time_taken: int) -> bool:
        """Record student response and return if correct"""
        is_correct = student_answer.strip().lower() == question.correct_answer.strip().lower()
        
        self.responses.append({
            'question_id': question.id,
            'level': question.difficulty_level,
            'skill': question.skill_focus,
            'is_correct': is_correct,
            'time_taken': time_taken,
            'student_answer': student_answer
        })
        
        # Save to database
        query = """
            INSERT INTO student_assessment_responses 
            (session_id, question_id, question_sequence, student_answer, 
             is_correct, time_taken_seconds, difficulty_at_question)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        execute_query(query, (
            self.session_id,
            question.id,
            self.questions_asked,
            student_answer,
            is_correct,
            time_taken,
            question.difficulty_level.value
        ))
        
        return is_correct
    
    def calculate_final_level(self) -> Dict:
        """
        Calculate final CEFR level using weighted accuracy across levels
        Based on highest level with ≥60% accuracy and ≥2 questions
        """
        level_scores = {level: {'correct': 0, 'total': 0} for level in CEFR_LEVELS_ORDER}
        
        # Aggregate responses by level
        for response in self.responses:
            level = response['level'].value
            level_scores[level]['total'] += 1
            if response['is_correct']:
                level_scores[level]['correct'] += 1
        
        # Find highest level with satisfactory performance
        detected_level = CEFRLevel.A1
        confidence = 50.0
        
        for level in reversed(CEFR_LEVELS_ORDER):
            correct = level_scores[level]['correct']
            total = level_scores[level]['total']
            
            if total >= 2:  # Need at least 2 questions at this level
                accuracy = correct / total
                if accuracy >= 0.6:  # 60% threshold
                    detected_level = CEFRLevel(level)
                    confidence = round(accuracy * 100, 2)
                    break
        
        # Calculate overall statistics
        total_correct = sum(r['is_correct'] for r in self.responses)
        total_time = sum(r['time_taken'] for r in self.responses)
        
        return {
            'detected_level': detected_level,
            'confidence_score': confidence,
            'questions_answered': len(self.responses),
            'correct_answers': total_correct,
            'total_time_seconds': total_time,
            'accuracy_percentage': round((total_correct / len(self.responses)) * 100, 2) if self.responses else 0,
            'level_breakdown': level_scores
        }

# ==================== API ENDPOINTS ====================

@app.get("/")
def root():
    """API health check"""
    return {
        "status": "healthy",
        "service": "Adaptive Language Assessment API",
        "version": "1.0.0"
    }

@app.post("/api/assessment/start", response_model=StartAssessmentResponse)
def start_assessment(request: StartAssessmentRequest):
    """
    Start a new adaptive assessment session
    
    - Creates a new session in the database
    - Initializes adaptive engine
    - Returns first question (B1 grammar warm-up)
    """
    
    # Check if student exists
    student_check = execute_query(
        "SELECT id FROM users WHERE id = %s",
        (request.student_id,),
        fetch_one=True
    )
    
    if not student_check:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Check for existing incomplete session
    existing_session = execute_query(
        """
        SELECT id FROM student_assessment_sessions 
        WHERE student_id = %s AND completed_at IS NULL
        ORDER BY started_at DESC LIMIT 1
        """,
        (request.student_id,),
        fetch_one=True
    )
    
    if existing_session:
        raise HTTPException(
            status_code=400, 
            detail=f"Student has an incomplete assessment session (ID: {existing_session['id']}). Please complete or cancel it first."
        )
    
    # Create new session
    query = """
        INSERT INTO student_assessment_sessions 
        (student_id, session_type, started_at, self_reported_level)
        VALUES (%s, %s, %s, %s)
    """
    
    session_id = execute_query(query, (
        request.student_id,
        request.session_type.value,
        datetime.now(),
        request.self_reported_level.value if request.self_reported_level else None
    ))
    
    # Initialize adaptive engine and get first question
    engine = AdaptiveEngine(session_id)
    first_question = engine.get_next_question()
    
    if not first_question:
        raise HTTPException(status_code=500, detail="No questions available in the database")
    
    return StartAssessmentResponse(
        session_id=session_id,
        first_question=first_question,
        total_questions=10
    )

@app.post("/api/assessment/submit-answer", response_model=SubmitAnswerResponse)
def submit_answer(request: SubmitAnswerRequest):
    """
    Submit student's answer and get next question (or final results)
    
    - Records the response
    - Updates session statistics
    - Returns next adaptive question or completion status
    """
    
    # Validate session exists and is not completed
    session = execute_query(
        """
        SELECT id, student_id, questions_answered, correct_answers, 
               total_time_seconds, completed_at
        FROM student_assessment_sessions 
        WHERE id = %s
        """,
        (request.session_id,),
        fetch_one=True
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found")
    
    if session['completed_at']:
        raise HTTPException(status_code=400, detail="Assessment session already completed")
    
    # Fetch the question
    question_data = execute_query(
        """
        SELECT id, question_text, question_type, difficulty_level, 
               skill_focus, options, correct_answer
        FROM adaptive_assessment_questions
        WHERE id = %s
        """,
        (request.question_id,),
        fetch_one=True
    )
    
    if not question_data:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Parse options
    question_data['options'] = json.loads(question_data['options']) if isinstance(question_data['options'], str) else question_data['options']
    question = Question(**question_data)
    
    # Initialize engine and load previous responses
    engine = AdaptiveEngine(request.session_id)
    
    # Load previous responses for this session
    previous_responses = execute_query(
        """
        SELECT question_id, is_correct, difficulty_at_question, time_taken_seconds
        FROM student_assessment_responses
        WHERE session_id = %s
        ORDER BY question_sequence
        """,
        (request.session_id,),
        fetch_all=True
    )
    
    # Rebuild engine state
    for resp in previous_responses:
        engine.responses.append({
            'question_id': resp['question_id'],
            'level': CEFRLevel(resp['difficulty_at_question']),
            'skill': SkillType.GRAMMAR,  # Simplified for rebuild
            'is_correct': bool(resp['is_correct']),
            'time_taken': resp['time_taken_seconds'],
            'student_answer': ''
        })
        engine.questions_asked += 1
    
    # Record this answer
    is_correct = engine.record_response(question, request.student_answer, request.time_taken_seconds)
    
    # Update session statistics
    execute_query(
        """
        UPDATE student_assessment_sessions
        SET questions_answered = questions_answered + 1,
            correct_answers = correct_answers + %s,
            total_time_seconds = total_time_seconds + %s
        WHERE id = %s
        """,
        (1 if is_correct else 0, request.time_taken_seconds, request.session_id)
    )
    
    # Check if assessment is complete
    is_complete = engine.questions_asked >= engine.max_questions
    
    if is_complete:
        # Calculate final results
        final_results = engine.calculate_final_level()
        
        # Update session with final results
        execute_query(
            """
            UPDATE student_assessment_sessions
            SET completed_at = %s,
                final_detected_level = %s,
                confidence_score = %s
            WHERE id = %s
            """,
            (datetime.now(), final_results['detected_level'].value, 
             final_results['confidence_score'], request.session_id)
        )
        
        # Calculate level difference if self-reported level exists
        session_full = execute_query(
            "SELECT self_reported_level FROM student_assessment_sessions WHERE id = %s",
            (request.session_id,),
            fetch_one=True
        )
        
        if session_full and session_full['self_reported_level']:
            self_level_idx = CEFR_LEVELS_ORDER.index(session_full['self_reported_level'])
            detected_level_idx = CEFR_LEVELS_ORDER.index(final_results['detected_level'].value)
            level_diff = self_level_idx - detected_level_idx
            
            execute_query(
                "UPDATE student_assessment_sessions SET level_difference = %s WHERE id = %s",
                (level_diff, request.session_id)
            )
            
            final_results['level_difference'] = level_diff
        
        return SubmitAnswerResponse(
            is_correct=is_correct,
            correct_answer=question.correct_answer if not is_correct else None,
            next_question=None,
            current_level=engine.current_level,
            questions_remaining=0,
            is_complete=True,
            final_results=final_results
        )
    
    # Get next question
    next_question = engine.get_next_question()
    
    if not next_question:
        raise HTTPException(status_code=500, detail="Unable to generate next question")
    
    questions_remaining = engine.max_questions - engine.questions_asked
    
    return SubmitAnswerResponse(
        is_correct=is_correct,
        correct_answer=question.correct_answer if not is_correct else None,
        next_question=next_question,
        current_level=engine.current_level,
        questions_remaining=questions_remaining,
        is_complete=False
    )

@app.get("/api/assessment/results/{session_id}", response_model=AssessmentResults)
def get_assessment_results(session_id: int):
    """
    Retrieve complete results for a finished assessment session
    """
    
    # Fetch session
    session = execute_query(
        """
        SELECT id, student_id, session_type, started_at, completed_at,
               final_detected_level, confidence_score, questions_answered,
               correct_answers, total_time_seconds, self_reported_level,
               level_difference
        FROM student_assessment_sessions
        WHERE id = %s
        """,
        (session_id,),
        fetch_one=True
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Assessment session not found")
    
    if not session['completed_at']:
        raise HTTPException(status_code=400, detail="Assessment session not yet completed")
    
    # Fetch all responses for level breakdown
    responses = execute_query(
        """
        SELECT difficulty_at_question, is_correct
        FROM student_assessment_responses
        WHERE session_id = %s
        """,
        (session_id,),
        fetch_all=True
    )
    
    # Calculate level breakdown
    level_breakdown = {level: {'correct': 0, 'total': 0} for level in CEFR_LEVELS_ORDER}
    
    for resp in responses:
        level = resp['difficulty_at_question']
        level_breakdown[level]['total'] += 1
        if resp['is_correct']:
            level_breakdown[level]['correct'] += 1
    
    accuracy = (session['correct_answers'] / session['questions_answered'] * 100) if session['questions_answered'] > 0 else 0
    
    return AssessmentResults(
        session_id=session['id'],
        student_id=session['student_id'],
        detected_level=CEFRLevel(session['final_detected_level']),
        confidence_score=float(session['confidence_score']),
        questions_answered=session['questions_answered'],
        correct_answers=session['correct_answers'],
        total_time_seconds=session['total_time_seconds'],
        accuracy_percentage=round(accuracy, 2),
        level_breakdown=level_breakdown,
        self_reported_level=CEFRLevel(session['self_reported_level']) if session['self_reported_level'] else None,
        level_difference=session['level_difference'],
        started_at=session['started_at'],
        completed_at=session['completed_at']
    )

@app.get("/api/assessment/student/{student_id}/history")
def get_student_assessment_history(student_id: int, limit: int = 10):
    """
    Get assessment history for a student
    """
    
    sessions = execute_query(
        """
        SELECT id, session_type, started_at, completed_at,
               final_detected_level, confidence_score, 
               questions_answered, correct_answers
        FROM student_assessment_sessions
        WHERE student_id = %s
        ORDER BY started_at DESC
        LIMIT %s
        """,
        (student_id, limit),
        fetch_all=True
    )
    
    return {
        "student_id": student_id,
        "total_assessments": len(sessions),
        "assessments": sessions
    }

@app.post("/api/assessment/cancel/{session_id}")
def cancel_assessment(session_id: int):
    """
    Cancel an incomplete assessment session
    """
    
    session = execute_query(
        "SELECT id, completed_at FROM student_assessment_sessions WHERE id = %s",
        (session_id,),
        fetch_one=True
    )
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session['completed_at']:
        raise HTTPException(status_code=400, detail="Cannot cancel completed assessment")
    
    # Soft delete: mark as completed with null level
    execute_query(
        "UPDATE student_assessment_sessions SET completed_at = %s WHERE id = %s",
        (datetime.now(), session_id)
    )
    
    return {"message": "Assessment session cancelled successfully"}

# ==================== QUESTION MANAGEMENT ENDPOINTS ====================

@app.post("/api/questions/create")
def create_question(question: QuestionCreateRequest):
    """
    Create a new assessment question (Admin endpoint)
    """
    
    query = """
        INSERT INTO adaptive_assessment_questions
        (question_text, question_type, difficulty_level, skill_focus, 
         options, correct_answer, next_question_if_correct, next_question_if_incorrect)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    
    question_id = execute_query(query, (
        question.question_text,
        question.question_type.value,
        question.difficulty_level.value,
        question.skill_focus.value,
        json.dumps(question.options),
        question.correct_answer,
        question.next_question_if_correct,
        question.next_question_if_incorrect
    ))
    
    return {
        "message": "Question created successfully",
        "question_id": question_id
    }

@app.get("/api/questions/stats")
def get_question_statistics():
    """
    Get question bank statistics
    """
    
    stats = execute_query(
        """
        SELECT difficulty_level, skill_focus, COUNT(*) as count
        FROM adaptive_assessment_questions
        GROUP BY difficulty_level, skill_focus
        ORDER BY difficulty_level, skill_focus
        """,
        fetch_all=True
    )
    
    total = execute_query(
        "SELECT COUNT(*) as total FROM adaptive_assessment_questions",
        fetch_one=True
    )
    
    return {
        "total_questions": total['total'],
        "breakdown": stats
    }

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)