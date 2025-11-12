# Quiz Performance Optimizations for High Concurrency
import time
from functools import wraps
from flask import current_app
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

from threading import Lock
import json

class QuizPerformanceManager:
    """Manages quiz performance optimizations for high concurrency"""
    
    def __init__(self, app=None, redis_client=None):
        self.app = app
        self.redis_client = redis_client
        self.answer_locks = {}
        self.submission_lock = Lock()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app"""
        self.app = app
        
        # Try to initialize Redis for caching (optional)
        if REDIS_AVAILABLE:
            try:
                redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379')
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                app.logger.info("Redis connected for quiz caching")
            except Exception as e:
                app.logger.info(f"Redis not available ({str(e)}), using in-memory caching")
                self.redis_client = None
        else:
            app.logger.info("Redis module not installed, using in-memory caching")
            self.redis_client = None
    
    def cache_quiz_data(self, quiz_id, data, expire_time=300):
        """Cache quiz data for faster access"""
        if self.redis_client:
            try:
                key = f"quiz:{quiz_id}:data"
                self.redis_client.setex(key, expire_time, json.dumps(data))
            except:
                pass  # Fallback to no caching
    
    def get_cached_quiz_data(self, quiz_id):
        """Get cached quiz data"""
        if self.redis_client:
            try:
                key = f"quiz:{quiz_id}:data"
                cached = self.redis_client.get(key)
                if cached:
                    return json.loads(cached)
            except:
                pass
        return None
    
    def get_answer_lock(self, attempt_id, question_id):
        """Get lock for specific answer submission to prevent double submissions"""
        lock_key = f"{attempt_id}_{question_id}"
        if lock_key not in self.answer_locks:
            with self.submission_lock:
                if lock_key not in self.answer_locks:
                    self.answer_locks[lock_key] = Lock()
        return self.answer_locks[lock_key]
    
    def cleanup_old_locks(self):
        """Clean up old locks to prevent memory leaks"""
        # This should be called periodically
        if len(self.answer_locks) > 1000:
            # Keep only recent 500 locks
            keys = list(self.answer_locks.keys())
            with self.submission_lock:
                for key in keys[:-500]:
                    self.answer_locks.pop(key, None)

def prevent_double_submission(f):
    """Decorator to prevent double submission of answers"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, jsonify
        
        # Extract attempt_id from route or request
        attempt_id = kwargs.get('attempt_id') or request.get_json().get('attempt_id')
        question_data = request.get_json()
        question_id = question_data.get('question_id')
        
        if not attempt_id or not question_id:
            return f(*args, **kwargs)
        
        # Get performance manager
        perf_manager = current_app.extensions.get('quiz_performance')
        if not perf_manager:
            return f(*args, **kwargs)
        
        # Use lock for this specific answer submission
        answer_lock = perf_manager.get_answer_lock(attempt_id, question_id)
        
        if not answer_lock.acquire(blocking=False):
            return jsonify({
                'success': False, 
                'error': 'Answer submission in progress, please wait'
            }), 429
        
        try:
            return f(*args, **kwargs)
        finally:
            answer_lock.release()
    
    return decorated_function

def rate_limit_quiz_joins(max_joins_per_minute=30):
    """Rate limit quiz joins to prevent system overload"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, jsonify, current_app
            
            perf_manager = current_app.extensions.get('quiz_performance')
            if not perf_manager or not perf_manager.redis_client:
                # Skip rate limiting if Redis is not available
                return f(*args, **kwargs)
            
            # Get client IP
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            key = f"rate_limit:quiz_join:{client_ip}"
            
            try:
                current_joins = perf_manager.redis_client.get(key)
                if current_joins and int(current_joins) >= max_joins_per_minute:
                    return jsonify({
                        'success': False,
                        'error': 'Too many quiz join attempts. Please wait a moment.'
                    }), 429
                
                # Increment counter
                perf_manager.redis_client.incr(key)
                perf_manager.redis_client.expire(key, 60)  # Reset after 1 minute
                
            except Exception as e:
                # Continue without rate limiting if Redis fails
                current_app.logger.warning(f"Rate limiting failed: {str(e)}")
                pass
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

class QuizStatsCollector:
    """Collect real-time quiz statistics"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
    
    def record_participation(self, quiz_id, event_type='join'):
        """Record quiz participation events"""
        if not self.redis_client:
            return
        
        try:
            timestamp = int(time.time())
            key = f"quiz:{quiz_id}:stats:{event_type}"
            
            # Use sorted set to track events with timestamps
            self.redis_client.zadd(key, {str(timestamp): timestamp})
            
            # Keep only last hour of data
            cutoff = timestamp - 3600
            self.redis_client.zremrangebyscore(key, 0, cutoff)
            
        except:
            pass
    
    def get_live_stats(self, quiz_id):
        """Get live quiz statistics"""
        if not self.redis_client:
            return {'active_players': 0, 'total_joins': 0}
        
        try:
            current_time = int(time.time())
            
            # Get joins in last 5 minutes (active players)
            active_cutoff = current_time - 300
            join_key = f"quiz:{quiz_id}:stats:join"
            active_players = self.redis_client.zcount(join_key, active_cutoff, current_time)
            
            # Get total joins in last hour
            hour_cutoff = current_time - 3600
            total_joins = self.redis_client.zcount(join_key, hour_cutoff, current_time)
            
            return {
                'active_players': active_players,
                'total_joins': total_joins,
                'timestamp': current_time
            }
            
        except:
            return {'active_players': 0, 'total_joins': 0}

# Database query optimizations
class QuizQueryOptimizer:
    """Optimize database queries for quiz operations"""
    
    @staticmethod
    def get_quiz_with_questions(quiz_id):
        """Get quiz with all questions in single query"""
        from index import Quiz, QuizQuestion
        from sqlalchemy.orm import joinedload
        
        return Quiz.query.options(
            joinedload(Quiz.questions)
        ).filter_by(id=quiz_id).first()
    
    @staticmethod
    def get_attempt_with_answers(attempt_id):
        """Get attempt with all answers in single query"""
        from index import QuizAttempt, QuizAnswer
        from sqlalchemy.orm import joinedload
        
        return QuizAttempt.query.options(
            joinedload(QuizAttempt.answers)
        ).filter_by(id=attempt_id).first()
    
    @staticmethod
    def bulk_create_questions(quiz_id, questions_data):
        """Bulk create quiz questions for better performance"""
        from index import db, QuizQuestion
        
        questions = []
        for i, q_data in enumerate(questions_data, 1):
            question = QuizQuestion(
                quiz_id=quiz_id,
                question_text=q_data['question'],
                option_a=q_data.get('option_a', ''),
                option_b=q_data.get('option_b', ''),
                option_c=q_data.get('option_c', ''),
                option_d=q_data.get('option_d', ''),
                correct_answer=q_data['correct_answer'],
                question_order=i,
                points=q_data.get('points', 1)
            )
            questions.append(question)
        
        # Bulk insert
        db.session.bulk_save_objects(questions)
        db.session.commit()
        
        return len(questions)

# WebSocket support for real-time updates (optional)
class QuizWebSocketManager:
    """Manage WebSocket connections for real-time quiz updates"""
    
    def __init__(self):
        self.quiz_rooms = {}  # quiz_id -> set of participant_ids
    
    def join_quiz_room(self, quiz_id, participant_id):
        """Add participant to quiz room"""
        if quiz_id not in self.quiz_rooms:
            self.quiz_rooms[quiz_id] = set()
        self.quiz_rooms[quiz_id].add(participant_id)
    
    def leave_quiz_room(self, quiz_id, participant_id):
        """Remove participant from quiz room"""
        if quiz_id in self.quiz_rooms:
            self.quiz_rooms[quiz_id].discard(participant_id)
            if not self.quiz_rooms[quiz_id]:
                del self.quiz_rooms[quiz_id]
    
    def broadcast_to_quiz(self, quiz_id, message):
        """Broadcast message to all participants in quiz"""
        participants = self.quiz_rooms.get(quiz_id, set())
        return list(participants)  # Return list of participants to notify