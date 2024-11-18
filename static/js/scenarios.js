document.addEventListener('DOMContentLoaded', function() {
    const categoryFilter = document.getElementById('categoryFilter');
    const difficultyFilter = document.getElementById('difficultyFilter');
    const durationFilter = document.getElementById('durationFilter');
    const scenariosList = document.getElementById('scenariosList');
    const scenarioCards = document.querySelectorAll('.scenario-card');
    const newScenarioForm = document.getElementById('newScenarioForm');
    const submitButton = newScenarioForm?.querySelector('button[type="submit"]');
    let isSubmitting = false;
    
    function filterScenarios() {
        const selectedCategory = categoryFilter.value;
        const selectedDifficulty = difficultyFilter.value;
        const selectedDuration = parseInt(durationFilter.value) || Number.MAX_VALUE;
        
        scenarioCards.forEach(card => {
            const category = card.dataset.category;
            const difficulty = card.dataset.difficulty;
            const duration = parseInt(card.dataset.duration);
            
            const categoryMatch = !selectedCategory || category === selectedCategory;
            const difficultyMatch = !selectedDifficulty || difficulty === selectedDifficulty;
            const durationMatch = duration <= selectedDuration;
            
            card.style.display = categoryMatch && difficultyMatch && durationMatch ? '' : 'none';
        });
    }
    
    categoryFilter.addEventListener('change', filterScenarios);
    difficultyFilter.addEventListener('change', filterScenarios);
    durationFilter.addEventListener('change', filterScenarios);
    
    function showError(message, field = null) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger mt-2';
        errorDiv.textContent = message;
        
        if (field) {
            const parent = field.parentElement;
            const existingError = parent.querySelector('.alert-danger');
            if (existingError) {
                existingError.remove();
            }
            parent.appendChild(errorDiv);
        } else {
            const form = document.getElementById('newScenarioForm');
            const existingError = form.querySelector('.alert-danger');
            if (existingError) {
                existingError.remove();
            }
            form.insertBefore(errorDiv, form.firstChild);
        }
    }

    function clearErrors() {
        document.querySelectorAll('.alert-danger').forEach(error => error.remove());
    }

    function validateField(field) {
        clearErrors();
        
        if (!field.value.trim()) {
            showError(`${field.getAttribute('name')} is required`, field);
            return false;
        }
        
        if (field.type === 'number') {
            const value = parseInt(field.value);
            const min = parseInt(field.getAttribute('min'));
            const max = parseInt(field.getAttribute('max'));
            
            if (isNaN(value)) {
                showError(`${field.getAttribute('name')} must be a valid number`, field);
                return false;
            }
            
            if (min !== null && value < min) {
                showError(`${field.getAttribute('name')} must be at least ${min}`, field);
                return false;
            }
            
            if (max !== null && value > max) {
                showError(`${field.getAttribute('name')} must not exceed ${max}`, field);
                return false;
            }
        }
        
        return true;
    }

    function setSubmitting(submitting) {
        isSubmitting = submitting;
        if (submitButton) {
            submitButton.disabled = submitting;
            submitButton.innerHTML = submitting ? 
                '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Creating...' : 
                'Create Scenario';
        }
    }
    
    if (newScenarioForm) {
        // Add validation on input
        newScenarioForm.querySelectorAll('input, textarea, select').forEach(field => {
            field.addEventListener('input', () => validateField(field));
        });

        newScenarioForm.addEventListener('submit', function(e) {
            e.preventDefault();
            if (isSubmitting) return;
            
            clearErrors();
            
            // Validate all fields
            let isValid = true;
            this.querySelectorAll('[required]').forEach(field => {
                if (!validateField(field)) {
                    isValid = false;
                }
            });
            
            // Additional validation for min/max participants
            const minParticipants = parseInt(this.querySelector('[name="min_participants"]').value);
            const maxParticipants = parseInt(this.querySelector('[name="max_participants"]').value);
            if (minParticipants > maxParticipants) {
                showError('Minimum participants cannot be greater than maximum participants');
                isValid = false;
            }
            
            if (!isValid) return;
            
            setSubmitting(true);
            
            const formData = new FormData(this);
            const data = Object.fromEntries(formData.entries());
            
            // Convert numeric fields
            ['min_participants', 'max_participants', 'duration_minutes'].forEach(field => {
                data[field] = parseInt(data[field]);
            });
            
            fetch('/scenarios/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                } else {
                    throw new Error(data.error || 'Error creating scenario');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showError(error.message || 'Error creating scenario');
            })
            .finally(() => {
                setSubmitting(false);
            });
        });
    }
    
    // Participant number validation
    const minParticipants = document.querySelector('input[name="min_participants"]');
    const maxParticipants = document.querySelector('input[name="max_participants"]');
    
    if (minParticipants && maxParticipants) {
        minParticipants.addEventListener('change', function() {
            maxParticipants.min = this.value;
            validateField(maxParticipants);
        });
        
        maxParticipants.addEventListener('change', function() {
            minParticipants.max = this.value;
            validateField(minParticipants);
        });
    }
});
