// static/js/doctor.js

// Doctor-specific JavaScript functions

// Tab Management
class TabManager {
    constructor() {
        this.initTabs();
    }
    
    initTabs() {
        const tabButtons = document.querySelectorAll('.tab-button');
        const tabContents = document.querySelectorAll('.tab-content');
        
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tabName = button.getAttribute('data-tab');
                this.showTab(tabName, button);
            });
        });
    }
    
    showTab(tabName, clickedButton) {
        // Hide all tabs
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.classList.add('hidden');
        });
        
        // Remove active class from all buttons
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('border-blue-600', 'text-blue-600');
            btn.classList.add('border-transparent', 'text-gray-500');
        });
        
        // Show selected tab
        const selectedTab = document.getElementById(tabName + '-tab');
        if (selectedTab) {
            selectedTab.classList.remove('hidden');
        }
        
        // Add active class to clicked button
        if (clickedButton) {
            clickedButton.classList.remove('border-transparent', 'text-gray-500');
            clickedButton.classList.add('border-blue-600', 'text-blue-600');
        }
    }
}

// AI Assistant
class AIAssistant {
    constructor() {
        this.chatContainer = document.getElementById('chatContainer');
        this.queryInput = document.getElementById('queryInput');
        this.aiForm = document.getElementById('aiForm');
        this.currentMode = document.getElementById('currentMode');
        this.queryType = 'diagnosis';
        
        if (this.aiForm) {
            this.init();
        }
    }
    
    init() {
        this.aiForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.addWelcomeMessage();
    }
    
    addWelcomeMessage() {
        if (this.chatContainer && this.chatContainer.children.length === 0) {
            this.addMessage('Hello Doctor! I\'m your AI medical assistant. How can I help you today?', 'ai');
        }
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        const query = this.queryInput.value.trim();
        
        if (!query) return;
        
        this.addMessage(query, 'user');
        this.queryInput.value = '';
        this.queryInput.disabled = true;
        
        const loadingId = this.addMessage('Analyzing...', 'ai', true);
        
        try {
            const response = await fetch(window.location.href, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    type: this.queryType,
                    content: query
                })
            });
            
            const data = await response.json();
            
            document.getElementById(loadingId)?.remove();
            this.addMessage(data.response, 'ai');
        } catch (error) {
            document.getElementById(loadingId)?.remove();
            this.addMessage('Sorry, I encountered an error. Please try again.', 'ai');
        } finally {
            this.queryInput.disabled = false;
            this.queryInput.focus();
        }
    }
    
    addMessage(text, sender, isLoading = false) {
        const messageId = 'msg-' + Date.now();
        const messageDiv = document.createElement('div');
        messageDiv.id = messageId;
        messageDiv.className = 'flex items-start space-x-3';
        
        if (sender === 'ai') {
            messageDiv.innerHTML = `
                <div class="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-robot text-purple-600"></i>
                </div>
                <div class="flex-1 bg-gray-100 rounded-lg p-4">
                    <p class="text-gray-900 whitespace-pre-wrap">${isLoading ? '<i class="fas fa-spinner fa-spin"></i> ' + this.escapeHtml(text) : this.escapeHtml(text)}</p>
                </div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="flex-1"></div>
                <div class="bg-blue-600 text-white rounded-lg p-4 max-w-xl">
                    <p class="whitespace-pre-wrap">${this.escapeHtml(text)}</p>
                </div>
                <div class="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                    <i class="fas fa-user-md text-blue-600"></i>
                </div>
            `;
        }
        
        if (this.chatContainer) {
            this.chatContainer.appendChild(messageDiv);
            this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
        }
        
        return messageId;
    }
    
    setQueryType(type) {
        this.queryType = type;
        const modes = {
            'diagnosis': 'Diagnosis',
            'treatment': 'Treatment Recommendations',
            'research': 'Medical Research',
            'general': 'General Query'
        };
        if (this.currentMode) {
            this.currentMode.textContent = modes[type];
        }
    }
    
    clearChat() {
        if (this.chatContainer) {
            this.chatContainer.innerHTML = '';
            this.addWelcomeMessage();
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Schedule Management
class ScheduleManager {
    constructor() {
        this.scheduleForm = document.getElementById('scheduleForm');
        this.blockSlotForm = document.getElementById('blockSlotForm');
        
        if (this.scheduleForm) {
            this.initSchedule();
        }
        
        if (this.blockSlotForm) {
            this.initBlockSlot();
        }
    }
    
    initSchedule() {
        this.scheduleForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.saveSchedule();
        });
    }
    
    initBlockSlot() {
        this.blockSlotForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.blockSlot();
        });
    }
    
    async saveSchedule() {
        const formData = new FormData(this.scheduleForm);
        const schedules = [];
        
        for (let i = 0; i < 7; i++) {
            if (formData.get(`available_${i}`)) {
                schedules.push({
                    day: i,
                    start_time: formData.get(`start_${i}`),
                    end_time: formData.get(`end_${i}`)
                });
            }
        }
        
        try {
            const response = await fetch('/doctor/schedule', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({schedules})
            });
            
            if (response.ok) {
                window.utils.showToast('Schedule saved successfully!', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                throw new Error('Failed to save schedule');
            }
        } catch (error) {
            window.utils.showToast('Error saving schedule', 'error');
        }
    }
    
    async blockSlot() {
        const formData = new FormData(this.blockSlotForm);
        const data = Object.fromEntries(formData.entries());
        
        try {
            const response = await fetch('/doctor/block-slot', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            if (response.ok) {
                window.utils.showToast('Time slot blocked successfully!', 'success');
                setTimeout(() => location.reload(), 1000);
            } else {
                throw new Error('Failed to block slot');
            }
        } catch (error) {
            window.utils.showToast('Error blocking time slot', 'error');
        }
    }
}

// Analytics Charts
class AnalyticsCharts {
    constructor() {
        this.ageChart = document.getElementById('ageChart');
        this.diseaseChart = document.getElementById('diseaseChart');
        
        if (this.ageChart) {
            this.initCharts();
        }
    }
    
    initCharts() {
        // Charts are initialized in the template with server-side data
        // This class can be extended for interactive chart updates
    }
}

// Patient Search and Filter
class PatientFilter {
    constructor() {
        this.searchInput = document.querySelector('input[name="search"]');
        this.filterForm = document.querySelector('form');
        
        if (this.searchInput) {
            this.initSearch();
        }
    }
    
    initSearch() {
        const debouncedSearch = window.utils.debounce(() => {
            if (this.filterForm) {
                this.filterForm.submit();
            }
        }, 500);
        
        this.searchInput.addEventListener('input', debouncedSearch);
    }
}

// Modal Management
function openEmailModal() {
    window.utils.openModal('emailModal');
}

function closeEmailModal() {
    window.utils.closeModal('emailModal');
}

function openPrescriptionModal() {
    window.utils.openModal('prescriptionModal');
}

function closePrescriptionModal() {
    window.utils.closeModal('prescriptionModal');
}

function openScheduleModal() {
    window.utils.openModal('scheduleModal');
}

function closeScheduleModal() {
    window.utils.closeModal('scheduleModal');
}

function openBlockSlotModal() {
    window.utils.openModal('blockSlotModal');
}

function closeBlockSlotModal() {
    window.utils.closeModal('blockSlotModal');
}

// AI Assistant Query Type
function setQueryType(type) {
    if (window.aiAssistant) {
        window.aiAssistant.setQueryType(type);
    }
    
    // Update button styles
    document.querySelectorAll('.query-type-btn').forEach(btn => {
        btn.classList.remove('bg-blue-50', 'text-blue-700');
        btn.classList.add('bg-gray-50', 'text-gray-700');
    });
    event.target.classList.remove('bg-gray-50', 'text-gray-700');
    event.target.classList.add('bg-blue-50', 'text-blue-700');
}

function clearChat() {
    if (window.aiAssistant) {
        window.aiAssistant.clearChat();
    }
}

function useExample(element) {
    const text = element.querySelector('.text-xs').textContent;
    const input = document.getElementById('queryInput');
    if (input) {
        input.value = text;
        input.focus();
    }
}

// Initialize all doctor features
document.addEventListener('DOMContentLoaded', function() {
    new TabManager();
    window.aiAssistant = new AIAssistant();
    new ScheduleManager();
    new AnalyticsCharts();
    new PatientFilter();
});

// Export for use in templates
window.doctorUtils = {
    openEmailModal,
    closeEmailModal,
    openPrescriptionModal,
    closePrescriptionModal,
    openScheduleModal,
    closeScheduleModal,
    openBlockSlotModal,
    closeBlockSlotModal,
    setQueryType,
    clearChat,
    useExample
};