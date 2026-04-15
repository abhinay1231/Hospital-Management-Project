# intent_classifier.py
"""
Medical Intent Classifier for Doctor Queries
Replaces keyword-based intent detection with ML-based classification
"""

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import os

class MedicalIntentClassifier:
    def __init__(self, model_path='intent_model.pkl', vectorizer_path='vectorizer.pkl'):
        """Initialize the intent classifier"""
        self.model_path = model_path
        self.vectorizer_path = vectorizer_path
        self.classifier = None
        self.vectorizer = None
        
        # Define intent categories
        self.intents = [
            'SYMPTOM_QUERY',      # Questions about symptoms
            'VITALS_QUERY',        # Questions about vital signs
            'HISTORY_QUERY',       # Questions about medical history
            'COMPARISON_QUERY',    # Compare with previous visits
            'TREATMENT_QUERY',     # Questions about treatments
            'SIMILAR_CASES_QUERY', # Find similar patients
            'RESEARCH_QUERY',      # Medical research questions
            'APPOINTMENT_QUERY',   # Questions about appointments
            'GENERAL_QUERY'        # General questions
        ]
        
        # Try to load existing model
        self.load_model()
    
    def load_model(self):
        """Load trained model if exists"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.vectorizer_path):
                self.classifier = joblib.load(self.model_path)
                self.vectorizer = joblib.load(self.vectorizer_path)
                print("✅ Loaded existing intent classifier model")
                return True
        except Exception as e:
            print(f"Could not load model: {e}")
        return False
    
    def train(self, force_retrain=False):
        """Train the classifier with medical queries"""
        if self.classifier is not None and not force_retrain:
            return True
            
        print("🔄 Training intent classifier...")
        
        # Training data: (query, intent)
        training_data = [
            # ===== SYMPTOM QUERIES =====
            ("What symptoms is the patient experiencing?", "SYMPTOM_QUERY"),
            ("What's bothering him?", "SYMPTOM_QUERY"),
            ("Any health issues?", "SYMPTOM_QUERY"),
            ("What complaints does he have?", "SYMPTOM_QUERY"),
            ("Is he in pain?", "SYMPTOM_QUERY"),
            ("Does he have fever?", "SYMPTOM_QUERY"),
            ("What are the presenting complaints?", "SYMPTOM_QUERY"),
            ("Tell me about his symptoms", "SYMPTOM_QUERY"),
            ("What symptoms does she have?", "SYMPTOM_QUERY"),
            ("Describe the symptoms", "SYMPTOM_QUERY"),
            ("What's wrong with the patient?", "SYMPTOM_QUERY"),
            ("Current symptoms?", "SYMPTOM_QUERY"),
            ("Any pain or discomfort?", "SYMPTOM_QUERY"),
            ("What are the main symptoms?", "SYMPTOM_QUERY"),
            ("Symptoms since when?", "SYMPTOM_QUERY"),
            
            # ===== VITALS QUERIES =====
            ("What are the vital signs?", "VITALS_QUERY"),
            ("Blood pressure reading?", "VITALS_QUERY"),
            ("Temperature and heart rate?", "VITALS_QUERY"),
            ("Check vitals", "VITALS_QUERY"),
            ("What's his BP?", "VITALS_QUERY"),
            ("Oxygen saturation?", "VITALS_QUERY"),
            ("Show me the vitals", "VITALS_QUERY"),
            ("Latest health metrics", "VITALS_QUERY"),
            ("What's the blood pressure?", "VITALS_QUERY"),
            ("Heart rate?", "VITALS_QUERY"),
            ("BMI reading?", "VITALS_QUERY"),
            ("Blood sugar levels?", "VITALS_QUERY"),
            ("Recent vitals", "VITALS_QUERY"),
            ("How are his vitals?", "VITALS_QUERY"),
            ("Any abnormal vitals?", "VITALS_QUERY"),
            
            # ===== HISTORY QUERIES =====
            ("Past medical history?", "HISTORY_QUERY"),
            ("Any previous conditions?", "HISTORY_QUERY"),
            ("What surgeries has he had?", "HISTORY_QUERY"),
            ("Family history of heart disease?", "HISTORY_QUERY"),
            ("Previous admissions?", "HISTORY_QUERY"),
            ("Medical background?", "HISTORY_QUERY"),
            ("Tell me about his history", "HISTORY_QUERY"),
            ("Any chronic conditions?", "HISTORY_QUERY"),
            ("Past surgeries?", "HISTORY_QUERY"),
            ("Family medical history?", "HISTORY_QUERY"),
            ("Previous diagnoses?", "HISTORY_QUERY"),
            ("What's in his medical history?", "HISTORY_QUERY"),
            ("Any allergies?", "HISTORY_QUERY"),
            ("Previous medications?", "HISTORY_QUERY"),
            ("History of hypertension?", "HISTORY_QUERY"),
            
            # ===== COMPARISON QUERIES =====
            ("How is this different from last time?", "COMPARISON_QUERY"),
            ("Compare with previous visit", "COMPARISON_QUERY"),
            ("Is this worse than before?", "COMPARISON_QUERY"),
            ("Change in condition?", "COMPARISON_QUERY"),
            ("Progress since last visit?", "COMPARISON_QUERY"),
            ("Has it improved?", "COMPARISON_QUERY"),
            ("Compare to last month", "COMPARISON_QUERY"),
            ("Any deterioration?", "COMPARISON_QUERY"),
            ("How does this compare to before?", "COMPARISON_QUERY"),
            ("Is it getting better?", "COMPARISON_QUERY"),
            ("Trend of symptoms?", "COMPARISON_QUERY"),
            ("Worse or better?", "COMPARISON_QUERY"),
            ("Compare with previous readings", "COMPARISON_QUERY"),
            ("Change from last time?", "COMPARISON_QUERY"),
            ("Any improvement?", "COMPARISON_QUERY"),
            
            # ===== TREATMENT QUERIES =====
            ("What treatments have been tried?", "TREATMENT_QUERY"),
            ("Previous prescriptions?", "TREATMENT_QUERY"),
            ("What medications is he on?", "TREATMENT_QUERY"),
            ("Has he tried any medicines?", "TREATMENT_QUERY"),
            ("What was prescribed last time?", "TREATMENT_QUERY"),
            ("Current medications?", "TREATMENT_QUERY"),
            ("What treatments worked?", "TREATMENT_QUERY"),
            ("Any side effects?", "TREATMENT_QUERY"),
            ("Medication history?", "TREATMENT_QUERY"),
            ("What was the last prescription?", "TREATMENT_QUERY"),
            ("Is he on any meds?", "TREATMENT_QUERY"),
            ("Treatment plan?", "TREATMENT_QUERY"),
            ("What drugs is he taking?", "TREATMENT_QUERY"),
            ("Dosage information?", "TREATMENT_QUERY"),
            ("Any allergies to meds?", "TREATMENT_QUERY"),
            
            # ===== SIMILAR CASES QUERIES =====
            ("Are there similar patients?", "SIMILAR_CASES_QUERY"),
            ("Any other cases like this?", "SIMILAR_CASES_QUERY"),
            ("Similar cases in database?", "SIMILAR_CASES_QUERY"),
            ("Show me similar patients", "SIMILAR_CASES_QUERY"),
            ("Patients with same symptoms?", "SIMILAR_CASES_QUERY"),
            ("Any similar presentations?", "SIMILAR_CASES_QUERY"),
            ("What worked for similar patients?", "SIMILAR_CASES_QUERY"),
            ("Find similar cases", "SIMILAR_CASES_QUERY"),
            ("Other patients like this?", "SIMILAR_CASES_QUERY"),
            ("Similar symptom patients?", "SIMILAR_CASES_QUERY"),
            
            # ===== RESEARCH QUERIES =====
            ("Latest treatments for this condition?", "RESEARCH_QUERY"),
            ("What do guidelines recommend?", "RESEARCH_QUERY"),
            ("Recent studies on this?", "RESEARCH_QUERY"),
            ("Standard of care?", "RESEARCH_QUERY"),
            ("Evidence-based treatments?", "RESEARCH_QUERY"),
            ("Latest research on migraine", "RESEARCH_QUERY"),
            ("What's new in treatment?", "RESEARCH_QUERY"),
            ("Clinical guidelines?", "RESEARCH_QUERY"),
            ("Recent papers on this?", "RESEARCH_QUERY"),
            ("Any new drugs?", "RESEARCH_QUERY"),
            ("Research updates?", "RESEARCH_QUERY"),
            ("Latest evidence?", "RESEARCH_QUERY"),
            
            # ===== APPOINTMENT QUERIES =====
            ("When is the next appointment?", "APPOINTMENT_QUERY"),
            ("Upcoming appointments?", "APPOINTMENT_QUERY"),
            ("Has he visited before?", "APPOINTMENT_QUERY"),
            ("Previous visits?", "APPOINTMENT_QUERY"),
            ("Appointment history?", "APPOINTMENT_QUERY"),
            ("When was last visit?", "APPOINTMENT_QUERY"),
            ("Any scheduled appointments?", "APPOINTMENT_QUERY"),
            ("Show appointments", "APPOINTMENT_QUERY"),
            ("Visit history?", "APPOINTMENT_QUERY"),
            ("Last time seen?", "APPOINTMENT_QUERY"),
            
            # ===== GENERAL QUERIES =====
            ("Tell me about this patient", "GENERAL_QUERY"),
            ("Give me a summary", "GENERAL_QUERY"),
            ("What do you think?", "GENERAL_QUERY"),
            ("Any concerns?", "GENERAL_QUERY"),
            ("How is the patient?", "GENERAL_QUERY"),
            ("What's your assessment?", "GENERAL_QUERY"),
            ("Any red flags?", "GENERAL_QUERY"),
            ("What should I know?", "GENERAL_QUERY"),
            ("Patient overview", "GENERAL_QUERY"),
            ("Quick update?", "GENERAL_QUERY"),
        ]
        
        # Separate queries and intents
        queries = [item[0] for item in training_data]
        intent_labels = [item[1] for item in training_data]
        
        # Create and fit vectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=2000,
            ngram_range=(1, 3),
            stop_words='english',
            lowercase=True
        )
        
        X = self.vectorizer.fit_transform(queries)
        
        # Train classifier
        self.classifier = LogisticRegression(
            max_iter=1000,
            C=1.5,
            class_weight='balanced',
            random_state=42
        )
        
        self.classifier.fit(X, intent_labels)
        
        # Save model
        joblib.dump(self.classifier, self.model_path)
        joblib.dump(self.vectorizer, self.vectorizer_path)
        
        print(f"✅ Intent classifier trained with {len(queries)} examples")
        
        # Test accuracy
        predictions = self.classifier.predict(X)
        accuracy = np.mean(predictions == intent_labels)
        print(f"   Training accuracy: {accuracy:.2%}")
        
        return True
    
    def predict_intent(self, query, return_probabilities=False):
        """
        Predict the intent of a medical query
        
        Args:
            query: The doctor's query text
            return_probabilities: If True, return all intent probabilities
            
        Returns:
            Intent string or (intent, probabilities dict)
        """
        if self.classifier is None or self.vectorizer is None:
            if not self.load_model():
                # Train if no model exists
                self.train()
        
        # Vectorize the query
        query_vec = self.vectorizer.transform([query])
        
        # Get prediction
        intent = self.classifier.predict(query_vec)[0]
        
        if return_probabilities:
            # Get probability scores for all intents
            proba = self.classifier.predict_proba(query_vec)[0]
            probabilities = dict(zip(self.classifier.classes_, proba))
            return intent, probabilities
        
        return intent
    
    def get_intent_confidence(self, query):
        """Get confidence score for the predicted intent"""
        intent, probs = self.predict_intent(query, return_probabilities=True)
        return intent, probs[intent]
    
    def get_all_probabilities(self, query):
        """Get probability scores for all intents"""
        _, probs = self.predict_intent(query, return_probabilities=True)
        return probs
    
    def get_intent_description(self, intent):
        """Get a human-readable description of an intent"""
        descriptions = {
            'SYMPTOM_QUERY': "🔍 Questions about symptoms",
            'VITALS_QUERY': "📊 Vital signs and health metrics",
            'HISTORY_QUERY': "📜 Medical history",
            'COMPARISON_QUERY': "🔄 Comparing with previous visits",
            'TREATMENT_QUERY': "💊 Medications and treatments",
            'SIMILAR_CASES_QUERY': "👥 Finding similar patients",
            'RESEARCH_QUERY': "📚 Medical research and guidelines",
            'APPOINTMENT_QUERY': "📅 Appointments and visits",
            'GENERAL_QUERY': "💬 General questions"
        }
        return descriptions.get(intent, intent)

# Create global instance
intent_classifier = MedicalIntentClassifier()

# Train on startup
intent_classifier.train()
