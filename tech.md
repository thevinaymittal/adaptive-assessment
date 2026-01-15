# Technical Onboarding - Adaptive Language Assessment System

Comprehensive technical documentation for developers integrating, maintaining, or extending the adaptive assessment system.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Schema](#database-schema)
3. [API Reference](#api-reference)
4. [Adaptive Algorithm](#adaptive-algorithm)
5. [Integration Guide](#integration-guide)
6. [Data Ranges & Validation](#data-ranges--validation)
7. [Error Handling](#error-handling)
8. [Performance Optimization](#performance-optimization)
9. [Security Considerations](#security-considerations)
10. [Deployment](#deployment)

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Any)                         │
│            React / Vue / Angular / Mobile App               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HTTP/REST
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   API Gateway Layer                         │
│              (FastAPI - Port 8000/8001)                     │
├─────────────────────────────────────────────────────────────┤
│  Assessment API (8000)        │  Validation API (8001)      │
│  • Start assessment           │  • Bulk import              │
│  • Submit answers             │  • Calibration reports      │
│  • Get results                │  • Question validation      │
│  • Session management         │  • Reclassification         │
└──────────────────────┬──────────────────────┬───────────────┘
                       │                      │
                       ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Business Logic Layer                           │
├─────────────────────────────────────────────────────────────┤
│  • AdaptiveEngine               • QuestionValidator         │
│  • LevelCalculator              • CalibrationEngine         │
│  • ResponseTracker              • ImportProcessor           │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Database Layer (MySQL)                     │
├─────────────────────────────────────────────────────────────┤
│  Assessment Tables              │  Validation Tables        │
│  • assessment_questions         │  • validation_metrics     │
│  • assessment_sessions          │  • calibration_reports    │
│  • assessment_responses         │  • import_history         │
│                                 │  • reclassification_log   │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| API Framework | FastAPI | 0.104+ | REST API, auto-docs |
| Database | MySQL | 8.0+ | Data persistence |
| ORM/Driver | mysql-connector-python | 8.2+ | DB connection pooling |
| Data Processing | Pandas | 2.0+ | CSV import/export |
| Validation | Pydantic | 2.0+ | Request/response validation |
| Algorithm | NumPy | 1.24+ | Statistical calculations |
| Server | Uvicorn | 0.24+ | ASGI server |

---

## Database Schema

### Core Assessment Tables

#### 1. `adaptive_assessment_questions`
Stores the question bank with CEFR level classification.

```sql
CREATE TABLE adaptive_assessment_questions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  question_text TEXT NOT NULL,                    -- The actual question
  question_type ENUM('multiple_choice', 'fill_blank', 'ordering', 'audio_response'),
  difficulty_level VARCHAR(5) NOT NULL,           -- A1, A2, B1, B2, C1, C2
  skill_focus VARCHAR(50),                        -- grammar, vocabulary, reading, listening
  options JSON,                                   -- ["option1", "option2", ...]
  correct_answer TEXT,
  explanation TEXT NULL,                          -- Why this answer is correct
  
  -- Adaptive tree (optional)
  next_question_if_correct INT,
  next_question_if_incorrect INT,
  
  -- Metadata
  average_time_seconds INT,
  imported_from_batch_id INT NULL,
  
  -- Timestamps
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  FOREIGN KEY (next_question_if_correct) REFERENCES adaptive_assessment_questions(id),
  FOREIGN KEY (next_question_if_incorrect) REFERENCES adaptive_assessment_questions(id),
  INDEX idx_difficulty (difficulty_level),
  INDEX idx_skill (skill_focus)
);
```

**Data Ranges:**
- `question_text`: 10-1000 characters
- `question_type`: One of 4 enum values
- `difficulty_level`: Exactly one of [A1, A2, B1, B2, C1, C2]
- `skill_focus`: One of [grammar, vocabulary, reading, listening]
- `options`: JSON array, 2-6 items
- `correct_answer`: Must match one option exactly

#### 2. `student_assessment_sessions`
Tracks each assessment session from start to completion.

```sql
CREATE TABLE student_assessment_sessions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  student_id INT UNSIGNED NOT NULL,
  session_type ENUM('initial', 'periodic_retest') DEFAULT 'initial',
  
  -- Timestamps
  started_at DATETIME NOT NULL,
  completed_at DATETIME,
  
  -- Results
  final_detected_level VARCHAR(5),               -- A1-C2
  confidence_score DECIMAL(5,2),                 -- 0.00-100.00
  questions_answered INT DEFAULT 0,
  correct_answers INT DEFAULT 0,
  total_time_seconds INT DEFAULT 0,
  
  -- Comparison
  self_reported_level VARCHAR(5),
  level_difference INT,                          -- self_reported_idx - detected_idx
  
  -- Timestamps
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_student (student_id),
  INDEX idx_completed (completed_at)
);
```

**Data Ranges:**
- `confidence_score`: 0.00-100.00 (percentage)
- `questions_answered`: 0-10 (max 10 per session)
- `correct_answers`: 0-questions_answered
- `total_time_seconds`: 0-3600 (1 hour max recommended)
- `level_difference`: -5 to +5 (if self-reported)

#### 3. `student_assessment_responses`
Individual responses to each question within a session.

```sql
CREATE TABLE student_assessment_responses (
  id INT PRIMARY KEY AUTO_INCREMENT,
  session_id INT NOT NULL,
  question_id INT NOT NULL,
  question_sequence INT,                         -- 1-10
  
  student_answer TEXT,
  is_correct BOOLEAN,
  time_taken_seconds INT,
  difficulty_at_question VARCHAR(5),             -- Level when asked
  
  answered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  FOREIGN KEY (session_id) REFERENCES student_assessment_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES adaptive_assessment_questions(id),
  INDEX idx_session (session_id),
  INDEX idx_question (question_id)
);
```

**Data Ranges:**
- `question_sequence`: 1-10
- `time_taken_seconds`: 0-300 (5 min per question max)
- `difficulty_at_question`: A1-C2

### Validation & Calibration Tables

#### 4. `question_validation_metrics`
Performance analytics for each question.

```sql
CREATE TABLE question_validation_metrics (
  id INT PRIMARY KEY AUTO_INCREMENT,
  question_id INT NOT NULL,
  
  -- Performance metrics
  total_attempts INT DEFAULT 0,
  correct_attempts INT DEFAULT 0,
  accuracy_rate DECIMAL(5,2) DEFAULT 0.00,      -- 0.00-100.00
  avg_time_seconds DECIMAL(8,2) DEFAULT 0.00,
  
  -- Student level analysis
  student_levels_attempted JSON,                -- {"A1": 5, "B1": 10}
  
  -- Classification validation
  expected_level VARCHAR(5) NOT NULL,
  recommended_level VARCHAR(5) NULL,
  confidence_score DECIMAL(5,2) DEFAULT 0.00,   -- 0.00-100.00
  needs_review BOOLEAN DEFAULT FALSE,
  
  -- Timestamps
  last_calculated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  
  FOREIGN KEY (question_id) REFERENCES adaptive_assessment_questions(id) ON DELETE CASCADE,
  UNIQUE KEY unique_question (question_id)
);
```

**Data Ranges:**
- `total_attempts`: 0-unlimited
- `accuracy_rate`: 0.00-100.00
- `avg_time_seconds`: 0.00-300.00
- `confidence_score`: 0.00-100.00

#### 5. `calibration_reports`
Historical snapshots of question bank health.

```sql
CREATE TABLE calibration_reports (
  id INT PRIMARY KEY AUTO_INCREMENT,
  
  total_questions INT NOT NULL,
  questions_needing_review INT DEFAULT 0,
  
  misclassified_questions JSON,                 -- Array of objects
  level_accuracy JSON,                          -- {"A1": 92.5, "B1": 87.3}
  recommendations JSON,                         -- Array of strings
  
  generated_at DATETIME NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  
  INDEX idx_generated_at (generated_at DESC)
);
```

#### 6. `question_import_history`
Audit trail of bulk imports.

```sql
CREATE TABLE question_import_history (
  id INT PRIMARY KEY AUTO_INCREMENT,
  
  uploaded_by VARCHAR(100) NOT NULL,
  filename VARCHAR(255) NULL,
  total_rows INT NOT NULL,
  successful_imports INT DEFAULT 0,
  failed_imports INT DEFAULT 0,
  
  import_status ENUM('processing', 'completed', 'failed') DEFAULT 'processing',
  
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME NULL,
  
  INDEX idx_uploaded_by (uploaded_by),
  INDEX idx_status (import_status)
);
```

#### 7. `question_import_errors`
Detailed error logs for failed imports.

```sql
CREATE TABLE question_import_errors (
  id INT PRIMARY KEY AUTO_INCREMENT,
  import_id INT NOT NULL,
  
  row_num INT NOT NULL,
  error_message TEXT NOT NULL,
  
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (import_id) REFERENCES question_import_history(id) ON DELETE CASCADE,
  INDEX idx_import_id (import_id)
);
```

#### 8. `question_reclassification_history`
Audit trail of level changes.

```sql
CREATE TABLE question_reclassification_history (
  id INT PRIMARY KEY AUTO_INCREMENT,
  question_id INT NOT NULL,
  
  old_level VARCHAR(5) NOT NULL,
  new_level VARCHAR(5) NOT NULL,
  reclassified_by VARCHAR(100) NOT NULL,
  reason TEXT NULL,
  
  reclassified_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  
  FOREIGN KEY (question_id) REFERENCES adaptive_assessment_questions(id) ON DELETE CASCADE,
  INDEX idx_question_id (question_id)
);
```

---

## API Reference

### Assessment API (Port 8000)

#### 1. Start Assessment
**Endpoint:** `POST /api/assessment/start`

**Request:**
```json
{
  "student_id": 123,
  "session_type": "initial",
  "self_reported_level": "B1"
}
```

**Response:**
```json
{
  "session_id": 42,
  "first_question": {
    "id": 5,
    "question_text": "Complete: 'If I ___ rich, I would travel.'",
    "question_type": "multiple_choice",
    "difficulty_level": "B1",
    "skill_focus": "grammar",
    "options": ["am", "was", "were", "be"],
    "correct_answer": "were"
  },
  "total_questions": 10,
  "message": "Assessment started successfully"
}
```

**Validation:**
- `student_id`: Must exist in `users` table
- `session_type`: "initial" or "periodic_retest"
- `self_reported_level`: Optional, A1-C2
- Cannot start if student has incomplete session

#### 2. Submit Answer
**Endpoint:** `POST /api/assessment/submit-answer`

**Request:**
```json
{
  "session_id": 42,
  "question_id": 5,
  "student_answer": "were",
  "time_taken_seconds": 15
}
```

**Response (Not Complete):**
```json
{
  "is_correct": true,
  "correct_answer": null,
  "next_question": {
    "id": 8,
    "question_text": "What does 'meticulous' mean?",
    "difficulty_level": "B2",
    "skill_focus": "vocabulary",
    "options": ["Careless", "Very careful", "Fast", "Lazy"],
    "correct_answer": "Very careful"
  },
  "current_level": "B2",
  "questions_remaining": 7,
  "is_complete": false
}
```

**Response (Complete):**
```json
{
  "is_correct": true,
  "correct_answer": null,
  "next_question": null,
  "current_level": "B2",
  "questions_remaining": 0,
  "is_complete": true,
  "final_results": {
    "detected_level": "B2",
    "confidence_score": 87.5,
    "questions_answered": 10,
    "correct_answers": 7,
    "total_time_seconds": 245,
    "accuracy_percentage": 70.0,
    "level_breakdown": {
      "A1": {"correct": 0, "total": 0},
      "A2": {"correct": 1, "total": 1},
      "B1": {"correct": 3, "total": 4},
      "B2": {"correct": 3, "total": 4},
      "C1": {"correct": 0, "total": 1}
    }
  }
}
```

**Validation:**
- `session_id`: Must exist and not be completed
- `question_id`: Must exist
- `student_answer`: Cannot be empty
- `time_taken_seconds`: 0-300

#### 3. Get Assessment Results
**Endpoint:** `GET /api/assessment/results/{session_id}`

**Response:**
```json
{
  "session_id": 42,
  "student_id": 123,
  "detected_level": "B2",
  "confidence_score": 87.5,
  "questions_answered": 10,
  "correct_answers": 7,
  "total_time_seconds": 245,
  "accuracy_percentage": 70.0,
  "level_breakdown": {
    "A1": {"correct": 0, "total": 0},
    "A2": {"correct": 1, "total": 1},
    "B1": {"correct": 3, "total": 4},
    "B2": {"correct": 3, "total": 4},
    "C1": {"correct": 0, "total": 1},
    "C2": {"correct": 0, "total": 0}
  },
  "self_reported_level": "B1",
  "level_difference": -1,
  "started_at": "2026-01-15T10:30:00",
  "completed_at": "2026-01-15T10:34:05"
}
```

**Validation:**
- Session must be completed (`completed_at` not null)

#### 4. Get Student Assessment History
**Endpoint:** `GET /api/assessment/student/{student_id}/history?limit=10`

**Response:**
```json
{
  "student_id": 123,
  "total_assessments": 3,
  "assessments": [
    {
      "id": 42,
      "session_type": "initial",
      "started_at": "2026-01-15T10:30:00",
      "completed_at": "2026-01-15T10:34:05",
      "final_detected_level": "B2",
      "confidence_score": 87.5,
      "questions_answered": 10,
      "correct_answers": 7
    }
  ]
}
```

#### 5. Cancel Assessment
**Endpoint:** `POST /api/assessment/cancel/{session_id}`

**Response:**
```json
{
  "message": "Assessment session cancelled successfully"
}
```

---

### Validation API (Port 8001)

#### 6. Bulk Import Questions
**Endpoint:** `POST /api/validation/import`

**Request:**
- Form-data file upload
- Parameter: `uploaded_by` (string)

**Response:**
```json
{
  "import_id": 5,
  "total_rows": 100,
  "successful_imports": 95,
  "failed_imports": 5,
  "errors": [
    {
      "row": 23,
      "errors": ["correct_answer 'goes' not found in options"]
    }
  ],
  "imported_question_ids": [1, 2, 3, ...]
}
```

#### 7. Validate Single Question
**Endpoint:** `GET /api/validation/question/{question_id}?save_to_db=true`

**Response:**
```json
{
  "question_id": 5,
  "total_attempts": 47,
  "correct_attempts": 28,
  "accuracy_rate": 59.57,
  "avg_time_seconds": 18.3,
  "student_levels_attempted": {
    "B1": 15,
    "B2": 20,
    "C1": 12
  },
  "expected_level": "B2",
  "recommended_level": null,
  "confidence_score": 78.5,
  "needs_review": false
}
```

#### 8. Generate Calibration Report
**Endpoint:** `GET /api/validation/calibration-report?save_to_db=true`

**Response:**
```json
{
  "report_id": 3,
  "total_questions": 250,
  "questions_needing_review": 23,
  "misclassified_questions": [
    {
      "question_id": 42,
      "current_level": "B2",
      "recommended_level": "B1",
      "accuracy_rate": 87.3,
      "confidence_score": 45.2,
      "total_attempts": 55
    }
  ],
  "level_accuracy": {
    "A1": 92.5,
    "A2": 88.3,
    "B1": 85.7,
    "B2": 67.2,
    "C1": 78.9,
    "C2": 71.4
  },
  "recommendations": [
    "Level B2 has only 67.2% well-calibrated questions - needs expert review"
  ],
  "generated_at": "2026-01-15T14:30:00"
}
```

#### 9. Get Questions Needing Review
**Endpoint:** `GET /api/validation/questions-needing-review?min_attempts=10`

**Response:**
```json
{
  "total_questions_needing_review": 12,
  "questions": [
    {
      "question_id": 42,
      "question_text": "Choose: She ___ every day.",
      "difficulty_level": "B2",
      "skill_focus": "grammar",
      "options": ["go", "goes", "going", "gone"],
      "correct_answer": "goes",
      "total_attempts": 55,
      "accuracy_rate": 87.3,
      "confidence_score": 45.2,
      "recommended_level": "A1",
      "needs_review": true
    }
  ]
}
```

#### 10. Reclassify Question
**Endpoint:** `PUT /api/validation/reclassify/{question_id}?new_level=B1&reclassified_by=admin&reason=Too+easy`

**Response:**
```json
{
  "message": "Question 42 reclassified from B2 to B1",
  "question_id": 42,
  "old_level": "B2",
  "new_level": "B1"
}
```

#### 11. Get Calibration History
**Endpoint:** `GET /api/validation/calibration-history?limit=10`

**Response:**
```json
{
  "total_reports": 5,
  "reports": [
    {
      "id": 3,
      "total_questions": 250,
      "questions_needing_review": 23,
      "level_accuracy": {...},
      "recommendations": [...],
      "generated_at": "2026-01-15T14:30:00"
    }
  ]
}
```

#### 12. Get Level Distribution
**Endpoint:** `GET /api/validation/level-distribution`

**Response:**
```json
{
  "total_questions": 250,
  "distribution": [
    {"difficulty_level": "A1", "skill_focus": "grammar", "count": 12},
    {"difficulty_level": "A1", "skill_focus": "vocabulary", "count": 10}
  ],
  "level_totals": {
    "A1": 45,
    "A2": 42,
    "B1": 50,
    "B2": 48,
    "C1": 38,
    "C2": 27
  },
  "skill_totals": {
    "grammar": 70,
    "vocabulary": 65,
    "reading": 60,
    "listening": 55
  },
  "gaps": [
    "C2 listening: only 3 questions (need 5+ per level/skill)"
  ],
  "recommendations": [...]
}
```

#### 13. Get Import History
**Endpoint:** `GET /api/validation/import-history?limit=20`

**Response:**
```json
{
  "total_imports": 5,
  "imports": [
    {
      "id": 5,
      "uploaded_by": "admin",
      "total_rows": 100,
      "successful_imports": 95,
      "failed_imports": 5,
      "import_status": "completed",
      "created_at": "2026-01-15T10:00:00",
      "completed_at": "2026-01-15T10:00:45",
      "errors": [
        {
          "row_num": 23,
          "error_message": "correct_answer not in options"
        }
      ]
    }
  ]
}
```

#### 14. Get Reclassification History
**Endpoint:** `GET /api/validation/reclassification-history/{question_id}`

**Response:**
```json
{
  "question_id": 42,
  "total_reclassifications": 2,
  "history": [
    {
      "id": 8,
      "old_level": "B2",
      "new_level": "B1",
      "reclassified_by": "admin",
      "reason": "Too easy based on calibration",
      "reclassified_at": "2026-01-15T14:30:00"
    }
  ]
}
```

---

## Adaptive Algorithm

### Core Logic

```python
class AdaptiveEngine:
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.current_level = 'B1'  # Start at intermediate
        self.responses = []
        self.skill_index = 0
        self.questions_asked = 0
        self.max_questions = 10
    
    def get_next_question(self):
        # First question: B1 grammar
        if self.questions_asked == 0:
            return fetch_question('B1', 'grammar')
        
        # Adjust difficulty based on last response
        if self.responses[-1]['is_correct']:
            self.current_level = increase_difficulty(self.current_level)
        else:
            self.current_level = decrease_difficulty(self.current_level)
        
        # Rotate skills
        skill = SKILL_TYPES[self.skill_index % 4]
        self.skill_index += 1
        
        return fetch_question(self.current_level, skill)
```

### Level Calculation Algorithm

```python
def calculate_final_level(self):
    level_scores = {
        'A1': {'correct': 0, 'total': 0},
        'A2': {'correct': 0, 'total': 0},
        'B1': {'correct': 0, 'total': 0},
        'B2': {'correct': 0, 'total': 0},
        'C1': {'correct': 0, 'total': 0},
        'C2': {'correct': 0, 'total': 0}
    }
    
    # Aggregate responses by level
    for response in self.responses:
        level = response['level']
        level_scores[level]['total'] += 1
        if response['is_correct']:
            level_scores[level]['correct'] += 1
    
    # Find highest level with:
    # - At least 2 questions at that level
    # - At least 60% accuracy
    for level in reversed(['A1', 'A2', 'B1', 'B2', 'C1', 'C2']):
        correct = level_scores[level]['correct']
        total = level_scores[level]['total']
        
        if total >= 2 and (correct / total) >= 0.6:
            confidence = (correct / total) * 100
            return {
                'detected_level': level,
                'confidence_score': confidence
            }
    
    return {'detected_level': 'A1', 'confidence_score': 50}
```

### Calibration Algorithm

```python
def analyze_question_performance(question_id):
    # Get all responses to this question
    responses = fetch_responses(question_id)
    
    # Calculate basic metrics
    total_attempts = len(responses)
    correct_attempts = sum(1 for r in responses if r['is_correct'])
    accuracy_rate = (correct_attempts / total_attempts) * 100
    
    # Analyze by student level
    level_accuracy = {}
    for response in responses:
        student_level = response['student_final_level']
        # Track accuracy by student level
        
    # Calculate confidence score
    # Students at/above question level should pass
    # Students below should struggle
    confidence = calculate_weighted_accuracy(level_accuracy)
    
    # Flag for review if:
    needs_review = (
        (accuracy_rate > 85 and total_attempts > 10) or  # Too easy
        (accuracy_rate < 40 and total_attempts > 10)     # Too hard
    )
    
    return metrics
```

---

## Integration Guide

### Frontend Integration Examples

#### React
```javascript
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

// Start assessment
const startAssessment = async (studentId) => {
  const { data } = await axios.post(`${API_BASE}/assessment/start`, {
    student_id: studentId,
    session_type: 'initial'
  });
  
  return {
    sessionId: data.session_id,
    firstQuestion: data.first_question
  };
};

// Submit answer
const submitAnswer = async (sessionId, questionId, answer, timeTaken) => {
  const { data } = await axios.post(`${API_BASE}/assessment/submit-answer`, {
    session_id: sessionId,
    question_id: questionId,
    student_answer: answer,
    time_taken_seconds: timeTaken
  });
  
  return data;
};

// Get results
const getResults = async (sessionId) => {
  const { data } = await axios.get(`${API_BASE}/assessment/results/${sessionId}`);
  return data;
};
```

#### Vue.js
```javascript
export default {
  data() {
    return {
      sessionId: null,
      currentQuestion: null,
      selectedAnswer: null
    };
  },
  methods: {
    async startAssessment() {
      const response = await fetch('http://localhost:8000/api/assessment/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          student_id: this.studentId,
          session_type: 'initial'
        })
      });
      
      const data = await response.json();
      this.sessionId = data.session_id;
      this.currentQuestion = data.first_question;
    },
    
    async submitAnswer() {
      const response = await fetch('http://localhost:8000/api/assessment/submit-answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: this.sessionId,
          question_id: this.currentQuestion.id,
          student_answer: this.selectedAnswer,
          time_taken_seconds: this.timeTaken
        })
      });
      
      const data = await response.json();
      
      if (data.is_complete) {
        this.showResults(data.final_results);
      } else {
        this.currentQuestion = data.next_question;
      }
    }
  }
};
```

---

## Data Ranges & Validation

### Input Validation Rules

| Field | Type | Min | Max | Pattern | Required |
|-------|------|-----|-----|---------|----------|
| student_id | integer | 1 | 4294967295 | - | ✓ |
| question_text | string | 10 | 1000 | - | ✓ |
| difficulty_level | enum | - | - | A1\|A2\|B1\|B2\|C1\|C2 | ✓ |
| skill_focus | enum | - | - | grammar\|vocabulary\|reading\|listening | ✓ |
| options | array | 2 | 6 | - | ✓ |
| correct_answer | string | 1 | 200 | Must match option | ✓ |
| time_taken_seconds | integer | 0 | 300 | - | ✓ |
| confidence_score | decimal | 0.00 | 100.00 | - | - |

### Response Codes

| Code | Meaning | When Used |
|------|---------|-----------|
| 200 | Success | Request processed successfully |
| 201 | Created | Resource created (import, session) |
| 400 | Bad Request | Invalid input, missing fields |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Incomplete session exists |
| 422 | Validation Error | Pydantic validation failed |
| 500 | Server Error | Database or internal error |

---

## Error Handling

### Standard Error Response Format

```json
{
  "detail": "Error message here",
  "error_code": "VALIDATION_ERROR",
  "field": "student_answer",
  "timestamp": "2026-01-15T14:30:00Z"
}
```

### Common Errors

#### 1. Incomplete Session
```json
{
  "detail": "Student has an incomplete assessment session (ID: 42). Please complete or cancel it first.",
  "error_code": "INCOMPLETE_SESSION"
}
```

#### 2. Invalid Level
```json
{
  "detail": "Invalid level. Must be one of ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']",
  "error_code": "INVALID_LEVEL"
}
```

#### 3. Session Not Found
```json
{
  "detail": "Assessment session not found",
  "error_code": "SESSION_NOT_FOUND"
}
```

#### 4. CSV Import Error
```json
{
  "detail": "Missing required columns: ['question_text', 'difficulty_level']",
  "error_code": "CSV_VALIDATION_ERROR"
}
```

### Error Handling Best Practices

```javascript
// Frontend error handling example
try {
  const response = await fetch('/api/assessment/start', {
    method: 'POST',
    body: JSON.stringify(data)
  });
  
  if (!response.ok) {
    const error = await response.json();
    
    switch (error.error_code) {
      case 'INCOMPLETE_SESSION':
        // Show cancel/continue dialog
        break;
      case 'VALIDATION_ERROR':
        // Show field-specific error
        break;
      default:
        // Show generic error
    }
  }
  
  const result = await response.json();
} catch (error) {
  console.error('Network error:', error);
}
```

---

## Performance Optimization

### Database Connection Pooling

```python
# Already implemented in the system
connection_pool = pooling.MySQLConnectionPool(
    pool_name="assessment_pool",
    pool_size=10,  # Adjust based on load
    pool_reset_session=True,
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME
)
```

### Recommended Settings

| Metric | Development | Production |
|--------|------------|-----------|
| Pool Size | 5 | 20-50 |
| Max Connections | 10 | 100-200 |
| Connection Timeout | 5s | 30s |
| Query Timeout | 10s | 30s |

### Caching Strategy

**Question Bank Caching:**
```python
# Cache questions by level/skill for 1 hour
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=128)
def get_questions_by_level_skill(level: str, skill: str):
    return execute_query(
        "SELECT * FROM adaptive_assessment_questions WHERE difficulty_level = %s AND skill_focus = %s",
        (level, skill),
        fetch_all=True
    )
```

**Validation Metrics Caching:**
- Cache metrics for 15 minutes
- Invalidate on question reclassification
- Background job: Recalculate every night

### Query Optimization

**Indexes:**
```sql
-- Already created in schema
CREATE INDEX idx_difficulty ON adaptive_assessment_questions(difficulty_level);
CREATE INDEX idx_skill ON adaptive_assessment_questions(skill_focus);
CREATE INDEX idx_session ON student_assessment_responses(session_id);
CREATE INDEX idx_question ON student_assessment_responses(question_id);
CREATE INDEX idx_needs_review ON question_validation_metrics(needs_review, total_attempts);
```

**Query Tips:**
- Always use prepared statements (prevents SQL injection)
- Limit result sets (add `LIMIT` to queries)
- Use `EXISTS` instead of `COUNT(*)` for existence checks
- Avoid `SELECT *` in production (specify columns)

---

## Security Considerations

### 1. Authentication & Authorization
```python
from fastapi import Depends, HTTPException, Header

async def verify_token(authorization: str = Header(...)):
    """Verify JWT token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    token = authorization.split(" ")[1]
    # Verify JWT token here
    return token

@app.post("/api/assessment/start")
async def start_assessment(
    request: StartAssessmentRequest,
    token: str = Depends(verify_token)
):
    # Protected endpoint
    pass
```

### 2. Rate Limiting
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/assessment/start")
@limiter.limit("5/minute")  # 5 requests per minute
async def start_assessment(request: Request):
    pass
```

### 3. Input Sanitization
```python
# Pydantic handles this automatically
class SubmitAnswerRequest(BaseModel):
    student_answer: str
    
    @validator('student_answer')
    def validate_answer(cls, v):
        if not v or not v.strip():
            raise ValueError("Answer cannot be empty")
        # Strip HTML tags
        clean = re.sub(r'<[^>]+>', '', v)
        return clean.strip()
```

### 4. SQL Injection Prevention
```python
# ALWAYS use parameterized queries
# ✓ CORRECT
execute_query(
    "SELECT * FROM questions WHERE id = %s",
    (question_id,)
)

# ✗ WRONG (vulnerable to SQL injection)
execute_query(
    f"SELECT * FROM questions WHERE id = {question_id}"
)
```

### 5. CORS Configuration
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # Production domains only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)
```

---

## Deployment

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8001

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port 8000 & uvicorn validation_system:app --host 0.0.0.0 --port 8001"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
    volumes:
      - mysql_data:/var/lib/mysql
      - ./db:/docker-entrypoint-initdb.d
    ports:
      - "3306:3306"
  
  assessment-api:
    build: .
    depends_on:
      - mysql
    environment:
      DB_HOST: mysql
      DB_USER: ${DB_USER}
      DB_PASSWORD: ${DB_PASSWORD}
      DB_NAME: ${DB_NAME}
    ports:
      - "8000:8000"
      - "8001:8001"
    restart: unless-stopped

volumes:
  mysql_data:
```

### Production Checklist

- [ ] Set up SSL/TLS certificates
- [ ] Configure firewall rules
- [ ] Enable database backups (daily)
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Configure logging (ELK stack)
- [ ] Set up error tracking (Sentry)
- [ ] Enable rate limiting
- [ ] Implement authentication
- [ ] Set up CI/CD pipeline
- [ ] Configure environment variables
- [ ] Test disaster recovery
- [ ] Document runbooks

### Monitoring Queries

**System Health:**
```sql
-- Active sessions
SELECT COUNT(*) as active_sessions
FROM student_assessment_sessions
WHERE completed_at IS NULL;

-- Average completion time
SELECT AVG(TIMESTAMPDIFF(SECOND, started_at, completed_at)) as avg_seconds
FROM student_assessment_sessions
WHERE completed_at IS NOT NULL
AND started_at > DATE_SUB(NOW(), INTERVAL 24 HOUR);

-- Questions needing review
SELECT COUNT(*) as flagged_questions
FROM question_validation_metrics
WHERE needs_review = TRUE;
```

### Backup Strategy

**Daily Backups:**
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
mysqldump -u $DB_USER -p$DB_PASSWORD $DB_NAME > backup_$DATE.sql
# Upload to S3/Cloud Storage
aws s3 cp backup_$DATE.sql s3://your-bucket/backups/
```

**Recovery:**
```bash
mysql -u root -p tulkka_live < backup_20260115_140000.sql
```

---

## Troubleshooting

### Common Issues

#### 1. "No questions available"
**Cause:** Empty question bank
**Solution:**
```bash
# Import sample questions
curl -X POST http://localhost:8001/api/validation/import \
  -F "file=@questions.csv" \
  -F "uploaded_by=admin"
```

#### 2. "Too many connections"
**Cause:** Connection pool exhausted
**Solution:**
```python
# Increase pool size in config
connection_pool = pooling.MySQLConnectionPool(
    pool_size=20  # Increase from 10
)
```

#### 3. "Calibration takes too long"
**Cause:** Large question bank
**Solution:**
- Run calibration in background task
- Cache validation metrics
- Process in batches

#### 4. "Import fails with encoding errors"
**Cause:** CSV file encoding
**Solution:**
```python
# Save CSV as UTF-8
df.to_csv('questions.csv', encoding='utf-8', index=False)
```

---

## Appendix

### A. CEFR Level Descriptors

| Level | Can-Do Statements |
|-------|------------------|
| **A1** | Can understand and use familiar everyday expressions and very basic phrases |
| **A2** | Can communicate in simple and routine tasks requiring simple exchange of information |
| **B1** | Can deal with most situations likely to arise while traveling in an area where the language is spoken |
| **B2** | Can interact with a degree of fluency and spontaneity with native speakers |
| **C1** | Can express ideas fluently and spontaneously without much obvious searching for expressions |
| **C2** | Can understand with ease virtually everything heard or read |

### B. Question Types

| Type | Description | Example |
|------|-------------|---------|
| multiple_choice | 2-6 options, one correct | "Choose: She ___ daily." |
| fill_blank | Student types answer | "Complete: I ___ happy." |
| ordering | Arrange words/sentences | "Order: [to / go / I / want]" |
| audio_response | Listen and answer | Audio clip → "What did she say?" |

### C. Skill Definitions

| Skill | Focus | Example Question Types |
|-------|-------|----------------------|
| grammar | Sentence structure, tenses | Verb forms, conditionals |
| vocabulary | Word knowledge | Synonyms, definitions |
| reading | Comprehension | Passage questions |
| listening | Audio comprehension | Audio clips |

---

## Support & Contribution

### Development Setup
```bash
# Clone repo
git clone <repo-url>
cd adaptive-assessment

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dev dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Run with hot reload
uvicorn api:app --reload --port 8000
```

### Contribution Guidelines
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new features
4. Commit changes (`git commit -m 'Add amazing feature'`)
5. Push to branch (`git push origin feature/amazing-feature`)
6. Open Pull Request

---

**Last Updated:** January 15, 2026  
**Version:** 1.0.0  
**Maintainer:** Vinay Mittal