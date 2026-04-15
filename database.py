# database.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'patient' or 'doctor'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    contact = db.Column(db.String(20))
    address = db.Column(db.Text)
    family_history = db.Column(db.Text)
    symptoms = db.Column(db.Text)
    diet = db.Column(db.Text)
    lifestyle = db.Column(db.Text)
    medical_history = db.Column(db.Text)
    profile_completed = db.Column(db.Boolean, default=False)
    priority_level = db.Column(db.String(20), default='normal')  # critical, high, medium, normal
    disease_category = db.Column(db.String(100))
    tags = db.Column(db.Text)  # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='patient_profile')

class Doctor(db.Model):
    __tablename__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    specialization = db.Column(db.String(100))
    qualification = db.Column(db.String(200))
    experience = db.Column(db.Integer)
    contact = db.Column(db.String(20))
    consultation_duration = db.Column(db.Integer, default=30)  # minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='doctor_profile')

class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    appointment_date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, completed, cancelled
    reason = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='appointments')
    doctor = db.relationship('Doctor', backref='appointments')

class DoctorSchedule(db.Model):
    __tablename__ = 'doctor_schedules'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    
    doctor = db.relationship('Doctor', backref='schedules')

class BlockedSlot(db.Model):
    __tablename__ = 'blocked_slots'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    blocked_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(10))
    end_time = db.Column(db.String(10))
    reason = db.Column(db.String(200))
    
    doctor = db.relationship('Doctor', backref='blocked_slots')

class Prescription(db.Model):
    __tablename__ = 'prescriptions'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    medicines = db.Column(db.Text, nullable=False)  # JSON string
    diagnosis = db.Column(db.Text)
    notes = db.Column(db.Text)
    date_issued = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='prescriptions')
    doctor = db.relationship('Doctor', backref='prescriptions')

class HealthMetric(db.Model):
    __tablename__ = 'health_metrics'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    blood_pressure_systolic = db.Column(db.Integer)
    blood_pressure_diastolic = db.Column(db.Integer)
    heart_rate = db.Column(db.Integer)
    blood_sugar = db.Column(db.Float)
    weight = db.Column(db.Float)
    height = db.Column(db.Float)
    bmi = db.Column(db.Float)
    temperature = db.Column(db.Float)
    oxygen_saturation = db.Column(db.Integer)
    recorded_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='health_metrics')

class MedicalReport(db.Model):
    __tablename__ = 'medical_reports'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    report_type = db.Column(db.String(100))  # lab_test, imaging, discharge_summary
    title = db.Column(db.String(200))
    file_path = db.Column(db.String(500))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='medical_reports')
    doctor = db.relationship('Doctor', backref='medical_reports')

class ChatHistory(db.Model):
    __tablename__ = 'chat_history'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='chat_history')

class DoctorChat(db.Model):
    __tablename__ = 'doctor_chats'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    query_type = db.Column(db.String(50), default='general')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    doctor = db.relationship('Doctor', backref='chat_history')
    patient = db.relationship('Patient', backref='doctor_chats')


class DoctorNote(db.Model):
    __tablename__ = 'doctor_notes'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    note_content = db.Column(db.Text, nullable=False)
    is_private = db.Column(db.Boolean, default=True)
    note_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='doctor_notes')
    doctor = db.relationship('Doctor', backref='notes')

class Feedback(db.Model):
    __tablename__ = 'feedback'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comments = db.Column(db.Text)
    feedback_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    patient = db.relationship('Patient', backref='feedback')
    doctor = db.relationship('Doctor', backref='feedback')
    appointment = db.relationship('Appointment', backref='feedback')

class EmailLog(db.Model):
    __tablename__ = 'email_logs'
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    subject = db.Column(db.String(200))
    content = db.Column(db.Text)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    doctor = db.relationship('Doctor', backref='email_logs')
    patient = db.relationship('Patient', backref='email_logs')