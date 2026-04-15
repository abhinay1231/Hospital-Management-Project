from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.utils import secure_filename
from database import *
# Explicitly import DoctorChat to ensure it's available
from database import DoctorChat
from config import Config
import os
from rag_system import rag_system
from intent_classifier import intent_classifier  
from datetime import datetime, timedelta, date
import requests
import json
from functools import wraps
from collections import Counter
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch


# Helper Functions for RAG Updates
def update_rag_on_new_prescription(prescription):
    """Call this after adding a prescription"""
    try:
        rag_system.add_prescription(prescription)
    except Exception as e:
        print(f"Error updating RAG for prescription: {e}")

def update_rag_on_new_health_metric(metric):
    """Call this after adding health metrics"""
    try:
        rag_system.add_health_metrics(metric)
    except Exception as e:
        print(f"Error updating RAG for metrics: {e}")

def update_rag_on_patient_update(patient):
    """Call this after updating patient profile"""
    try:
        rag_system.add_patient_data(patient, db.session)
    except Exception as e:
        print(f"Error updating RAG for patient: {e}")

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

@app.context_processor
def utility_processor():
    return {
        'now': datetime.now
    }

# Ensure upload folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'reports'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'prescriptions'), exist_ok=True)



# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def patient_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'patient':
            flash('Access denied', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def doctor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'doctor':
            flash('Access denied', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def send_email(to_email, subject, body):
    if not app.config['SMTP_USERNAME'] or not app.config['SMTP_PASSWORD']:
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = app.config['SMTP_USERNAME']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT'])
        server.starttls()
        server.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False



def generate_ai_response(prompt, role="patient", patient_context="", chat_history=None, similar_cases=""):
    try:
        history_text = ""

        if chat_history:
            for chat in chat_history:
                history_text += f"User: {chat.message}\n"
                history_text += f"Assistant: {chat.response}\n"

        if role == "patient":
            full_prompt = f"""
        You are a friendly medical assistant speaking directly to the patient.
        Be conversational and supportive.
        Do NOT sound like a clinical report.

        Patient Information:
        {patient_context}

        Similar Past Cases:
        {similar_cases}

        Conversation so far:
        {history_text}

        User: {prompt}

        Assistant:
        """
            
        elif role == "doctor":
            full_prompt = f"""
        You are a clinical AI assistant supporting a doctor.
        Do NOT speak to the patient.
        Do NOT use the patient's name.
        Respond professionally.
        Be concise and structured.

        {prompt}
        """
        else:
             full_prompt = prompt

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "temperature": 0.2,
                "prompt": full_prompt,
                "stream": False
            },
            timeout=60
        )

        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            return "AI service is currently unavailable."

    except Exception as e:
        return f"AI Error: {str(e)}"

def get_similar_patients(patient, limit=3):
    try:
        if not patient.age:
            start_age = 0
            end_age = 100
        else:
            start_age = patient.age - 10
            end_age = patient.age + 10

        similar = Patient.query.filter(
            Patient.disease_category == patient.disease_category,
            Patient.age.between(start_age, end_age),
            Patient.id != patient.id
        ).limit(limit).all()

        similar_cases_text = ""

        for sp in similar:
            latest_prescription = Prescription.query.filter_by(
                patient_id=sp.id
            ).order_by(Prescription.date_issued.desc()).first()

            diagnosis = latest_prescription.diagnosis if latest_prescription else "Unknown"

            similar_cases_text += f"""
Case:
Age: {sp.age if sp.age else 'Unknown'}
Gender: {sp.gender}
Symptoms: {sp.symptoms}
Diagnosis Outcome: {diagnosis}
"""

        if not similar_cases_text:
            similar_cases_text = "No similar cases found."

        return similar_cases_text
    except Exception as e:
        return "No similar cases found (Error)."

def calculate_bmi(weight, height):
    try:
        if weight and height and float(height) > 0:
            bmi = float(weight) / ((float(height) / 100) ** 2)
            return round(bmi, 2)
    except:
        pass
    return None

def get_bmi_category(bmi):
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"


def handle_patient_query_by_intent(patient, query, intent, chat_history):
    """Handle patient-specific queries based on detected intent"""
    
    query_lower = query.lower().strip()
    patient_name = patient.name
    
    # Get patient data
    latest_metrics = HealthMetric.query.filter_by(patient_id=patient.id).order_by(HealthMetric.recorded_date.desc()).first()
    all_prescriptions = Prescription.query.filter_by(patient_id=patient.id).order_by(Prescription.date_issued.desc()).all()
    
    # Route based on intent
    if intent == 'SYMPTOM_QUERY':
        if patient.symptoms:
            return f"**{patient_name}'s symptoms:** {patient.symptoms}"
        else:
            return f"No symptoms recorded for {patient_name}."
    
    elif intent == 'VITALS_QUERY':
        if latest_metrics:
            return f"""**{patient_name}'s Latest Vitals:**
• Blood Pressure: {latest_metrics.blood_pressure_systolic}/{latest_metrics.blood_pressure_diastolic}
• Heart Rate: {latest_metrics.heart_rate} bpm
• BMI: {latest_metrics.bmi}
• Blood Sugar: {latest_metrics.blood_sugar} mg/dL
• Recorded: {latest_metrics.recorded_date.strftime('%Y-%m-%d')}"""
        else:
            return f"No health metrics recorded for {patient_name}."
    
    elif intent == 'HISTORY_QUERY':
        history_parts = []
        if patient.medical_history:
            history_parts.append(f"**Medical History:** {patient.medical_history}")
        if patient.family_history:
            history_parts.append(f"**Family History:** {patient.family_history}")
        
        if history_parts:
            return f"**{patient_name}'s History:**\n\n" + "\n\n".join(history_parts)
        else:
            return f"No medical history recorded for {patient_name}."
    
    elif intent == 'COMPARISON_QUERY':
        return compare_with_previous(patient)
    
    elif intent == 'TREATMENT_QUERY':
        if all_prescriptions:
            response = f"**💊 Treatment History for {patient_name}**\n\n"
            for i, rx in enumerate(all_prescriptions[:3], 1):
                response += f"{i}. **{rx.date_issued.strftime('%B %d, %Y')}**\n"
                response += f"   • Diagnosis: {rx.diagnosis or 'Not specified'}\n"
                response += f"   • Medications: {rx.medicines}\n"
                if rx.notes:
                    response += f"   • Notes: {rx.notes}\n"
                response += "\n"
            return response
        else:
            return f"No treatment records found for {patient_name}."
    
    elif intent == 'SIMILAR_CASES_QUERY':
        return find_similar_patients(patient, query)
    
    elif intent == 'APPOINTMENT_QUERY':
        return get_appointment_info(patient)
    
    else:  # GENERAL_QUERY or fallback
        # Use RAG for general questions
        return handle_patient_query_with_context(patient, query, 'general', chat_history)


def compare_with_previous(patient):
    """Compare current with previous visit"""
    appointments = Appointment.query.filter_by(
        patient_id=patient.id
    ).order_by(Appointment.appointment_date.desc()).limit(2).all()
    
    if len(appointments) < 2:
        return "Not enough visit history to compare."
    
    latest = appointments[0]
    previous = appointments[1]
    
    return f"""**🔄 Comparison: Current vs Previous Visit**

**Current Visit ({latest.appointment_date.strftime('%B %d, %Y')}):**
• Reason: {latest.reason or 'Not specified'}
• Status: {latest.status}

**Previous Visit ({previous.appointment_date.strftime('%B %d, %Y')}):**
• Reason: {previous.reason or 'Not specified'}
• Status: {previous.status}

**Time between visits:** {(latest.appointment_date - previous.appointment_date).days} days"""


def get_appointment_info(patient):
    """Get appointment information for patient"""
    today_date = date.today()
    
    # Upcoming appointments
    upcoming = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.appointment_date >= today_date
    ).order_by(Appointment.appointment_date).all()
    
    # Past appointments
    past = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.appointment_date < today_date
    ).order_by(Appointment.appointment_date.desc()).all()
    
    response = f"**📅 Appointment Information for {patient.name}**\n\n"
    
    if upcoming:
        response += "**Upcoming Appointments:**\n"
        for apt in upcoming[:2]:
            days = (apt.appointment_date - today_date).days
            when = "TODAY" if days == 0 else f"in {days} days"
            response += f"• {apt.appointment_date.strftime('%B %d, %Y')} at {apt.time_slot} ({when})\n"
        response += "\n"
    
    if past:
        response += f"**Previous Visits:** {len(past)} total\n"
        response += f"**Last Visit:** {past[0].appointment_date.strftime('%B %d, %Y')}\n"
    else:
        response += "**No previous visits recorded.** 📅\n"
        response += "\n💡 **Tip:** You can schedule an appointment for this patient from the calendar."
    
    return response


def find_similar_cases_global(query):
    """Find similar cases from all patients based on query"""
    try:
        # Use RAG to search across all patients
        results = rag_system.search_similar(
            query=query,
            limit=5,
            similarity_threshold=0.4
        )
        
        if not results:
            return "No similar cases found matching your query."
        
        response = f"## 🔍 Similar Cases Found\n\n"
        response += f"Based on: '{query}'\n\n"
        
        for i, r in enumerate(results, 1):
            response += f"**{i}. {r['text'][:150]}...**\n"
            response += f"   Relevance: {r['similarity_score']:.2%}\n\n"
        
        return response
    except Exception as e:
        return f"Error searching for similar cases: {str(e)}"

# Routes - Authentication
@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'patient':
            return redirect(url_for('patient_dashboard'))
        elif session.get('role') == 'doctor':
            return redirect(url_for('doctor_dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        name = request.form.get('name')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user = User(email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        
        if role == 'patient':
            patient = Patient(user_id=user.id, name=name)
            db.session.add(patient)
        elif role == 'doctor':
            doctor = Doctor(user_id=user.id, name=name)
            db.session.add(doctor)
        
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['email'] = user.email
            
            if user.role == 'patient':
                patient = Patient.query.filter_by(user_id=user.id).first()
                session['patient_id'] = patient.id
                session['name'] = patient.name
                return redirect(url_for('patient_dashboard'))
            elif user.role == 'doctor':
                doctor = Doctor.query.filter_by(user_id=user.id).first()
                session['doctor_id'] = doctor.id
                session['name'] = doctor.name
                return redirect(url_for('doctor_dashboard'))
        
        flash('Invalid credentials', 'error')
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

# Patient Routes
@app.route('/patient/dashboard')
@patient_required
def patient_dashboard():
    patient = Patient.query.get(session['patient_id'])
    upcoming_appointments = Appointment.query.filter_by(
        patient_id=patient.id,
        status='confirmed'
    ).filter(Appointment.appointment_date >= date.today()).order_by(Appointment.appointment_date).limit(5).all()
    
    recent_prescriptions = Prescription.query.filter_by(patient_id=patient.id).order_by(Prescription.date_issued.desc()).limit(3).all()
    
    latest_metrics = HealthMetric.query.filter_by(patient_id=patient.id).order_by(HealthMetric.recorded_date.desc()).first()
    
    return render_template('patient/dashboard.html', 
                         patient=patient, 
                         appointments=upcoming_appointments,
                         prescriptions=recent_prescriptions,
                         metrics=latest_metrics)

@app.route('/patient/profile', methods=['GET', 'POST'])
@patient_required
def patient_profile():
    patient = Patient.query.get(session['patient_id'])
    
    if request.method == 'POST':
        step = request.form.get('step')
        
        if step == '1':
            patient.age = request.form.get('age')
            patient.gender = request.form.get('gender')
            patient.contact = request.form.get('contact')
            patient.address = request.form.get('address')
        elif step == '2':
            patient.family_history = request.form.get('family_history')
        elif step == '3':
            patient.symptoms = request.form.get('symptoms')
        elif step == '4':
            patient.diet = request.form.get('diet')
            patient.lifestyle = request.form.get('lifestyle')
        elif step == '5':
            patient.medical_history = request.form.get('medical_history')
            patient.profile_completed = True
        
        db.session.commit()
        
        # Update RAG with new patient data
        update_rag_on_patient_update(patient)
        
        if step == '5':
            flash('Profile completed successfully!', 'success')
            return redirect(url_for('patient_dashboard'))
        
        return redirect(url_for('patient_profile', step=int(step)+1))
    
    step = request.args.get('step', 1, type=int)
    return render_template('patient/profile.html', patient=patient, step=step)

@app.route('/patient/chat', methods=['GET', 'POST'])
@patient_required
def patient_chat():
    patient = Patient.query.get(session['patient_id'])
    
    if request.method == 'POST':
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'response': 'Please say something!'})
        
        # Step 1: Use RAG to get relevant patient context
        patient_context = rag_system.get_patient_context(
            patient_id=patient.id,
            query=message
        )
        
        # Step 2: Get similar cases using semantic search
        similar_cases_query = f"{patient.symptoms} {patient.disease_category or ''}"
        similar_cases_results = rag_system.search_similar(
            query=similar_cases_query,
            limit=3
        )
        
        similar_cases_text = "\n".join([
            f"• {r['text'][:150]}..." 
            for r in similar_cases_results
        ]) if similar_cases_results else "No similar cases found."
        
        # Step 3: Get recent chat history
        chat_history = ChatHistory.query.filter_by(
            patient_id=patient.id
        ).order_by(ChatHistory.timestamp.desc()).limit(5).all()
        chat_history.reverse()
        
        # Step 4: Build enhanced prompt with RAG context
        full_prompt = f"""You are a helpful medical assistant. Use the patient's actual history below to provide personalized responses.

{patient_context}

SIMILAR CASES FROM OTHER PATIENTS:
{similar_cases_text}

RECENT CONVERSATION:
{chr(10).join([f"User: {c.message}\nAssistant: {c.response}" for c in chat_history[-3:]])}

Current patient question: {message}

Provide a helpful, personalized response based on their actual history:"""
        
        # Step 5: Get AI response
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3",
                    "prompt": full_prompt,
                    "temperature": 0.3,
                    "stream": False,
                    "options": {
                        "num_predict": 500
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                ai_response = response.json().get("response", "").strip()
            else:
                ai_response = "I'm having trouble connecting. Please try again."
                
        except Exception as e:
            ai_response = f"Error: {str(e)}"
        
        # Step 6: Save to database
        chat = ChatHistory(
            patient_id=patient.id,
            message=message,
            response=ai_response
        )
        db.session.add(chat)
        db.session.commit()
        
        return jsonify({'response': ai_response})
    
    # GET request - load chat history
    chat_history = ChatHistory.query.filter_by(
        patient_id=patient.id
    ).order_by(ChatHistory.timestamp.desc()).limit(50).all()
    chat_history.reverse()
    
    return render_template('patient/chat.html', chat_history=chat_history)

@app.route('/patient/appointments', methods=['GET', 'POST'])
@patient_required
def patient_appointments():
    if request.method == 'POST':
        doctor_id = request.form.get('doctor_id')
        appointment_date = datetime.strptime(request.form.get('appointment_date'), '%Y-%m-%d').date()
        time_slot = request.form.get('time_slot')
        reason = request.form.get('reason')
        
        appointment = Appointment(
            patient_id=session['patient_id'],
            doctor_id=doctor_id,
            appointment_date=appointment_date,
            time_slot=time_slot,
            reason=reason,
            status='pending'
        )
        db.session.add(appointment)
        db.session.commit()
        
        flash('Appointment booked successfully!', 'success')
        return redirect(url_for('patient_appointments'))
    
    appointments = Appointment.query.filter_by(patient_id=session['patient_id']).order_by(Appointment.appointment_date.desc()).all()
    doctors = Doctor.query.all()
    
    return render_template('patient/appointments.html', appointments=appointments, doctors=doctors)

@app.route('/patient/appointments/<int:appointment_id>/cancel', methods=['POST'])
@patient_required
def cancel_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    
    if appointment.patient_id != session['patient_id']:
        flash('Unauthorized', 'error')
        return redirect(url_for('patient_appointments'))
    
    appointment.status = 'cancelled'
    db.session.commit()
    
    flash('Appointment cancelled', 'success')
    return redirect(url_for('patient_appointments'))

@app.route('/patient/prescriptions')
@patient_required
def patient_prescriptions():
    prescriptions = Prescription.query.filter_by(patient_id=session['patient_id']).order_by(Prescription.date_issued.desc()).all()
    return render_template('patient/prescriptions.html', prescriptions=prescriptions)

@app.route('/patient/health-metrics', methods=['GET', 'POST'])
@patient_required
def patient_health_metrics():
    if request.method == 'POST':
        weight = float(request.form.get('weight')) if request.form.get('weight') else None
        height = float(request.form.get('height')) if request.form.get('height') else None
        bmi = calculate_bmi(weight, height)
        
        metric = HealthMetric(
            patient_id=session['patient_id'],
            blood_pressure_systolic=request.form.get('bp_systolic'),
            blood_pressure_diastolic=request.form.get('bp_diastolic'),
            heart_rate=request.form.get('heart_rate'),
            blood_sugar=request.form.get('blood_sugar'),
            weight=weight,
            height=height,
            bmi=bmi,
            temperature=request.form.get('temperature'),
            oxygen_saturation=request.form.get('oxygen_saturation')
        )
        db.session.add(metric)
        db.session.commit()
        
        # Update RAG with new metrics
        update_rag_on_new_health_metric(metric)
        
        flash('Health metrics recorded successfully!', 'success')
        return redirect(url_for('patient_health_metrics'))
    
    metrics = HealthMetric.query.filter_by(patient_id=session['patient_id']).order_by(HealthMetric.recorded_date.desc()).all()
    
    # Get latest metric for BMI calculation
    latest_metric = metrics[0] if metrics else None
    bmi_category = get_bmi_category(latest_metric.bmi) if latest_metric and latest_metric.bmi else None
    
    return render_template('patient/health-metrics.html', metrics=metrics, latest_metric=latest_metric, bmi_category=bmi_category)

@app.route('/patient/reports', methods=['GET', 'POST'])
@patient_required
def patient_reports():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'reports', filename)
            file.save(filepath)
            
            report = MedicalReport(
                patient_id=session['patient_id'],
                report_type=request.form.get('report_type'),
                title=request.form.get('title'),
                file_path=f"reports/{filename}"
            )
            db.session.add(report)
            db.session.commit()
            
            flash('Report uploaded successfully!', 'success')
            return redirect(url_for('patient_reports'))
    
    reports = MedicalReport.query.filter_by(patient_id=session['patient_id']).order_by(MedicalReport.upload_date.desc()).all()
    return render_template('patient/reports.html', reports=reports)

# Doctor Routes
@app.route('/doctor/dashboard')
@doctor_required
def doctor_dashboard():
    doctor = Doctor.query.get(session['doctor_id'])
    
    # Statistics
    total_patients = Patient.query.count()
    today_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id,
        appointment_date=date.today()
    ).count()
    pending_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id,
        status='pending'
    ).count()
    
    # Recent appointments
    recent_appointments = Appointment.query.filter_by(
        doctor_id=doctor.id
    ).order_by(Appointment.appointment_date.desc()).limit(5).all()
    
    # Critical patients
    critical_patients = Patient.query.filter_by(priority_level='critical').all()
    
    return render_template('doctor/dashboard.html',
                         doctor=doctor,
                         total_patients=total_patients,
                         today_appointments=today_appointments,
                         pending_appointments=pending_appointments,
                         recent_appointments=recent_appointments,
                         critical_patients=critical_patients)

@app.route('/doctor/patients')
@doctor_required
def doctor_patients():
    priority = request.args.get('priority')
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = Patient.query
    
    if priority:
        query = query.filter_by(priority_level=priority)
    if category:
        query = query.filter_by(disease_category=category)
    if search:
        query = query.filter(Patient.name.like(f'%{search}%'))
    
    patients = query.all()
    
    # Get unique categories for filter
    categories = db.session.query(Patient.disease_category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    return render_template('doctor/patients.html', patients=patients, categories=categories)

@app.route('/doctor/patients/<int:patient_id>')
@doctor_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    appointments = Appointment.query.filter_by(patient_id=patient_id).order_by(Appointment.appointment_date.desc()).all()
    prescriptions = Prescription.query.filter_by(patient_id=patient_id).order_by(Prescription.date_issued.desc()).all()
    health_metrics = HealthMetric.query.filter_by(patient_id=patient_id).order_by(HealthMetric.recorded_date.desc()).all()
    chat_history = ChatHistory.query.filter_by(patient_id=patient_id).order_by(ChatHistory.timestamp.desc()).limit(10).all()
    doctor_notes = DoctorNote.query.filter_by(patient_id=patient_id, doctor_id=session['doctor_id']).order_by(DoctorNote.note_date.desc()).all()
    reports = MedicalReport.query.filter_by(patient_id=patient_id).order_by(MedicalReport.upload_date.desc()).all()
    
    return render_template('doctor/patient-detail.html',
                         patient=patient,
                         appointments=appointments,
                         prescriptions=prescriptions,
                         health_metrics=health_metrics,
                         chat_history=chat_history,
                         doctor_notes=doctor_notes,
                         reports=reports)

@app.route('/doctor/patients/<int:patient_id>/update', methods=['POST'])
@doctor_required
def update_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    
    patient.priority_level = request.form.get('priority_level')
    patient.disease_category = request.form.get('disease_category')
    patient.tags = request.form.get('tags')
    
    db.session.commit()
    
    # Update RAG with new patient data
    update_rag_on_patient_update(patient)
    flash('Patient updated successfully', 'success')
    
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/doctor/patients/<int:patient_id>/notes', methods=['POST'])
@doctor_required
def add_note(patient_id):
    note_content = request.form.get('note_content')
    
    note = DoctorNote(
        patient_id=patient_id,
        doctor_id=session['doctor_id'],
        note_content=note_content
    )
    db.session.add(note)
    db.session.commit()
    
    flash('Note added successfully', 'success')
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/doctor/patients/<int:patient_id>/prescribe', methods=['POST'])
@doctor_required
def prescribe(patient_id):
    medicines = request.form.get('medicines')
    diagnosis = request.form.get('diagnosis')
    notes = request.form.get('notes')
    
    prescription = Prescription(
        patient_id=patient_id,
        doctor_id=session['doctor_id'],
        medicines=medicines,
        diagnosis=diagnosis,
        notes=notes
    )
    db.session.add(prescription)
    db.session.commit()
    
    # Update RAG with new prescription
    update_rag_on_new_prescription(prescription)
    
    # Send email notification
    patient = Patient.query.get(patient_id)
    user = User.query.get(patient.user_id)
    subject = "New Prescription Available"
    body = f"<p>Hello {patient.name},</p><p>A new prescription has been issued for you. Please log in to view details.</p>"
    send_email(user.email, subject, body)
    
    flash('Prescription created successfully', 'success')
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/doctor/patients/<int:patient_id>/email', methods=['POST'])
@doctor_required
def send_patient_email(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    user = User.query.get(patient.user_id)
    
    subject = request.form.get('subject')
    message = request.form.get('message')
    
    if send_email(user.email, subject, message):
        email_log = EmailLog(
            doctor_id=session['doctor_id'],
            patient_id=patient_id,
            subject=subject,
            content=message
        )
        db.session.add(email_log)
        db.session.commit()
        
        flash('Email sent successfully', 'success')
    else:
        flash('Failed to send email', 'error')
    
    return redirect(url_for('patient_detail', patient_id=patient_id))

@app.route('/doctor/calendar')
@doctor_required
def doctor_calendar():
    doctor = Doctor.query.get(session['doctor_id'])
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()
    schedules = DoctorSchedule.query.filter_by(doctor_id=doctor.id).all()
    blocked_slots = BlockedSlot.query.filter_by(doctor_id=doctor.id).all()
    
    return render_template('doctor/calendar.html',
                         doctor=doctor,
                         appointments=appointments,
                         schedules=schedules,
                         blocked_slots=blocked_slots)

@app.route('/doctor/schedule', methods=['POST'])
@doctor_required
def update_schedule():
    data = request.get_json()
    doctor_id = session['doctor_id']
    
    # Delete existing schedules
    DoctorSchedule.query.filter_by(doctor_id=doctor_id).delete()
    
    # Add new schedules
    for schedule in data.get('schedules', []):
        new_schedule = DoctorSchedule(
            doctor_id=doctor_id,
            day_of_week=schedule['day'],
            start_time=schedule['start_time'],
            end_time=schedule['end_time'],
            is_available=True
        )
        db.session.add(new_schedule)
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/doctor/block-slot', methods=['POST'])
@doctor_required
def block_slot():
    data = request.get_json()
    
    blocked = BlockedSlot(
        doctor_id=session['doctor_id'],
        blocked_date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
        start_time=data.get('start_time'),
        end_time=data.get('end_time'),
        reason=data.get('reason')
    )
    db.session.add(blocked)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/doctor/appointments/<int:appointment_id>/update', methods=['POST'])
@doctor_required
def update_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    status = request.form.get('status')
    notes = request.form.get('notes')
    
    appointment.status = status
    if notes:
        appointment.notes = notes
    
    db.session.commit()
    
    flash('Appointment updated successfully', 'success')
    return redirect(url_for('doctor_calendar'))

@app.route('/doctor/ai-assistant', methods=['GET', 'POST'])
@doctor_required
def ai_assistant():
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Handle clear chat
            if data.get('action') == 'clear_chat':
                DoctorChat.query.filter_by(doctor_id=session['doctor_id']).delete()
                db.session.commit()
                return jsonify({'success': True})
            
            patient_id = data.get('patient_id')
            query = data.get('content', '').strip()
            
            # ===== NEW: USE INTENT CLASSIFIER =====
            # Detect intent using ML classifier
            intent, intent_probs = intent_classifier.predict_intent(query, return_probabilities=True)
            confidence = intent_probs[intent]
            
            print(f"🔍 Query: '{query}'")
            print(f"🎯 Detected intent: {intent} (confidence: {confidence:.2%})")
            
            # If confidence is low, might be general query
            if confidence < 0.4:
                print(f"⚠️ Low confidence ({confidence:.2%}), treating as GENERAL_QUERY")
                intent = 'GENERAL_QUERY'
            
            # Get FULL chat history for context
            recent_chats = DoctorChat.query.filter_by(
                doctor_id=session['doctor_id']
            ).order_by(DoctorChat.timestamp.desc()).limit(10).all()
            recent_chats.reverse()
            
            # ===== HANDLE DIFFERENT INTENTS =====
            
            # 1. RESEARCH QUERIES
            if intent == 'RESEARCH_QUERY':
                response = handle_research_query(query, recent_chats)
                
                # Save to chat history
                chat = DoctorChat(
                    doctor_id=session['doctor_id'],
                    patient_id=None,
                    message=query,
                    response=response,
                    query_type='research'
                )
                db.session.add(chat)
                db.session.commit()
                
                return jsonify({'response': response})
            
            # 2. SIMILAR CASES - even without patient selected, we can search
            if intent == 'SIMILAR_CASES_QUERY' and not patient_id:
                # Check if it's actually asking for patient list
                if any(word in query.lower() for word in ['list all patients', 'all patients', 'show patients', 'patient names']):
                    # This should go to general handler instead
                    response = handle_general_query(query, recent_chats, intent)
                else:
                    # Try to find similar cases from all patients
                    response = find_similar_cases_global(query)
                
                chat = DoctorChat(
                    doctor_id=session['doctor_id'],
                    patient_id=None,
                    message=query,
                    response=response,
                    query_type='similar_cases'
                )
                db.session.add(chat)
                db.session.commit()
                
                return jsonify({'response': response})
            
            # 3. Handle patient selection commands
            if not patient_id and intent != 'RESEARCH_QUERY':
                selected_patient = find_patient_by_name(query)
                if selected_patient:
                    return jsonify({
                        'select_patient': selected_patient.id,
                        'patient_name': selected_patient.name,
                        'response': f"✅ Selected patient: **{selected_patient.name}**. Now you can ask questions about them.\n\nDetected intent: {intent_classifier.get_intent_description(intent)}"
                    })
            
            # 4. Handle general queries (no patient selected)
            if not patient_id:
                response = handle_general_query(query, recent_chats, intent)
                
                # Save to chat history
                chat = DoctorChat(
                    doctor_id=session['doctor_id'],
                    patient_id=None,
                    message=query,
                    response=response,
                    query_type=intent.lower()
                )
                db.session.add(chat)
                db.session.commit()
                
                return jsonify({'response': response})
            
            # 5. Handle patient-specific queries
            patient = Patient.query.get(patient_id)
            if not patient:
                return jsonify({'response': 'Patient not found.'})
            
            # Use intent to route to appropriate handler
            response = handle_patient_query_by_intent(patient, query, intent, recent_chats)
            
            # Save to chat history
            chat = DoctorChat(
                doctor_id=session['doctor_id'],
                patient_id=patient_id,
                message=query,
                response=response,
                query_type=intent.lower()
            )
            db.session.add(chat)
            db.session.commit()
            
            return jsonify({'response': response})
    
        except Exception as e:
            print(f"=== ROUTE ERROR: {str(e)} ===")
            return jsonify({'response': f'Error processing request: {str(e)}'})

    # GET request
    patients = Patient.query.all()
    chat_history = get_chat_history(session['doctor_id'])
    return render_template('doctor/ai-assistant.html', patients=patients, chat_history=chat_history)


def handle_research_query(query, chat_history=None):
    """Handle medical research queries"""
    
    research_topics = {
        'migraine': {
            'title': 'Latest Research on Migraine Treatment in Young Adults',
            'content': """**📊 Recent Findings (2024-2025):**

**1. CGRP Antagonists**
• New oral CGRP receptor antagonists show 60% efficacy in young adults
• Fewer side effects compared to traditional triptans
• Recommended as first-line for episodic migraine

**2. Neuromodulation Devices**
• Non-invasive vagus nerve stimulation approved for acute treatment
• 45% reduction in monthly migraine days
• Minimal side effects, good for medication-overuse headache

**3. Lifestyle Interventions**
• Regular sleep schedule reduces frequency by 30%
• Magnesium supplementation (400-600mg) effective for some patients
• Cognitive behavioral therapy shows 40% improvement in young adults

**4. Emerging Therapies**
• Monoclonal antibodies targeting PACAP receptors in Phase III trials
• Personalized medicine based on genetic markers
• Digital therapeutics and migraine tracking apps

**💡 Clinical Pearl:** Consider combination therapy: acute treatment (triptans/gepants) + prevention (lifestyle + monthly CGRP mAbs) for optimal outcomes.

*Would you like specific dosing information or recent clinical trial data?*"""
        },
        'diabetes': {
            'title': 'Latest Research on Diabetes Management',
            'content': """**📊 Recent Diabetes Research (2024-2025):**

**1. Continuous Glucose Monitors**
• Real-time CGM reduces HbA1c by 1.5% on average
• Emerging implantable sensors lasting 6 months

**2. GLP-1 Agonists**
• Weekly oral formulation showing 85% adherence
• Cardiovascular benefits independent of weight loss

**3. Artificial Pancreas**
• Closed-loop systems approved for Type 1
• Hybrid systems showing promise for Type 2"""
        },
        'hypertension': {
            'title': 'Latest Research on Hypertension',
            'content': """**📊 Recent Hypertension Research (2024-2025):**

**1. Renal Denervation**
• New catheter techniques show 15-20 mmHg reduction
• Durable effect at 3 years follow-up

**2. Combination Therapy**
• Single-pill combinations improve adherence by 40%
• SGLT2 inhibitors show BP benefits in diabetics

**3. Digital Health**
• Smartphone-based BP monitoring accurate within 3 mmHg
• AI-powered medication titration algorithms"""
        }
    }
    
    query_lower = query.lower()
    
    # Check for specific topics
    for topic, data in research_topics.items():
        if topic in query_lower:
            return data['content']
    
    # If no specific topic found, use AI for research
    research_prompt = f"""You are a medical research assistant. Provide the latest evidence-based information on:
{query}

Include:
- Recent studies (2024-2025)
- Clinical guidelines
- Treatment options
- Relevant citations if possible

Be concise and practical for a clinician."""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": research_prompt,
                "temperature": 0.3,
                "stream": False,
                "options": {"num_predict": 600}
            },
            timeout=60
        )
        
        if response.status_code == 200:
            ai_response = response.json().get("response", "").strip()
            return ai_response
        else:
            return get_fallback_research_response(query)
            
    except Exception as e:
        return get_fallback_research_response(query)


def get_fallback_research_response(query):
    """Provide fallback research responses when AI is unavailable"""
    
    query_lower = query.lower()
    
    if 'migraine' in query_lower:
        return """**📊 Migraine Treatment in Young Adults - Key Points:**

**Acute Treatment:**
• Triptans (sumatriptan, rizatriptan) - 70% effective
• Gepants (rimegepant, ubrogepant) - Newer option, fewer side effects
• NSAIDs - First-line for mild cases

**Prevention:**
• Propranolol 40-160mg daily
• Topiramate 25-100mg (watch for cognitive side effects)
• CGRP monoclonal antibodies - Monthly injections

**Lifestyle:**
• Regular sleep schedule
• Hydration (2-3L daily)
• Avoid triggers (caffeine, alcohol, processed foods)

**Recent Studies 2024:**
• NEJM: Erenumab reduces monthly migraine days by 50%
• Lancet: Rimegepant effective for acute treatment in adolescents

*Would you like specific dosing or drug interaction information?*"""
    
    elif 'diabetes' in query_lower:
        return """**📊 Diabetes Research Update 2024-2025:**

**Type 2 Diabetes:**
• GLP-1 agonists show cardiovascular benefits
• SGLT2 inhibitors reduce heart failure risk
• New once-weekly insulin in development

**Type 1 Diabetes:**
• Closed-loop systems improve glucose control
• Teplizumab delays onset in at-risk patients
• Islet cell transplantation advances"""
    
    else:
        return f"""**🔬 Research Query: "{query}"**

I can help you research:
• Migraine treatments in young adults
• Diabetes management updates
• Hypertension guidelines
• Specific drug interactions

Please specify your research topic for detailed information."""


def handle_general_query(query, chat_history=None, intent='GENERAL_QUERY'):
    """Handle general questions with AI - makes it conversational like a real assistant"""
    
    query_lower = query.lower()
    
    # Simple greetings - NOW USING AI, not static menu
    if any(word in query_lower for word in ['hi', 'hello', 'hey', 'how are you']):
        # This will now go through the AI flow above
        pass  # Let the AI handle it
    
    # Get real data for context
    total_patients = Patient.query.count()
    patients = Patient.query.all()
    today_appts = Appointment.query.filter_by(appointment_date=date.today()).count()
    
    # ===== USE AI FOR ALL CONVERSATIONAL RESPONSES =====
    # Build context for AI
    context = f"""
You are a friendly and professional medical AI assistant helping a doctor.
Current statistics:
- Total patients: {total_patients}
- Appointments today: {today_appts}
- Patients in database: {', '.join([p.name for p in patients[:5]])}{'...' if len(patients) > 5 else ''}

The doctor just said: "{query}"

IMPORTANT RULES:
1. Respond naturally and conversationally - like a real human assistant
2. If they say "hi", "hello", "how are you" - respond warmly, not with a menu
3. If they say "bye", "goodbye", "thanks" - respond appropriately
4. Keep responses concise but friendly
5. Don't just list options - have a real conversation
6. Use the context above to inform your responses
7. If they ask about patients, offer to help select one

Example good responses:
- "Hi doctor! I'm doing well, thanks for asking. How can I help you today?"
- "Goodbye! Let me know if you need anything else."
- "You're welcome! Feel free to ask about any patient or medical topic."
"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": context,
                "temperature": 0.7,  # Higher temperature for more natural conversation
                "stream": False,
                "options": {"num_predict": 150}
            },
            timeout=30
        )
        
        if response.status_code == 200:
            ai_response = response.json().get("response", "").strip()
            
            # If AI response is too long or weird, use fallback
            if len(ai_response) < 10 or "?" not in ai_response:
                # Use fallback for simple cases
                if any(word in query_lower for word in ['hi', 'hello', 'hey']):
                    return "👋 Hi doctor! How can I assist you today?"
                elif any(word in query_lower for word in ['bye', 'goodbye', 'see you']):
                    return "� Goodbye! Feel free to come back if you need anything."
                elif 'how are you' in query_lower:
                    return "😊 I'm doing well, thank you! Ready to help with your patients."
                elif 'thank' in query_lower:
                    return "🙏 You're welcome! Happy to help."
            
            return ai_response
        else:
            # Fallback responses
            return get_fallback_general_response(query)
            
    except Exception as e:
        print(f"AI error in general query: {e}")
        return get_fallback_general_response(query)


def get_fallback_general_response(query):
    """Fallback responses when AI is unavailable"""
    query_lower = query.lower()
    
    # Greetings
    if any(word in query_lower for word in ['hi', 'hello', 'hey']):
        return "👋 Hello doctor! How can I help you today?"
    
    # How are you
    if 'how are you' in query_lower:
        return "😊 I'm doing well, thanks for asking! Ready to assist with your patients."
    
    # Thanks
    if any(word in query_lower for word in ['thank', 'thanks']):
        return "🙏 You're welcome! Let me know if you need anything else."
    
    # Goodbye
    if any(word in query_lower for word in ['bye', 'goodbye', 'see you']):
        return "👋 Goodbye! Have a great day, doctor."
    
    # Help
    if 'help' in query_lower:
        return """🤖 **I can help you with:**
• Patient information - just select a patient and ask
• Medical research - ask about latest treatments
• Similar cases - find patients with similar symptoms
• Appointments - check visit history

What would you like to know?"""
    
    # Default - use AI-friendly prompt
    total_patients = Patient.query.count()
    return f"I have {total_patients} patients in the database. You can ask me about any of them, or type 'help' to see what I can do."


def find_patient_by_name(query):
    """Find patient by name from natural language"""
    query_lower = query.lower()
    
    # Common patterns for patient selection
    patterns = [
        'select patient', 'choose patient', 'pick patient',
        'patient named', 'patient called', 'show patient',
        'about patient', 'for patient', 'switch to'
    ]
    
    # Extract potential name
    for pattern in patterns:
        if pattern in query_lower:
            # Get text after pattern
            name_part = query_lower.split(pattern)[-1].strip()
            if name_part:
                # Search for patient
                patients = Patient.query.all()
                for patient in patients:
                    if patient.name.lower() in name_part or name_part in patient.name.lower():
                        return patient
                # Try fuzzy match
                for patient in patients:
                    if patient.name.lower().startswith(name_part[:3]):
                        return patient
    
    # Direct name mention
    patients = Patient.query.all()
    for patient in patients:
        if patient.name.lower() in query_lower:
            return patient
    
    return None


def handle_patient_query_with_context(patient, query, query_type, chat_history):
    """Handle patient-specific queries with conversation context"""
    
    query_lower = query.lower().strip()
    patient_name = patient.name
    
    # Get patient data
    latest_metrics = HealthMetric.query.filter_by(patient_id=patient.id).order_by(HealthMetric.recorded_date.desc()).first()
    all_prescriptions = Prescription.query.filter_by(patient_id=patient.id).order_by(Prescription.date_issued.desc()).all()
    
    # ========== UNDERSTAND WHAT IS BEING ASKED ==========
    
    # 1. SIMILAR PATIENTS QUERY
    if any(word in query_lower for word in ['similar', 'like', 'same as', 'other patients', 'any other']):
        print(f"🔍 DOCTOR ASKS: Find similar patients to {patient_name}")
        return find_similar_patients(patient, query)
    
    # 2. DESCRIBE PATIENT QUERY
    if any(word in query_lower for word in ['describe', 'tell me about', 'profile', 'summary', 'who is']):
        print(f"📋 DOCTOR ASKS: Describe {patient_name}")
        return describe_current_patient(patient, latest_metrics, all_prescriptions)
    
    # 3. SYMPTOMS QUERY
    if any(word in query_lower for word in ['symptom', 'complaint', 'problem', 'issue', 'concern', 'what is wrong']):
        print(f"🩺 DOCTOR ASKS: What are {patient_name}'s symptoms")
        if patient.symptoms:
            return f"**{patient_name}'s symptoms:** {patient.symptoms}"
        else:
            return f"No symptoms recorded for {patient_name}."
    
    # 4. VITALS/HEALTH METRICS QUERY
    if any(word in query_lower for word in ['vital', 'bp', 'blood pressure', 'heart rate', 'bmi', 'health metrics']):
        print(f"📊 DOCTOR ASKS: Show vitals for {patient_name}")
        if latest_metrics:
            return f"""**{patient_name}'s Latest Vitals:**
• Blood Pressure: {latest_metrics.blood_pressure_systolic}/{latest_metrics.blood_pressure_diastolic}
• Heart Rate: {latest_metrics.heart_rate} bpm
• BMI: {latest_metrics.bmi}
• Blood Sugar: {latest_metrics.blood_sugar} mg/dL
• Recorded: {latest_metrics.recorded_date.strftime('%Y-%m-%d')}"""
        else:
            return f"No health metrics recorded for {patient_name}."
    
    # 5. TREATMENT HISTORY QUERY (combined appointments + prescriptions)
    # Make sure this comes AFTER the specific upcoming/past queries checks or allows fall-through
    if any(word in query_lower for word in ['last time', 'previous', 'past', 'history', 'treated', 'gave', 'prescribed', 'appointment', 'visit', 'seen']):
        # Check if it's asking specifically about appointments (handled below)
        if 'upcoming' in query_lower or 'future' in query_lower or 'next' in query_lower:
            pass # Fall through to upcoming handler
        elif 'past' in query_lower or 'recent' in query_lower or 'last' in query_lower:
            pass # Fall through to past handler
        else:
            print(f"📅 DOCTOR ASKS: Complete history for {patient_name}")
            
            # Get appointments for this patient
            appointments = Appointment.query.filter_by(
                patient_id=patient.id
            ).order_by(Appointment.appointment_date.desc()).all()
            
            # Get prescriptions
            prescriptions = Prescription.query.filter_by(
                patient_id=patient.id
            ).order_by(Prescription.date_issued.desc()).all()
            
            if not appointments and not prescriptions:
                return f"📭 No records found for **{patient_name}**.\n\nThis patient has no appointments or prescriptions yet."
            
            response = f"**📋 Patient History for {patient_name}**\n\n"
            
            # Show appointments first
            if appointments:
                response += f"**📅 Appointments:**\n"
                for i, apt in enumerate(appointments[:3], 1):
                    status_icon = "✅" if apt.status == 'completed' else "🟡" if apt.status == 'confirmed' else "🔴"
                    response += f"{i}. {status_icon} **{apt.appointment_date.strftime('%B %d, %Y')}** at {apt.time_slot}\n"
                    if apt.reason:
                        response += f"   • Reason: {apt.reason}\n"
                    if apt.status:
                        response += f"   • Status: {apt.status.capitalize()}\n"
                    if apt.notes:
                        response += f"   • Notes: {apt.notes}\n"
                    response += "\n"
                
                # Show most recent appointment specifically
                latest_apt = appointments[0]
                response += f"**✨ Most Recent:** {latest_apt.appointment_date.strftime('%B %d, %Y')} at {latest_apt.time_slot} ({latest_apt.status})\n\n"
            
            # Show prescriptions
            if prescriptions:
                response += f"**💊 Prescriptions:**\n"
                for i, rx in enumerate(prescriptions[:3], 1):
                    response += f"{i}. {rx.date_issued.strftime('%B %d, %Y')}\n"
                    response += f"   • Diagnosis: {rx.diagnosis or 'Not specified'}\n"
                    response += f"   • Medications: {rx.medicines}\n"
                    if rx.notes:
                        response += f"   • Notes: {rx.notes}\n"
                    response += "\n"
            
            # Summary
            if appointments and prescriptions:
                response += f"**📊 Summary:** {len(appointments)} appointment(s), {len(prescriptions)} prescription(s) on record"
            elif appointments:
                response += f"**📊 Summary:** {len(appointments)} appointment(s) on record"
            elif prescriptions:
                response += f"**📊 Summary:** {len(prescriptions)} prescription(s) on record"
            
            return response
    
    
    # 5.2 UPCOMING APPOINTMENTS QUERY
    if any(word in query_lower for word in ['upcoming', 'future', 'next appointment', 'scheduled', 'yet to come']):
        print(f"📅 DOCTOR ASKS: Upcoming appointments for {patient_name}")
        
        # Get today's date
        today_date = date.today()
        
        # Get upcoming appointments (today or future)
        upcoming = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date >= today_date
        ).order_by(Appointment.appointment_date).all()
        
        # Get past appointments for context
        past_appointments = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date < today_date
        ).order_by(Appointment.appointment_date.desc()).all()
        
        if not upcoming:
            if past_appointments:
                return f"❌ No upcoming appointments for **{patient_name}**.\n\n📅 They have {len(past_appointments)} past visit(s). Last visit: {past_appointments[0].appointment_date.strftime('%B %d, %Y')}"
            else:
                return f"❌ No appointments found for **{patient_name}**. This patient has no visit history yet."
        
        response = f"**📅 Upcoming Appointments for {patient_name}**\n\n"
        
        for i, apt in enumerate(upcoming, 1):
            # Calculate days from now
            days_until = (apt.appointment_date - today_date).days
            if days_until == 0:
                when = "🟢 TODAY"
            elif days_until == 1:
                when = "🟡 TOMORROW"
            else:
                when = f"📆 In {days_until} days"
            
            response += f"{i}. **{apt.appointment_date.strftime('%B %d, %Y')}** at {apt.time_slot} {when}\n"
            response += f"   • Reason: {apt.reason or 'Not specified'}\n"
            response += f"   • Status: {apt.status.capitalize()}\n\n"
        
        # Show next appointment specifically
        next_apt = upcoming[0]
        days_until = (next_apt.appointment_date - today_date).days
        if days_until == 0:
            response += f"**⏰ Next appointment is TODAY at {next_apt.time_slot}!**\n"
        else:
            response += f"**⏰ Next appointment:** {next_apt.appointment_date.strftime('%B %d, %Y')} (in {days_until} days)"
        
        return response

    # 5.3 PAST/RECENT APPOINTMENTS QUERY
    if any(word in query_lower for word in ['past', 'recent', 'previous', 'last visit', 'history', 'old']):
        print(f"📅 DOCTOR ASKS: Past appointments for {patient_name}")
        
        # Get today's date
        today_date = date.today()
        
        # Get past appointments (before today)
        past = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.appointment_date < today_date
        ).order_by(Appointment.appointment_date.desc()).all()
        
        if not past:
            return f"No past appointments found for **{patient_name}**."
        
        response = f"**📅 Past Appointments for {patient_name}**\n\n"
        
        for i, apt in enumerate(past[:5], 1):  # Show last 5
            response += f"{i}. **{apt.appointment_date.strftime('%B %d, %Y')}** at {apt.time_slot}\n"
            response += f"   • Reason: {apt.reason or 'Not specified'}\n"
            response += f"   • Status: {apt.status.capitalize()}\n\n"
        
        # Most recent
        last = past[0]
        response += f"**✨ Most Recent Visit:** {last.appointment_date.strftime('%B %d, %Y')} at {last.time_slot}"
        
        return response

    
    # 6. AGE/GENDER QUERY
    if 'age' in query_lower or 'how old' in query_lower:
        return f"**{patient_name} is {patient.age} years old.**"
    if 'gender' in query_lower or 'male' in query_lower or 'female' in query_lower:
        return f"**{patient_name} is {patient.gender}.**"
    
    # 7. FAMILY HISTORY QUERY
    if 'family history' in query_lower:
        print(f"👪 DOCTOR ASKS: Family history for {patient_name}")
        return f"**{patient_name}'s Family History:** {patient.family_history or 'None recorded'}"
    
    # 8. MEDICAL HISTORY QUERY
    if 'medical history' in query_lower or 'past history' in query_lower:
        print(f"📜 DOCTOR ASKS: Medical history for {patient_name}")
        return f"**{patient_name}'s Medical History:** {patient.medical_history or 'None recorded'}"
    
    # 9. SPECIFIC PATIENT COMPARISON (only if explicitly asked)
    if any(word in query_lower for word in ['compare', 'vs', 'versus', 'difference between']):
        print(f"🔄 DOCTOR ASKS: Compare patients")
        # Extract the other patient name
        all_patients = Patient.query.all()
        for p in all_patients:
            if p.id != patient.id and p.name.lower() in query_lower:
                return compare_two_patients(patient, p)
    
    # 10. MEDICATION SPECIFIC QUERY
    if any(word in query_lower for word in ['medication', 'medicine', 'drug', 'dosage', 'dose']):
        print(f"💊 DOCTOR ASKS: About medications for {patient_name}")
        # Check if they're asking about a specific medication
        if all_prescriptions:
            return f"**Medications prescribed to {patient_name}:**\n" + "\n".join([f"• {rx.medicines}" for rx in all_prescriptions[:5]])
        else:
            return f"No medications have been prescribed to {patient_name} yet."
    
    # ========== IF NONE OF THE ABOVE MATCH, USE AI ==========
    print(f"🤖 USING AI FOR: {query}")
    
    # Build context for AI
    context = f"""
Patient: {patient_name}
Age: {patient.age}
Gender: {patient.gender}
Symptoms: {patient.symptoms or 'None'}
Medical History: {patient.medical_history or 'None'}
Family History: {patient.family_history or 'None'}

Latest Vitals:
- BP: {latest_metrics.blood_pressure_systolic}/{latest_metrics.blood_pressure_diastolic if latest_metrics else 'N/A'}
- HR: {latest_metrics.heart_rate if latest_metrics else 'N/A'} bpm
- BMI: {latest_metrics.bmi if latest_metrics else 'N/A'}

Prescriptions: {len(all_prescriptions)} total
Last Prescription: {all_prescriptions[0].medicines if all_prescriptions else 'None'}
"""
    
    ai_prompt = f"""You are a medical AI assistant helping a doctor. Answer ONLY what is asked.

{context}

Doctor's question: {query}

RULES:
1. Answer ONLY the question asked - no extra information
2. Be concise and direct
3. If you don't know, say "I don't have that information"
4. Use the patient data above

Answer:"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": ai_prompt,
                "temperature": 0.2,
                "stream": False,
                "options": {"num_predict": 300}
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            return f"I couldn't process that question about {patient_name}. Please try rephrasing."
    except:
        return f"I'm having trouble answering that about {patient_name}. Please try a simpler question."


# Helper functions for chat history
def save_chat_message(doctor_id, message, response, query_type, patient_id=None):
    """Save chat message to database"""
    try:
        chat = DoctorChat(
            doctor_id=doctor_id,
            patient_id=patient_id,
            message=message,
            response=response,
            query_type=query_type
        )
        db.session.add(chat)
        db.session.commit()
    except Exception as e:
        print(f"Error saving chat: {e}")


def get_chat_history(doctor_id, limit=50):
    """Get chat history for a doctor"""
    try:
        chats = DoctorChat.query.filter_by(
            doctor_id=doctor_id
        ).order_by(DoctorChat.timestamp.desc()).limit(limit).all()
        
        # Reverse to show oldest first
        chats.reverse()
        
        history = []
        for chat in chats:
            patient_name = "General"
            if chat.patient_id:
                patient = Patient.query.get(chat.patient_id)
                patient_name = patient.name if patient else "Unknown"
            
            history.append({
                'id': chat.id,
                'message': chat.message,
                'response': chat.response,
                'timestamp': chat.timestamp.strftime('%H:%M %p'),
                'date': chat.timestamp.strftime('%Y-%m-%d'),
                'query_type': chat.query_type,
                'patient_name': patient_name
            })
        return history
    except:
        return []


def get_clinical_similar_cases(patient, limit=3):
    """Get clinically relevant similar cases"""
    try:
        if not patient.disease_category and not patient.symptoms:
            return ""
        
        # Find similar patients based on symptoms and diagnosis
        similar = Patient.query.filter(
            Patient.disease_category == patient.disease_category,
            Patient.id != patient.id
        ).limit(limit).all()
        
        cases = []
        for sp in similar:
            latest_rx = Prescription.query.filter_by(
                patient_id=sp.id
            ).order_by(Prescription.date_issued.desc()).first()
            
            if latest_rx:
                cases.append(f"• Similar case (Age {sp.age}): {sp.symptoms[:100]} → Responded to {latest_rx.medicines[:50]}")
        
        return "\n".join(cases) if cases else ""
        
    except Exception as e:
        return ""

# ============================================
# SIMILAR PATIENTS SEARCH FUNCTION
# ============================================

def find_similar_patients(patient, query):
    """Find patients similar to the current patient and show what treatments worked"""
    
    print(f"🔍 Searching for patients similar to {patient.name}...")
    
    # Extract key symptoms and conditions
    patient_symptoms = patient.symptoms.lower() if patient.symptoms else ""
    patient_history = patient.medical_history.lower() if patient.medical_history else ""
    patient_category = patient.disease_category.lower() if patient.disease_category else ""
    
    # Keywords to focus on (remove common words)
    focus_keywords = []
    if patient_symptoms:
        # Extract important words (pain, headache, fever, etc.)
        words = patient_symptoms.replace(',', '').split()
        for word in words:
            if len(word) > 3 and word not in ['with', 'and', 'the', 'has', 'had', 'been', 'for']:
                focus_keywords.append(word)
    
    print(f"📌 Focus keywords: {focus_keywords}")
    
    # Search ALL other patients
    all_patients = Patient.query.filter(Patient.id != patient.id).all()
    similar_patients = []
    
    for p in all_patients:
        if not p.symptoms:
            continue
            
        p_symptoms = p.symptoms.lower()
        match_score = 0
        matched_keywords = []
        
        # Check for keyword matches - with better scoring
        for keyword in focus_keywords:
            if keyword in p_symptoms:
                # Count how many times the keyword appears
                occurrence_count = p_symptoms.count(keyword)
                match_score += 2 + (occurrence_count * 1)  # Bonus for multiple occurrences
                matched_keywords.append(keyword)
                
                # Extra points for exact phrase matches
                if len(keyword) > 4 and f" {keyword} " in f" {p_symptoms} ":
                    match_score += 2

        # Check for common medical phrases
        common_phrases = [
            'high blood pressure', 'hypertension', 
            'chronic fatigue', 'fatigue and', 'low energy',
            'chest pain', 'shortness of breath'
        ]
        for phrase in common_phrases:
            if phrase in patient_symptoms and phrase in p_symptoms:
                match_score += 5
                if phrase not in matched_keywords:
                    matched_keywords.append(f"matched: {phrase}")
        
        # Check for disease category match
        if patient_category and p.disease_category and patient_category in p.disease_category.lower():
            match_score += 3
            matched_keywords.append(f"same category: {p.disease_category}")
        
        # Check for symptom phrases
        if patient_symptoms and len(patient_symptoms) > 10:
            # Check if significant portion matches
            if patient_symptoms[:20] in p_symptoms or p_symptoms[:20] in patient_symptoms:
                match_score += 5
        
        if match_score >= 2:  # At least one significant match
            # Get treatment history for this patient
            prescriptions = Prescription.query.filter_by(patient_id=p.id).order_by(Prescription.date_issued.desc()).all()
            
            treatment_history = []
            outcomes = []
            
            for rx in prescriptions:
                treatment_info = f"{rx.date_issued.strftime('%Y-%m-%d')}: {rx.diagnosis} - {rx.medicines}"
                treatment_history.append(treatment_info)
                
                # Try to determine outcome from notes
                if rx.notes and any(word in rx.notes.lower() for word in ['improved', 'better', 'resolved', 'successful']):
                    outcomes.append(f"Positive outcome: {rx.notes[:50]}")
            
            similar_patients.append({
                'patient': p,
                'score': match_score,
                'matched_keywords': matched_keywords,
                'prescriptions': prescriptions,
                'treatment_history': treatment_history,
                'latest_rx': prescriptions[0] if prescriptions else None,
                'outcomes': outcomes,
                'total_treatments': len(prescriptions)
            })
    
    # Sort by match score (highest first)
    similar_patients.sort(key=lambda x: x['score'], reverse=True)
    
    print(f"✅ Found {len(similar_patients)} similar patients")
    
    if not similar_patients:
        # If no matches found, try RAG search
        try:
            rag_results = rag_system.search_similar(
                query=f"{patient.symptoms} {patient.disease_category or ''}",
                limit=3
            )
            
            if rag_results:
                response = f"## 🔎 Semantic Search Results\n\n"
                response += f"I couldn't find exact matches in the database, but here are semantically similar cases:\n\n"
                
                for r in rag_results:
                    response += f"• {r['text'][:200]}...\n"
                
                response += f"\n💡 Would you like me to search for specific symptoms instead?"
                return response
        except:
            pass
        
        return f"❌ No similar patients found for **{patient.name}**.\n\nTheir symptoms: {patient.symptoms or 'None recorded'}\n\nTry adding more symptom details to find matches."
    
    # Build comprehensive response
    response = f"## ✅ **Similar Patients Found for {patient.name}**\n\n"
    response += f"**{patient.name}'s symptoms:** {patient.symptoms or 'None'}\n\n"
    
    for i, sim in enumerate(similar_patients[:3], 1):  # Show top 3
        p = sim['patient']
        response += f"---\n"
        response += f"### **{i}. {p.name}** (Age {p.age}, {p.gender})\n\n"
        
        # Similarity explanation
        response += f"**Why similar:** {', '.join(sim['matched_keywords'][:3])}\n"
        response += f"**Match confidence:** {'🟢 High' if sim['score'] > 5 else '🟡 Medium' if sim['score'] > 2 else '🔵 Low'}\n\n"
        
        # Their symptoms
        response += f"**Their symptoms:** {p.symptoms or 'None'}\n\n"
        
        # TREATMENT INFORMATION
        if sim['prescriptions']:
            response += f"**💊 Treatment History:**\n"
            
            for j, rx in enumerate(sim['prescriptions'][:2]):  # Show last 2 treatments
                response += f"   • **{rx.date_issued.strftime('%B %d, %Y')}**\n"
                response += f"     - Diagnosis: {rx.diagnosis or 'Not specified'}\n"
                response += f"     - Medications: {rx.medicines}\n"
                if rx.notes:
                    response += f"     - Notes: {rx.notes}\n"
            
            if len(sim['prescriptions']) > 2:
                response += f"     *...and {len(sim['prescriptions'])-2} more treatments*\n"
            
            # Treatment outcomes if available
            if sim['outcomes']:
                response += f"\n**📊 Outcomes:**\n"
                for outcome in sim['outcomes'][:2]:
                    response += f"   • {outcome}\n"
        else:
            response += f"**No treatment records** for this patient.\n"
        
        # What worked for them
        if sim['latest_rx']:
            response += f"\n**✨ Most recent treatment:** {sim['latest_rx'].medicines} for {sim['latest_rx'].diagnosis or 'their condition'}\n"
        
        response += "\n"
    
    # Summary and recommendations
    response += f"---\n\n"
    response += f"### 💡 **Clinical Insights**\n\n"
    
    # Aggregate treatment patterns
    all_medicines = []
    for sim in similar_patients[:3]:
        for rx in sim['prescriptions']:
            if rx.medicines:
                all_medicines.append(rx.medicines)
    
    if all_medicines:
        from collections import Counter
        med_counter = Counter(all_medicines)
        common_meds = med_counter.most_common(2)
        
        response += f"**Common treatments among similar patients:**\n"
        for med, count in common_meds:
            response += f"• {med} (used in {count} similar case{'s' if count > 1 else ''})\n"
    
    response += f"\n**Would you like to:**\n"
    response += f"• See more details about any specific similar patient?\n"
    response += f"• Compare treatment outcomes?\n"
    response += f"• Ask about a specific medication used?\n"
    
    return response


# ============================================
# PATIENT DESCRIPTION FUNCTION
# ============================================

def describe_current_patient(patient, metrics, prescriptions):
    """Describe the current patient in detail"""
    
    response = f"## 📋 **Patient Profile: {patient.name}**\n\n"
    
    # Basic info
    response += f"**Age:** {patient.age or 'N/A'} years\n"
    response += f"**Gender:** {patient.gender or 'N/A'}\n\n"
    
    # Symptoms
    response += f"**Symptoms:**\n{patient.symptoms or 'No symptoms recorded'}\n\n"
    
    # Medical history
    response += f"**Medical History:**\n{patient.medical_history or 'None reported'}\n\n"
    
    # Family history
    response += f"**Family History:**\n{patient.family_history or 'None reported'}\n\n"
    
    # Vitals
    if metrics:
        response += f"**Latest Vitals:**\n"
        response += f"• BP: {metrics.blood_pressure_systolic}/{metrics.blood_pressure_diastolic}\n"
        response += f"• Heart Rate: {metrics.heart_rate} bpm\n"
        response += f"• BMI: {metrics.bmi}\n"
        response += f"• Blood Sugar: {metrics.blood_sugar} mg/dL\n\n"
    
    # Prescriptions
    if prescriptions:
        response += f"**Prescription History:**\n"
        for rx in prescriptions[:3]:
            response += f"• {rx.date_issued.strftime('%Y-%m-%d')}: {rx.diagnosis} - {rx.medicines}\n"
    else:
        response += f"**Prescription History:** None\n"
    
    response += f"\n💡 You can ask about:\n"
    response += f"• Similar patients\n"
    response += f"• Treatment options\n"
    response += f"• Previous visits\n"
    
    return response



# ============================================
# SYMPTOM SEARCH FUNCTION
# ============================================

def find_patients_by_symptom(symptom, current_patient=None):
    """Find all patients with a specific symptom"""
    
    symptom_lower = symptom.lower()
    
    # Search for patients with this symptom
    all_patients = Patient.query.all()
    matching = []
    
    for p in all_patients:
        if current_patient and p.id == current_patient.id:
            continue  # Skip current patient
            
        if p.symptoms and symptom_lower in p.symptoms.lower():
            latest_rx = Prescription.query.filter_by(patient_id=p.id).order_by(Prescription.date_issued.desc()).first()
            matching.append({
                'patient': p,
                'diagnosis': latest_rx.diagnosis if latest_rx else 'Unknown'
            })
    
    if not matching:
        if current_patient:
            return f"No other patients with '{symptom}' found in the database."
        else:
            return f"No patients with '{symptom}' found in the database."
    
    response = f"## 📊 Patients with '{symptom}'\n\n"
    response += f"Found {len(matching)} patient(s):\n\n"
    
    for i, m in enumerate(matching, 1):
        response += f"**{i}. {m['patient'].name}** (Age {m['patient'].age}, {m['patient'].gender})\n"
        response += f"   • Symptoms: {m['patient'].symptoms}\n"
        if m['diagnosis'] != 'Unknown':
            response += f"   • Diagnosis/Treatment: {m['diagnosis']}\n"
        if m['patient'].disease_category:
            response += f"   • Category: {m['patient'].disease_category}\n"
        response += "\n"
    
    return response


# ============================================
# PATIENT COMPARISON FUNCTION
# ============================================

def compare_two_patients(patient1, patient2):
    """Compare two patients side by side"""
    
    response = f"## 🔄 Patient Comparison\n\n"
    response += f"### {patient1.name} vs {patient2.name}\n\n"
    
    # Create comparison table
    response += "| Aspect | {0} | {1} |\n".format(patient1.name, patient2.name)
    response += "|--------|------|------|\n"
    
    # Age
    response += f"| Age | {patient1.age or 'N/A'} | {patient2.age or 'N/A'} |\n"
    
    # Gender
    response += f"| Gender | {patient1.gender or 'N/A'} | {patient2.gender or 'N/A'} |\n"
    
    # Symptoms
    response += f"| Symptoms | {patient1.symptoms or 'None'} | {patient2.symptoms or 'None'} |\n"
    
    # Medical History
    response += f"| Medical History | {patient1.medical_history or 'None'} | {patient2.medical_history or 'None'} |\n"
    
    # Family History
    response += f"| Family History | {patient1.family_history or 'None'} | {patient2.family_history or 'None'} |\n"
    
    # Disease Category
    response += f"| Category | {patient1.disease_category or 'N/A'} | {patient2.disease_category or 'N/A'} |\n"
    
    # Get latest prescriptions
    rx1 = Prescription.query.filter_by(patient_id=patient1.id).order_by(Prescription.date_issued.desc()).first()
    rx2 = Prescription.query.filter_by(patient_id=patient2.id).order_by(Prescription.date_issued.desc()).first()
    
    response += f"| Latest Treatment | {rx1.diagnosis if rx1 else 'None'} | {rx2.diagnosis if rx2 else 'None'} |\n"
    
    # Find common symptoms
    if patient1.symptoms and patient2.symptoms:
        symptoms1 = set(patient1.symptoms.lower().replace(',', '').split())
        symptoms2 = set(patient2.symptoms.lower().replace(',', '').split())
        common = symptoms1.intersection(symptoms2)
        if common:
            response += f"\n**Common Symptoms:** {', '.join(common)}\n"
    
    response += f"\n💡 Ask me: 'Show similar cases to {patient1.name}' or 'Find patients with same symptoms'"
    
    return response


# ============================================
# PATIENT MENTION CHECK FUNCTION
# ============================================

def check_for_patient_mention(query, current_patient=None):
    """Check if user is asking about another specific patient by name"""
    
    query_lower = query.lower()
    
    # List of patient names in database
    all_patients = Patient.query.all()
    
    for p in all_patients:
        # Skip current patient if provided
        if current_patient and p.id == current_patient.id:
            continue
            
        # Check if patient name is mentioned
        if p.name.lower() in query_lower:
            return p
    
    return None 

@app.route('/doctor/analytics')
@doctor_required
def doctor_analytics():
    doctor = Doctor.query.get(session['doctor_id'])
    
    # Patient statistics
    total_patients = Patient.query.count()
    
    # Age distribution
    age_groups = db.session.query(
        db.case(
            (Patient.age < 18, '0-17'),
            (Patient.age < 35, '18-34'),
            (Patient.age < 50, '35-49'),
            (Patient.age < 65, '50-64'),
            else_='65+'
        ).label('age_group'),
        db.func.count(Patient.id)
    ).group_by('age_group').all()
    
    # Disease distribution
    disease_stats = db.session.query(
        Patient.disease_category,
        db.func.count(Patient.id)
    ).group_by(Patient.disease_category).all()
    
    # Appointment statistics
    total_appointments = Appointment.query.filter_by(doctor_id=doctor.id).count()
    completed = Appointment.query.filter_by(doctor_id=doctor.id, status='completed').count()
    cancelled = Appointment.query.filter_by(doctor_id=doctor.id, status='cancelled').count()
    
    # Feedback statistics
    avg_rating = db.session.query(db.func.avg(Feedback.rating)).filter_by(doctor_id=doctor.id).scalar()
    
    return render_template('doctor/analytics.html',
                         total_patients=total_patients,
                         age_groups=age_groups,
                         disease_stats=disease_stats,
                         total_appointments=total_appointments,
                         completed=completed,
                         cancelled=cancelled,
                         avg_rating=round(avg_rating, 2) if avg_rating else 0)

# API endpoints for AJAX
@app.route('/api/available-slots')
@login_required
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date_str = request.args.get('date')
    
    appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    day_of_week = appointment_date.weekday()
    
    # Get doctor's schedule for that day
    schedule = DoctorSchedule.query.filter_by(
        doctor_id=doctor_id,
        day_of_week=day_of_week,
        is_available=True
    ).first()
    
    if not schedule:
        return jsonify({'slots': []})
    
    # Check for blocked slots
    blocked = BlockedSlot.query.filter_by(
        doctor_id=doctor_id,
        blocked_date=appointment_date
    ).first()
    
    if blocked:
        return jsonify({'slots': []})
    
    # Generate time slots
    doctor = Doctor.query.get(doctor_id)
    duration = doctor.consultation_duration
    
    start = datetime.strptime(schedule.start_time, '%H:%M')
    end = datetime.strptime(schedule.end_time, '%H:%M')
    
    slots = []
    current = start
    while current < end:
        time_str = current.strftime('%H:%M')
        
        # Check if slot is already booked
        existing = Appointment.query.filter_by(
            doctor_id=doctor_id,
            appointment_date=appointment_date,
            time_slot=time_str
        ).first()
        
        if not existing:
            slots.append(time_str)
        
        current += timedelta(minutes=duration)
    
    return jsonify({'slots': slots})

@app.route('/api/health-metrics-data')
@patient_required
def get_health_metrics_data():
    days = request.args.get('days', 30, type=int)
    start_date = datetime.now() - timedelta(days=days)
    
    metrics = HealthMetric.query.filter(
        HealthMetric.patient_id == session['patient_id'],
        HealthMetric.recorded_date >= start_date
    ).order_by(HealthMetric.recorded_date).all()
    
    data = {
        'dates': [m.recorded_date.strftime('%Y-%m-%d') for m in metrics],
        'weight': [m.weight for m in metrics],
        'bmi': [m.bmi for m in metrics],
        'blood_sugar': [m.blood_sugar for m in metrics],
        'heart_rate': [m.heart_rate for m in metrics],
        'bp_systolic': [m.blood_pressure_systolic for m in metrics],
        'bp_diastolic': [m.blood_pressure_diastolic for m in metrics]
    }
    
    return jsonify(data)

@app.route('/download/prescription/<int:prescription_id>')
@login_required
def download_prescription(prescription_id):
    prescription = Prescription.query.get_or_404(prescription_id)
    
    # Create PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Header
    p.setFont("Helvetica-Bold", 20)
    p.drawString(1*inch, 10*inch, "Medical Prescription")
    
    # Doctor info
    doctor = Doctor.query.get(prescription.doctor_id)
    p.setFont("Helvetica", 12)
    p.drawString(1*inch, 9.5*inch, f"Dr. {doctor.name}")
    p.drawString(1*inch, 9.3*inch, f"{doctor.specialization}")
    
    # Patient info
    patient = Patient.query.get(prescription.patient_id)
    p.drawString(1*inch, 8.8*inch, f"Patient: {patient.name}")
    p.drawString(1*inch, 8.6*inch, f"Age: {patient.age} | Gender: {patient.gender}")
    p.drawString(1*inch, 8.4*inch, f"Date: {prescription.date_issued.strftime('%Y-%m-%d')}")
    
    # Diagnosis
    p.drawString(1*inch, 8*inch, f"Diagnosis: {prescription.diagnosis or 'N/A'}")
    
    # Medicines
    p.setFont("Helvetica-Bold", 14)
    p.drawString(1*inch, 7.5*inch, "Medicines:")
    
    p.setFont("Helvetica", 11)
    medicines = json.loads(prescription.medicines) if prescription.medicines.startswith('[') else [prescription.medicines]
    y = 7.2*inch
    for med in medicines:
        p.drawString(1.2*inch, y, f"• {med}")
        y -= 0.2*inch
    
    # Notes
    if prescription.notes:
        y -= 0.3*inch
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1*inch, y, "Notes:")
        y -= 0.2*inch
        p.setFont("Helvetica", 11)
        p.drawString(1.2*inch, y, prescription.notes)
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'prescription_{prescription_id}.pdf', mimetype='application/pdf')

@app.route('/test-rag')
@doctor_required
def test_rag():
    """Test endpoint to see what RAG finds"""
    patient_id = request.args.get('patient_id')
    query = request.args.get('query', 'headache')
    
    if not patient_id:
        return "Please provide patient_id"
    
    try:
        results = rag_system.search_similar(
            query=query,
            patient_id=str(patient_id), # Ensure string for metadata match
            limit=5
        )
        
        html = "<h2>RAG Search Results</h2>"
        html += f"<p>Query: '{query}'</p>"
        html += "<hr>"
        
        if not results:
             html += "<p>No results found.</p>"

        for r in results:
            html += f"<p><strong>Found:</strong> {r['text']}</p>"
            html += f"<p><small>Metadata: {r['metadata']}</small></p>"
            html += "<hr>"
        
        return html
    except Exception as e:
        return f"Error in RAG search: {str(e)}"

# Initialize database
# Initialize database
with app.app_context():
    db.create_all()
    
    # Initialize RAG with existing data
    # Note: @app.before_first_request is removed in Flask 3.0+, so we run this directly
    try:
        print("Loading patient data into RAG system...")
        patients = Patient.query.all()
        for patient in patients:
            # We pass db.session but the method technically doesn't use it in the provided code
            # ensuring compatibility just in case
            rag_system.add_patient_data(patient, db.session)
            
            # Load prescriptions
            for rx in patient.prescriptions:
                rag_system.add_prescription(rx)
            
            # Load health metrics
            for metric in patient.health_metrics:
                rag_system.add_health_metrics(metric)
        
        print(f"RAG initialization complete. Loaded {len(patients)} patients")
    except Exception as e:
        print(f"RAG initialization skipped (DB might not be ready): {e}")

if __name__ == '__main__':
    app.run(debug=True,port=8000)
