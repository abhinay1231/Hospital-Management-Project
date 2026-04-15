# rag_system.py
"""
RAG (Retrieval-Augmented Generation) System for Medical Data
This file handles vector storage and semantic search
"""

import os
import pickle
import numpy as np
from datetime import datetime
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

class MedicalRAG:
    def __init__(self, persist_directory="./rag_data"):
        """
        Initialize the RAG system
        """
        print("Initializing RAG system...")
        
        # Create directory for storing vector data
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize the sentence transformer model
        # The warning about HF token is harmless and can be ignored
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Initialize ChromaDB with the NEW PersistentClient (fix for deprecated config)
        self.client = chromadb.PersistentClient(
            path=persist_directory
        )
        
        # Create or get collections (like tables in database)
        self.collections = {}
        collection_names = ['symptoms', 'prescriptions', 'health_metrics', 
                           'similar_cases', 'doctor_notes', 'medical_reports']
        
        for name in collection_names:
            try:
                # Try to get existing collection
                self.collections[name] = self.client.get_collection(name)
                print(f"Loaded existing collection: {name}")
            except:
                # Create new collection if it doesn't exist
                self.collections[name] = self.client.create_collection(name)
                print(f"Created new collection: {name}")
        
        print(f"RAG system ready with {len(collection_names)} collections")
    
    def text_to_vector(self, text):
        """Convert text to vector embedding"""
        return self.encoder.encode(text).tolist()
    
    def add_patient_data(self, patient, db_session):
        """
        Add all patient data to vector database
        Call this when patient profile is updated or new data added
        """
        patient_id = str(patient.id)
        
        # 1. Add symptoms and medical history
        if patient.symptoms:
            symptom_text = f"Patient {patient.name}: Symptoms - {patient.symptoms}"
            vector = self.text_to_vector(symptom_text)
            self.collections['symptoms'].add(
                embeddings=[vector],
                documents=[symptom_text],
                metadatas=[{
                    "patient_id": patient_id,
                    "type": "symptom",
                    "date": str(datetime.now().date())
                }],
                ids=[f"symptom_{patient_id}_{datetime.now().timestamp()}"]
            )
        
        # 2. Add medical history
        if patient.medical_history:
            history_text = f"Patient {patient.name}: Medical History - {patient.medical_history}"
            vector = self.text_to_vector(history_text)
            self.collections['symptoms'].add(
                embeddings=[vector],
                documents=[history_text],
                metadatas=[{
                    "patient_id": patient_id,
                    "type": "medical_history",
                    "date": str(datetime.now().date())
                }],
                ids=[f"history_{patient_id}_{datetime.now().timestamp()}"]
            )
        
        # 3. Add family history
        if patient.family_history:
            family_text = f"Patient {patient.name}: Family History - {patient.family_history}"
            vector = self.text_to_vector(family_text)
            self.collections['symptoms'].add(
                embeddings=[vector],
                documents=[family_text],
                metadatas=[{
                    "patient_id": patient_id,
                    "type": "family_history",
                    "date": str(datetime.now().date())
                }],
                ids=[f"family_{patient_id}_{datetime.now().timestamp()}"]
            )
        
        print(f"Added patient {patient_id} data to RAG")
    
    def add_prescription(self, prescription):
        """Add prescription to vector database"""
        patient_id = str(prescription.patient_id)
        
        rx_text = f"Prescription for patient {patient_id}: {prescription.medicines} | Diagnosis: {prescription.diagnosis} | Notes: {prescription.notes}"
        vector = self.text_to_vector(rx_text)
        
        self.collections['prescriptions'].add(
            embeddings=[vector],
            documents=[rx_text],
            metadatas=[{
                "patient_id": patient_id,
                "doctor_id": str(prescription.doctor_id),
                "date": str(prescription.date_issued.date()),
                "type": "prescription"
            }],
            ids=[f"rx_{prescription.id}_{datetime.now().timestamp()}"]
        )
    
    def add_health_metrics(self, metric):
        """Add health metrics to vector database"""
        patient_id = str(metric.patient_id)
        
        metrics_text = f"""
        Patient {patient_id} Health Metrics:
        BP: {metric.blood_pressure_systolic}/{metric.blood_pressure_diastolic}
        Heart Rate: {metric.heart_rate}
        Blood Sugar: {metric.blood_sugar}
        BMI: {metric.bmi}
        Weight: {metric.weight}
        Date: {metric.recorded_date.date()}
        """
        
        vector = self.text_to_vector(metrics_text)
        
        self.collections['health_metrics'].add(
            embeddings=[vector],
            documents=[metrics_text],
            metadatas=[{
                "patient_id": patient_id,
                "date": str(metric.recorded_date.date()),
                "type": "health_metrics"
            }],
            ids=[f"metric_{metric.id}_{datetime.now().timestamp()}"]
        )
    
    def search_similar(self, query, patient_id=None, collection_name=None, limit=5, similarity_threshold=0.3):
        """
        Search for similar content across all collections with similarity scoring
        
        Args:
            query: The search query (patient question or doctor query)
            patient_id: Filter by specific patient (optional)
            collection_name: Search only specific collection (optional)
            limit: Number of results to return
            similarity_threshold: Maximum distance threshold (lower = more strict)
        
        Returns:
            List of relevant documents with similarity scores
        """
        # Convert query to vector
        query_vector = self.text_to_vector(query)
        
        # Determine which collections to search
        if collection_name:
            collections_to_search = [self.collections[collection_name]]
        else:
            collections_to_search = self.collections.values()
        
        # Search each collection
        all_results = []
        for collection in collections_to_search:
            try:
                # Add filter if patient_id provided
                where_filter = {"patient_id": patient_id} if patient_id else None
                
                # Get MORE results with distances
                results = collection.query(
                    query_embeddings=[query_vector],
                    n_results=limit * 3,  # Get more to filter later
                    where=where_filter,
                    include=["documents", "metadatas", "distances"]  # IMPORTANT: Add distances
                )
                
                if results['documents'] and results['documents'][0]:
                    # Now we have distances too!
                    documents = results['documents'][0]
                    metadatas = results['metadatas'][0]
                    distances = results['distances'][0]  # Lower = more similar
                    
                    # Pair them up and filter by threshold
                    for doc, metadata, distance in zip(documents, metadatas, distances):
                        if distance <= similarity_threshold:  # Only include relevant ones
                            # Calculate similarity score (1 - distance) for easier understanding
                            similarity_score = 1 - min(distance, 1.0)  # Cap at 1.0
                            
                            all_results.append({
                                'text': doc,
                                'metadata': metadata,
                                'distance': distance,  # Raw Chroma distance
                                'similarity_score': similarity_score,  # 0-1 scale, higher = better
                                'relevance': self._get_relevance_label(similarity_score)  # high/medium/low
                            })
            except Exception as e:
                print(f"Error searching collection {collection.name}: {e}")
                continue
        
        # Sort by similarity score (highest first)
        all_results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Return top results
        return all_results[:limit]

    def _get_relevance_label(self, similarity_score):
        """Convert similarity score to relevance label"""
        if similarity_score > 0.8:
            return 'high'
        elif similarity_score > 0.6:
            return 'medium'
        else:
            return 'low'
    
    def get_patient_context(self, patient_id, query, similarity_threshold=0.3):
        """
        Get comprehensive context for a patient based on a query
        Now includes similarity scores and better filtering
        """
        # Search across all collections with scoring
        symptoms = self.search_similar(
            query, patient_id, 'symptoms', 
            limit=3, similarity_threshold=similarity_threshold
        )
        prescriptions = self.search_similar(
            query, patient_id, 'prescriptions', 
            limit=3, similarity_threshold=similarity_threshold
        )
        metrics = self.search_similar(
            query, patient_id, 'health_metrics', 
            limit=2, similarity_threshold=similarity_threshold
        )
        
        # Format the context with scores
        context = "RELEVANT PATIENT HISTORY:\n"
        context += "=" * 50 + "\n\n"
        
        # Track if we found anything
        has_content = False
        
        if symptoms:
            has_content = True
            context += "🔍 SYMPTOMS & HISTORY (with relevance scores):\n"
            context += "-" * 40 + "\n"
            for s in symptoms:
                # Show relevance visually
                relevance_icon = "🟢" if s['relevance'] == 'high' else "🟡" if s['relevance'] == 'medium' else "⚪"
                context += f"{relevance_icon} [Score: {s['similarity_score']:.2f}] {s['text'][:200]}\n"
            context += "\n"
        
        if prescriptions:
            has_content = True
            context += "💊 PREVIOUS PRESCRIPTIONS:\n"
            context += "-" * 40 + "\n"
            for p in prescriptions:
                relevance_icon = "🟢" if p['relevance'] == 'high' else "🟡" if p['relevance'] == 'medium' else "⚪"
                context += f"{relevance_icon} [Score: {p['similarity_score']:.2f}] {p['text'][:200]}\n"
            context += "\n"
        
        if metrics:
            has_content = True
            context += "📊 RECENT HEALTH METRICS:\n"
            context += "-" * 40 + "\n"
            for m in metrics:
                relevance_icon = "🟢" if m['relevance'] == 'high' else "🟡" if m['relevance'] == 'medium' else "⚪"
                context += f"{relevance_icon} [Score: {m['similarity_score']:.2f}] {m['text'][:200]}\n"
            context += "\n"
        
        if not has_content:
            context += "No highly relevant patient records found for this query.\n"
        
        # Add summary statistics
        context += "=" * 50 + "\n"
        context += f"📊 Summary: Found {len(symptoms)} symptom records, {len(prescriptions)} prescriptions, {len(metrics)} health metrics\n"
        context += f"   (Filtered with similarity threshold: {similarity_threshold})\n"
        
        return context

    def get_similarity_stats(self, query, patient_id=None):
        """
        Helper method to analyze similarity scores for a query
        Useful for finding the right threshold
        """
        query_vector = self.text_to_vector(query)
        all_distances = []
        
        for collection_name, collection in self.collections.items():
            try:
                where_filter = {"patient_id": patient_id} if patient_id else None
                results = collection.query(
                    query_embeddings=[query_vector],
                    n_results=20,
                    where=where_filter,
                    include=["distances"]
                )
                
                if results['distances'] and results['distances'][0]:
                    all_distances.extend(results['distances'][0])
            except:
                continue
        
        if all_distances:
            import numpy as np
            stats = {
                'mean': np.mean(all_distances),
                'median': np.median(all_distances),
                'std': np.std(all_distances),
                'min': min(all_distances),
                'max': max(all_distances),
                'suggested_threshold': np.percentile(all_distances, 75)  # 75th percentile
            }
            return stats
        return None

# Create a global instance
rag_system = MedicalRAG()
