// static/js/patient.js

// Patient-specific JavaScript functions

// Chat functionality
class ChatManager {
    constructor() {
        this.messageContainer = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.chatForm = document.getElementById('chatForm');
        
        if (this.chatForm) {
            this.initChat();
        }
    }
    
    initChat() {
        this.chatForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.scrollToBottom();
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        const message = this.messageInput.value.trim();
        
        if (!message) return;
        
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.messageInput.disabled = true;
        
        const loadingId = this.addMessage('Thinking...', 'ai', true);
        
        try {
            const response = await fetch(window.location.href, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: message})
            });
            
            const data = await response.json();
            
            document.getElementById(loadingId)?.remove();
            this.addMessage(data.response, 'ai');
        } catch (error) {
            document.getElementById(loadingId)?.remove();
            this.addMessage('Sorry, something went wrong. Please try again.', 'ai');
        } finally {
            this.messageInput.disabled = false;
            this.messageInput.focus();
        }
    }
    
    addMessage(text, sender, isLoading = false) {
        const messageId = 'msg-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.id = messageId;
        messageDiv.className = sender === 'user' ? 'flex justify-end' : 'flex justify-start';
        
        const time = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        
        if (sender === 'user') {
            messageDiv.innerHTML = `
                <div class="max-w-xs lg:max-w-md">
                    <div class="bg-blue-600 text-white rounded-lg rounded-tr-none px-4 py-3 shadow">
                        <p class="text-sm">${this.escapeHtml(text)}</p>
                    </div>
                    <p class="text-xs text-gray-500 mt-1 text-right">${time}</p>
                </div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="max-w-xs lg:max-w-md">
                    <div class="bg-white border border-gray-200 rounded-lg rounded-tl-none px-4 py-3 shadow">
                        <p class="text-sm text-gray-900 whitespace-pre-wrap">${isLoading ? '<i class="fas fa-spinner fa-spin"></i> ' + this.escapeHtml(text) : this.escapeHtml(text)}</p>
                    </div>
                    <p class="text-xs text-gray-500 mt-1">${time}</p>
                </div>
            `;
        }
        
        if (this.messageContainer) {
            this.messageContainer.appendChild(messageDiv);
            this.scrollToBottom();
        }
        
        return messageId;
    }
    
    scrollToBottom() {
        if (this.messageContainer) {
            this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Appointment booking
class AppointmentBooking {
    constructor() {
        this.doctorSelect = document.getElementById('doctorSelect');
        this.dateInput = document.getElementById('appointmentDate');
        this.timeSlot = document.getElementById('timeSlot');
        
        if (this.doctorSelect && this.dateInput) {
            this.init();
        }
    }
    
    init() {
        this.doctorSelect.addEventListener('change', () => this.loadSlots());
        this.dateInput.addEventListener('change', () => this.loadSlots());
        
        // Set minimum date to today
        const today = new Date().toISOString().split('T')[0];
        this.dateInput.setAttribute('min', today);
    }
    
    async loadSlots() {
        const doctorId = this.doctorSelect.value;
        const date = this.dateInput.value;
        
        if (!doctorId || !date) {
            this.timeSlot.innerHTML = '<option value="">Select date and doctor first</option>';
            return;
        }
        
        this.timeSlot.innerHTML = '<option value="">Loading slots...</option>';
        
        try {
            const response = await fetch(`/api/available-slots?doctor_id=${doctorId}&date=${date}`);
            const data = await response.json();
            
            if (data.slots && data.slots.length > 0) {
                this.timeSlot.innerHTML = '<option value="">Select a time slot</option>';
                data.slots.forEach(slot => {
                    const option = document.createElement('option');
                    option.value = slot;
                    option.textContent = window.utils.formatTime(slot);
                    this.timeSlot.appendChild(option);
                });
            } else {
                this.timeSlot.innerHTML = '<option value="">No slots available</option>';
            }
        } catch (error) {
            this.timeSlot.innerHTML = '<option value="">Error loading slots</option>';
            window.utils.showToast('Failed to load available slots', 'error');
        }
    }
}

// Health metrics chart
class HealthMetricsChart {
    constructor() {
        this.chartElement = document.getElementById('healthChart');
        if (this.chartElement) {
            this.loadChartData();
        }
    }
    
    async loadChartData() {
        try {
            const response = await fetch('/api/health-metrics-data?days=30');
            const data = await response.json();
            
            const ctx = this.chartElement.getContext('2d');
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.dates,
                    datasets: [
                        {
                            label: 'Weight (kg)',
                            data: data.weight,
                            borderColor: '#3B82F6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            tension: 0.4,
                            fill: true
                        },
                        {
                            label: 'BMI',
                            data: data.bmi,
                            borderColor: '#10B981',
                            backgroundColor: 'rgba(16, 185, 129, 0.1)',
                            tension: 0.4,
                            fill: true
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'top'
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)'
                            }
                        },
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Error loading chart data:', error);
        }
    }
}

// BMI Calculator
class BMICalculator {
    constructor() {
        this.weightInput = document.querySelector('input[name="weight"]');
        this.heightInput = document.querySelector('input[name="height"]');
        
        if (this.weightInput && this.heightInput) {
            this.init();
        }
    }
    
    init() {
        this.weightInput.addEventListener('input', () => this.calculateBMI());
        this.heightInput.addEventListener('input', () => this.calculateBMI());
    }
    
    calculateBMI() {
        const weight = parseFloat(this.weightInput.value);
        const height = parseFloat(this.heightInput.value);
        
        if (weight && height && height > 0) {
            const bmi = weight / Math.pow(height / 100, 2);
            const bmiValue = bmi.toFixed(2);
            
            let category = '';
            let color = '';
            
            if (bmi < 18.5) {
                category = 'Underweight';
                color = 'text-yellow-600';
            } else if (bmi < 25) {
                category = 'Normal';
                color = 'text-green-600';
            } else if (bmi < 30) {
                category = 'Overweight';
                color = 'text-orange-600';
            } else {
                category = 'Obese';
                color = 'text-red-600';
            }
            
            const resultDiv = document.getElementById('bmiResult');
            if (resultDiv) {
                resultDiv.innerHTML = `
                    <div class="mt-4 p-4 bg-blue-50 rounded-lg">
                        <p class="text-sm text-gray-700">Your BMI: <span class="font-bold text-lg">${bmiValue}</span></p>
                        <p class="text-sm ${color} font-semibold">Category: ${category}</p>
                    </div>
                `;
            }
        }
    }
}

// File upload with preview
class FileUploadPreview {
    constructor() {
        this.fileInputs = document.querySelectorAll('input[type="file"]');
        this.init();
    }
    
    init() {
        this.fileInputs.forEach(input => {
            input.addEventListener('change', (e) => this.handleFileSelect(e));
        });
    }
    
    handleFileSelect(event) {
        const input = event.target;
        const file = input.files[0];
        
        if (file) {
            const preview = document.createElement('div');
            preview.className = 'mt-2 p-3 bg-gray-100 rounded-lg flex items-center justify-between';
            preview.innerHTML = `
                <div class="flex items-center">
                    <i class="fas fa-file text-blue-600 text-2xl mr-3"></i>
                    <div>
                        <p class="text-sm font-medium text-gray-900">${file.name}</p>
                        <p class="text-xs text-gray-500">${(file.size / 1024).toFixed(2)} KB</p>
                    </div>
                </div>
                <button type="button" onclick="this.parentElement.remove(); document.querySelector('input[type=file]').value = '';" class="text-red-600 hover:text-red-800">
                    <i class="fas fa-times"></i>
                </button>
            `;
            
            const existingPreview = input.parentElement.querySelector('.file-preview');
            if (existingPreview) {
                existingPreview.remove();
            }
            
            preview.classList.add('file-preview');
            input.parentElement.appendChild(preview);
        }
    }
}

// Initialize all patient features
document.addEventListener('DOMContentLoaded', function() {
    new ChatManager();
    new AppointmentBooking();
    new HealthMetricsChart();
    new BMICalculator();
    new FileUploadPreview();
});

// Quick message function for chat
function sendQuickMessage(message) {
    const input = document.getElementById('messageInput');
    const form = document.getElementById('chatForm');
    
    if (input && form) {
        input.value = message;
        form.dispatchEvent(new Event('submit'));
    }
}

// Export for use in templates
window.patientUtils = {
    sendQuickMessage
};