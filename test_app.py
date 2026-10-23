"""
Comprehensive Test Suite for CareerAI Application
Tests database integrity, recommender math, resume parser, and all Flask endpoints.
"""

import os
import unittest
import json
import io

from app import app
from database.db import (
    init_db, save_profile, get_latest_profile, get_profile_by_id,
    save_recommendations, get_recommendations_for_profile,
    toggle_task_progress, get_completed_tasks, get_dashboard_metrics
)
from models.recommender import CareerRecommender
from utils.skill_extractor import extract_text_from_file, extract_skills_from_text, analyze_resume_against_career

class CareerAITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.recommender = CareerRecommender()
        cls.client = app.test_client()
        app.config['TESTING'] = True

    def test_01_database_operations(self):
        """Test profile storage, retrieval, and learning progress."""
        test_profile = {
            'full_name': 'Unit Test User',
            'education_level': 'BCA',
            'degree_branch': 'Computer Science',
            'experience_level': 'Student / Fresher',
            'preferred_domain': 'Data & Analytics',
            'career_goal': 'Data Analyst',
            'skills_text': 'Python, SQL, Excel',
            'programming_languages': 'Python, SQL',
            'soft_skills': 'Communication, Problem Solving',
            'interests': 'Business Intelligence'
        }
        profile_id = save_profile(test_profile)
        self.assertIsNotNone(profile_id)
        
        fetched = get_profile_by_id(profile_id)
        self.assertEqual(fetched['full_name'], 'Unit Test User')

        # Test task progress toggle
        toggle_task_progress(profile_id, 'data_analyst', 'Python', 'beginner', 'task_1', True)
        completed = get_completed_tasks(profile_id, 'data_analyst')
        self.assertIn('Python::beginner::task_1', completed)

    def test_02_career_recommender(self):
        """Test recommendation scoring and ranking logic."""
        profile = {
            'full_name': 'Test Engineer',
            'skills_text': 'Python, SQL, Apache Spark, ETL, Git, Docker',
            'programming_languages': 'Python, SQL',
            'preferred_domain': 'Data & Analytics',
            'career_goal': 'Data Engineer',
            'education_level': 'BCA',
            'degree_branch': 'Data Engineering'
        }
        recs = self.recommender.recommend(profile, top_n=3)
        self.assertEqual(len(recs), 3)
        # Data Engineer should be the top recommendation
        self.assertEqual(recs[0]['career_id'], 'data_engineer')
        self.assertGreaterEqual(recs[0]['suitability_score'], 50.0)
        self.assertIn('Python', recs[0]['matching_skills'])
        self.assertIn('SQL', recs[0]['matching_skills'])

    def test_03_resume_extraction(self):
        """Test text skill parsing and career gap analysis."""
        resume_text = """
        Experienced in Python, SQL, Pandas, NumPy, Git, and Docker.
        Built REST APIs with Flask and worked with MySQL databases.
        Strong problem solving and communication skills.
        """
        extracted = extract_skills_from_text(resume_text)
        self.assertIn('Python', extracted['technical_skills'])
        self.assertIn('SQL', extracted['technical_skills'])
        self.assertIn('Docker', extracted['technical_skills'])
        self.assertIn('Communication', extracted['soft_skills'])

        target_career = self.recommender.get_career_by_id('data_engineer')
        audit = analyze_resume_against_career(resume_text, target_career)
        self.assertIn('Python', audit['matching_required_skills'])
        self.assertIn('Data Warehousing', audit['missing_required_skills'])
        self.assertGreater(audit['match_percentage'], 0)

    def test_04_flask_routes(self):
        """Test all public Flask routes and JSON APIs."""
        # 1. Home
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)

        # 2. Profile Page
        res = self.client.get('/profile')
        self.assertEqual(res.status_code, 200)

        # 3. Load Demo Profile
        res = self.client.get('/load-demo', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Your Top 3 Career Matches', res.data)

        # 4. Recommendations Page
        res = self.client.get('/recommendations')
        self.assertEqual(res.status_code, 200)

        # 5. Skill Gap Page
        res = self.client.get('/skill-gap?career_id=data_engineer')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Skill Gap Diagnostic', res.data)

        # 6. Roadmap Page
        res = self.client.get('/roadmap?career_id=data_engineer')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Career Roadmap', res.data)

        # 7. Dashboard
        res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Candidate Dashboard', res.data)

        # 8. Resume Analyzer Page
        res = self.client.get('/resume-analyzer')
        self.assertEqual(res.status_code, 200)

        # 9. Sample Resume Scan
        res = self.client.get('/sample-resume-scan')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Audit Results', res.data)

        # 10. API Toggle Task
        profile = get_latest_profile()
        res = self.client.post('/api/toggle-task', 
            data=json.dumps({
                'profile_id': profile['id'],
                'career_id': 'data_engineer',
                'skill_name': 'Python',
                'level': 'beginner',
                'task_identifier': 'task_1',
                'is_completed': True
            }),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])

        # 11. Resume File Upload (TXT)
        sample_txt = io.BytesIO(b"Candidate with skills in Python, SQL, Docker, Linux.")
        res = self.client.post('/resume-analyzer', data={
            'target_career_id': 'data_engineer',
            'resume_file': (sample_txt, 'candidate_resume.txt')
        }, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Audit Results', res.data)

        # 12. Real PDF File Upload
        pdf_path = os.path.join(os.path.dirname(__file__), 'data', 'sample_resume.pdf')
        with open(pdf_path, 'rb') as f:
            pdf_bytes = io.BytesIO(f.read())
        res = self.client.post('/resume-analyzer', data={
            'target_career_id': 'data_engineer',
            'resume_file': (pdf_bytes, 'sample_resume.pdf')
        }, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'sample_resume.pdf', res.data)
        self.assertIn(b'Audit Results', res.data)

        # 13. Progress Tracker Page
        res = self.client.get('/progress-tracker')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Learning Progress & Task Tracker', res.data)

        # 14. About Project Page
        res = self.client.get('/about')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Architecture & Specifications', res.data)

        # 15. Reset Progress Action
        res = self.client.post('/reset-progress', data={'career_id': 'data_engineer'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'reset successfully', res.data)

if __name__ == '__main__':
    unittest.main()
