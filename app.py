"""
CareerAI - AI Career Recommendation and Skill Gap Analyser
Main Flask Application Entry Point
"""

import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from database.db import (
    init_db, save_profile, get_latest_profile, get_profile_by_id,
    save_recommendations, get_recommendations_for_profile,
    toggle_task_progress, get_completed_tasks, get_dashboard_metrics,
    record_resume_scan, reset_all_progress
)
from models.recommender import CareerRecommender, normalize_skill
from utils.skill_extractor import extract_text_from_file, analyze_resume_against_career
from data.roadmap_data import get_roadmap_for_skill

# Load environment configuration
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'careerai-secret-key-2026-bca-project')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB Max upload limit

ALLOWED_EXTENSIONS = {'pdf', 'txt'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Database Schema
init_db()

# Initialize AI Recommender Engine
recommender = CareerRecommender()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ----------------- ROUTES ----------------- #

@app.route('/')
def index():
    """Home / Landing Page"""
    return render_template('index.html')

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """Student Profile Form - View & Submission"""
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        education_level = request.form.get('education_level', '').strip()
        degree_branch = request.form.get('degree_branch', '').strip()
        experience_level = request.form.get('experience_level', 'Student / Fresher').strip()
        preferred_domain = request.form.get('preferred_domain', 'Data & Analytics').strip()
        career_goal = request.form.get('career_goal', '').strip()
        skills_text = request.form.get('skills_text', '').strip()
        programming_languages = request.form.get('programming_languages', '').strip()
        soft_skills = request.form.get('soft_skills', '').strip()
        interests = request.form.get('interests', '').strip()

        if not full_name or not education_level or not skills_text:
            flash("Please fill in all mandatory fields (Name, Education, and Skills).", "error")
            return redirect(url_for('profile'))

        profile_data = {
            'full_name': full_name,
            'education_level': education_level,
            'degree_branch': degree_branch,
            'experience_level': experience_level,
            'preferred_domain': preferred_domain,
            'career_goal': career_goal,
            'skills_text': skills_text,
            'programming_languages': programming_languages,
            'soft_skills': soft_skills,
            'interests': interests
        }

        profile_id = save_profile(profile_data)
        profile_data['id'] = profile_id

        # Generate Recommendations via AI Model
        top_recommendations = recommender.recommend(profile_data, top_n=3)
        save_recommendations(profile_id, top_recommendations)

        flash(f"Profile saved! Your top 3 AI career matches are ready.", "success")
        return redirect(url_for('recommendations'))

    current_profile = get_latest_profile()
    return render_template('profile.html', profile=current_profile)

@app.route('/load-demo')
def load_demo_profile():
    """Seeds a realistic student profile and generates recommendations instantly."""
    role = request.args.get('role', 'analyst').lower()
    
    if role == 'engineer':
        demo_profile = {
            'full_name': 'Priya Patel',
            'education_level': 'Bachelor of Computer Applications (BCA)',
            'degree_branch': 'Data Engineering & Cloud Systems',
            'experience_level': 'Student / Fresher',
            'preferred_domain': 'Data & Analytics',
            'career_goal': 'Aspiring Data Engineer building scalable pipelines, data warehouses, and automated cloud workflows.',
            'skills_text': 'Python, SQL, Apache Spark, ETL, Data Warehousing, Git, Linux, Docker, Cloud Platforms',
            'programming_languages': 'Python, SQL, Scala',
            'soft_skills': 'System Architecture, Problem Solving, Teamwork',
            'interests': 'Data Pipelines, Big Data, Distributed Computing, Lakehouses'
        }
    elif role == 'developer':
        demo_profile = {
            'full_name': 'Rahul Verma',
            'education_level': 'Bachelor of Computer Applications (BCA)',
            'degree_branch': 'Web Technologies & Software Systems',
            'experience_level': 'Student / Fresher',
            'preferred_domain': 'Software Development',
            'career_goal': 'Full-Stack Web Developer creating modern React applications and REST APIs.',
            'skills_text': 'HTML, CSS, JavaScript, React, Node.js, Express, SQL, Git, REST APIs, MongoDB',
            'programming_languages': 'JavaScript, Python, SQL',
            'soft_skills': 'Clean Coding, Communication, Agile/Scrum',
            'interests': 'Frontend Architecture, API Design, UI/UX, Cloud Deployment'
        }
    else:  # Default: Data Analytics candidate with Python, SQL, Excel, Power BI
        demo_profile = {
            'full_name': 'Aarav Sharma',
            'education_level': 'Bachelor of Computer Applications (BCA)',
            'degree_branch': 'Computer Applications / Analytics',
            'experience_level': 'Student / Fresher',
            'preferred_domain': 'Data & Analytics',
            'career_goal': 'Data Analyst transforming business data into predictive insights and executive dashboards.',
            'skills_text': 'Python, SQL, Excel, Power BI, Tableau, Pandas, NumPy, Statistics, Data Cleaning, Data Visualization',
            'programming_languages': 'Python, SQL, R',
            'soft_skills': 'Analytical Thinking, Storytelling, Communication, Problem Solving',
            'interests': 'Business Intelligence, Statistical Analysis, Data Visualization, Market Trends'
        }

    profile_id = save_profile(demo_profile)
    demo_profile['id'] = profile_id

    top_recommendations = recommender.recommend(demo_profile, top_n=3)
    save_recommendations(profile_id, top_recommendations)

    flash(f"Demo profile for '{demo_profile['full_name']} (BCA)' loaded successfully! AI Career Matches generated.", "success")
    return redirect(url_for('recommendations'))

@app.route('/recommendations')
def recommendations():
    """Displays Top 3 AI Career Recommendations with score breakdowns."""
    prof = get_latest_profile()
    if not prof:
        flash("Please complete your student profile first.", "info")
        return redirect(url_for('profile'))

    recs = get_recommendations_for_profile(prof['id'])
    if not recs:
        # Re-compute if empty
        recs = recommender.recommend(prof, top_n=3)
        save_recommendations(prof['id'], recs)

    # Re-hydrate score breakdown calculations if retrieved from DB
    enriched_recs = []
    for r in recs:
        full_rec = recommender.recommend(prof, top_n=10)
        matched_full = next((x for x in full_rec if x['career_id'] == r['career_id']), None)
        if matched_full:
            enriched_recs.append(matched_full)
        else:
            enriched_recs.append(r)

    return render_template('recommendations.html', profile=prof, recommendations=enriched_recs)

@app.route('/skill-gap')
def skill_gap():
    """Skill Gap Diagnostic Page comparing existing skills against role requirements."""
    prof = get_latest_profile()
    if not prof:
        flash("Please complete your profile first to diagnose skill gaps.", "info")
        return redirect(url_for('profile'))

    all_careers = recommender.get_all_careers()
    career_id = request.args.get('career_id')

    if not career_id:
        recs = get_recommendations_for_profile(prof['id'])
        if recs:
            career_id = recs[0]['career_id']
        else:
            career_id = all_careers[0]['career_id']

    target_career = recommender.get_career_by_id(career_id)
    if not target_career:
        flash("Career role not found.", "error")
        return redirect(url_for('recommendations'))

    # User skills normalized
    user_raw_skills = [s.strip() for s in (prof['skills_text'] or '').split(',') if s.strip()]
    if prof.get('programming_languages'):
        user_raw_skills.extend([s.strip() for s in prof['programming_languages'].split(',') if s.strip()])
    user_skills_norm = set(normalize_skill(s) for s in user_raw_skills)

    raw_req = target_career['required_skills']
    raw_sec = target_career['secondary_skills']

    req_map = {normalize_skill(s): s for s in raw_req}
    req_set = set(req_map.keys())

    matching_skills = [req_map[s] for s in user_skills_norm.intersection(req_set)]
    missing_skills = [req_map[s] for s in req_set - user_skills_norm]

    # Assign priority levels
    missing_priorities = []
    high_priority_count = 0
    for idx, s in enumerate(missing_skills):
        if s in raw_req[:3]:
            priority = "High"
            high_priority_count += 1
        elif s in raw_req:
            priority = "Medium"
        else:
            priority = "Low"
        missing_priorities.append({
            "skill": s,
            "priority": priority
        })

    match_pct = round((len(matching_skills) / len(raw_req) * 100), 1) if raw_req else 0

    # Data for Radar Chart: Role Required (100) vs User Competency (0 or 90)
    radar_labels = raw_req[:6]  # top 6 key requirements for radar visualization
    user_scores = []
    required_scores = []
    for skill_name in radar_labels:
        required_scores.append(100)
        if normalize_skill(skill_name) in user_skills_norm:
            user_scores.append(90)
        else:
            user_scores.append(20)

    return render_template(
        'skill_gap.html',
        profile=prof,
        career=target_career,
        all_careers=all_careers,
        matching_skills=matching_skills,
        missing_skills=missing_skills,
        missing_priorities=missing_priorities,
        high_priority_count=high_priority_count,
        match_pct=match_pct,
        radar_labels=radar_labels,
        user_scores=user_scores,
        required_scores=required_scores
    )

@app.route('/roadmap')
def roadmap():
    """Personalized Learning Roadmap with persistent weekly task tracking."""
    prof = get_latest_profile()
    if not prof:
        flash("Please complete your profile first to view your roadmap.", "info")
        return redirect(url_for('profile'))

    career_id = request.args.get('career_id')
    if not career_id:
        recs = get_recommendations_for_profile(prof['id'])
        if recs:
            career_id = recs[0]['career_id']
        else:
            career_id = 'data_engineer'

    career = recommender.get_career_by_id(career_id)
    if not career:
        flash("Career role not found.", "error")
        return redirect(url_for('recommendations'))

    # Determine skills to display roadmap for
    user_raw_skills = [s.strip() for s in (prof['skills_text'] or '').split(',') if s.strip()]
    if prof.get('programming_languages'):
        user_raw_skills.extend([s.strip() for s in prof['programming_languages'].split(',') if s.strip()])
    user_skills_norm = set(normalize_skill(s) for s in user_raw_skills)

    skills_to_show = []
    specific_skill = request.args.get('skill')
    if specific_skill:
        skills_to_show = [specific_skill]
    else:
        # Include missing required skills first, then matching required skills
        raw_req = career['required_skills']
        missing_first = [s for s in raw_req if normalize_skill(s) not in user_skills_norm]
        acquired_next = [s for s in raw_req if normalize_skill(s) in user_skills_norm]
        skills_to_show = missing_first + acquired_next

    roadmaps = []
    total_tasks = 0
    for s in skills_to_show:
        data = get_roadmap_for_skill(s)
        is_missing = normalize_skill(s) not in user_skills_norm
        roadmaps.append({
            "skill_name": s,
            "is_missing": is_missing,
            "data": data
        })
        # 3 levels * 3 practice tasks = 9 tasks per skill
        total_tasks += sum(len(lvl['practice_tasks']) for lvl in data['levels'].values())

    completed_keys = get_completed_tasks(prof['id'], career['career_id'])
    progress_pct = round((len(completed_keys) / total_tasks * 100), 1) if total_tasks > 0 else 0

    return render_template(
        'roadmap.html',
        profile=prof,
        career=career,
        roadmaps=roadmaps,
        completed_keys=completed_keys,
        total_tasks=total_tasks,
        progress_pct=progress_pct
    )

@app.route('/dashboard')
def dashboard():
    """Candidate Progress & Analytics Dashboard."""
    prof = get_latest_profile()
    if not prof:
        flash("Please complete your profile to view your personal dashboard.", "info")
        return redirect(url_for('profile'))

    metrics = get_dashboard_metrics(prof['id'])
    if not metrics:
        return redirect(url_for('profile'))

    return render_template(
        'dashboard.html',
        profile=metrics['profile'],
        total_skills_count=metrics['total_skills_count'],
        top_career=metrics['top_career'],
        recs=metrics['recommendations'],
        completed_tasks_count=metrics['completed_tasks_count']
    )

@app.route('/resume-analyzer', methods=['GET', 'POST'])
def resume_analyzer():
    """Resume Skill Analyser - Supports PDF & TXT File Uploads."""
    all_careers = recommender.get_all_careers()
    target_career_id = request.args.get('target_career_id', 'data_engineer')

    if request.method == 'POST':
        target_career_id = request.form.get('target_career_id')
        if not target_career_id:
            flash("Please choose a target career to audit your resume against.", "error")
            return redirect(url_for('resume_analyzer'))

        if 'resume_file' not in request.files:
            flash("No file was uploaded.", "error")
            return redirect(url_for('resume_analyzer'))

        file = request.files['resume_file']
        if file.filename == '':
            flash("No file selected.", "error")
            return redirect(url_for('resume_analyzer'))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            try:
                # Extract text
                extracted_text = extract_text_from_file(file_path)
                
                # Fetch target career
                target_career = recommender.get_career_by_id(target_career_id)
                scan_result = analyze_resume_against_career(extracted_text, target_career)

                # Record in database
                record_resume_scan(
                    filename=filename,
                    target_career=target_career['career_title'],
                    found_skills=scan_result['skills_detected'],
                    missing_skills=scan_result['missing_required_skills'],
                    match_score=scan_result['match_percentage']
                )

                # Remove uploaded file immediately to prevent unnecessary storage
                if os.path.exists(file_path):
                    os.remove(file_path)

                flash(f"Resume '{filename}' scanned successfully! Audit results displayed below.", "success")
                return render_template(
                    'resume.html',
                    all_careers=all_careers,
                    target_career_id=target_career_id,
                    target_career=target_career,
                    filename=filename,
                    scan_result=scan_result
                )

            except Exception as e:
                if os.path.exists(file_path):
                    os.remove(file_path)
                flash(f"Failed to parse resume: {str(e)}", "error")
                return redirect(url_for('resume_analyzer'))
        else:
            flash("Unsupported file format. Please upload a .pdf or .txt resume file.", "error")
            return redirect(url_for('resume_analyzer'))

    return render_template(
        'resume.html',
        all_careers=all_careers,
        target_career_id=target_career_id,
        target_career=None,
        scan_result=None
    )

@app.route('/sample-resume-scan')
def load_sample_resume_scan():
    """Runs a live instant resume analysis on sample student resume text."""
    sample_resume_text = """
    Aarav Sharma - Aspiring Data Professional
    Education: Bachelor of Computer Applications (BCA) - 2026
    
    Technical Skills:
    - Programming Languages: Python, SQL, JavaScript
    - Libraries & Frameworks: Pandas, NumPy, Scikit-learn, Flask
    - Databases & Storage: PostgreSQL, MySQL, SQLite
    - Tools & DevOps: Git, GitHub, Docker, Linux, Excel
    
    Academic Projects:
    1. Automated Data Pipeline & Cleansing Tool
       Built a Python script to ingest, clean, and validate 50,000+ rows of e-commerce data using Pandas.
    2. Student Performance Analytics Dashboard
       Developed an interactive dashboard with SQL and Chart.js visualizing semester grades.
       
    Soft Skills: Communication, Problem Solving, Analytical Thinking, Team Collaboration.
    """
    all_careers = recommender.get_all_careers()
    target_career = recommender.get_career_by_id('data_engineer')
    scan_result = analyze_resume_against_career(sample_resume_text, target_career)

    flash("Sample resume scanned! Auditing against 'Data Engineer' requirements.", "success")
    return render_template(
        'resume.html',
        all_careers=all_careers,
        target_career_id='data_engineer',
        target_career=target_career,
        filename='sample_aarav_sharma_resume.pdf',
        scan_result=scan_result
    )

@app.route('/progress-tracker')
def progress_tracker():
    """Dedicated Progress Tracker Page with task filtering and completion metrics."""
    prof = get_latest_profile()
    if not prof:
        flash("Please complete your profile to track your roadmap progress.", "info")
        return redirect(url_for('profile'))

    career_id = request.args.get('career_id')
    recs = get_recommendations_for_profile(prof['id'])
    
    if not career_id:
        career_id = recs[0]['career_id'] if recs else 'data_engineer'

    target_career = recommender.get_career_by_id(career_id)
    if not target_career:
        target_career = recommender.get_career_by_id('data_engineer')

    # Gather required skills
    raw_req = target_career['required_skills'] if target_career else ['Python', 'SQL', 'Git']
    completed_keys = get_completed_tasks(prof['id'], target_career['career_id'])

    skills_data = []
    total_tasks = 0
    completed_count = 0

    for skill_name in raw_req:
        data = get_roadmap_for_skill(skill_name)
        task_list = []
        skill_total = 0
        skill_done = 0

        for lvl_name, lvl_info in data['levels'].items():
            for idx, task_text in enumerate(lvl_info.get('practice_tasks', []), 1):
                task_id = f"task_{idx}"
                task_key = f"{skill_name}::{lvl_name}::{task_id}"
                is_done = task_key in completed_keys
                skill_total += 1
                total_tasks += 1
                if is_done:
                    skill_done += 1
                    completed_count += 1
                task_list.append({
                    "level": lvl_name,
                    "task_id": task_id,
                    "text": task_text,
                    "is_completed": is_done
                })

        skill_pct = round((skill_done / skill_total * 100), 1) if skill_total > 0 else 0
        skills_data.append({
            "skill_name": skill_name,
            "tasks": task_list,
            "total_in_skill": skill_total,
            "completed_in_skill": skill_done,
            "skill_pct": skill_pct
        })

    progress_pct = round((completed_count / total_tasks * 100), 1) if total_tasks > 0 else 0

    return render_template(
        'progress.html',
        profile=prof,
        target_career=target_career,
        skills_data=skills_data,
        completed_keys=completed_keys,
        total_tasks=total_tasks,
        completed_count=completed_count,
        progress_pct=progress_pct
    )

@app.route('/reset-progress', methods=['POST'])
def reset_progress():
    """Resets task checklist history in database."""
    prof = get_latest_profile()
    if not prof:
        return redirect(url_for('profile'))
    
    career_id = request.form.get('career_id')
    reset_all_progress(prof['id'], career_id if career_id else None)
    flash("Progress history reset successfully. You can begin checking milestones afresh!", "info")
    return redirect(url_for('progress_tracker', career_id=career_id if career_id else ''))

@app.route('/about')
def about():
    """About Project & Academic Specifications Page."""
    return render_template('about.html')

# ----------------- REST API ----------------- #

@app.route('/api/toggle-task', methods=['POST'])
def api_toggle_task():
    """API endpoint to update roadmap task completion status via AJAX."""
    try:
        data = request.get_json() or {}
        profile_id = int(data.get('profile_id'))
        career_id = data.get('career_id')
        skill_name = data.get('skill_name')
        level = data.get('level')
        task_id = data.get('task_identifier')
        is_completed = bool(data.get('is_completed'))

        toggle_task_progress(profile_id, career_id, skill_name, level, task_id, is_completed)
        return jsonify({"success": True, "is_completed": is_completed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

# ----------------- ERROR HANDLERS ----------------- #

@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('base.html'), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
