document.addEventListener('DOMContentLoaded', function() {
    const startButton = document.getElementById('start-simulation');
    const stopButton = document.getElementById('stop-simulation');
    const simulationFeed = document.getElementById('simulation-feed');
    const statusIndicator = document.getElementById('simulation-status');
    const loadingIndicator = document.getElementById('loading-indicator');
    const scenarioSelect = document.getElementById('scenario');
    const participantWarning = document.getElementById('participant-warning');
    const scenarioDetails = document.getElementById('scenario-details');
    const personaSearch = document.getElementById('persona-search');
    const behaviorFilter = document.getElementById('behavior-filter');
    const interactionFilter = document.getElementById('interaction-filter');
    const communicationFilter = document.getElementById('communication-filter');
    const personaPreview = document.getElementById('persona-preview');
    const personaItems = document.querySelectorAll('.persona-item');
    const previewContainer = document.getElementById('preview-container');
    const customContextInput = document.getElementById('custom-context');
    const conversationDepthSelect = document.getElementById('conversation-depth');
    const depthProgress = document.getElementById('depth-progress');
    
    let currentSimulationId = null;
    let currentScenario = null;
    let currentConversationCount = 0;
    let maxConversationDepth = getMaxDepth('medium');

    function getMaxDepth(depth) {
        const depthMap = {
            'short': 2,
            'medium': 5,
            'long': 10,
            'extended': 25,
            'longform': 50,
            'marathon': 100
        };
        return depthMap[depth] || 5;
    }

    function updateDepthIndicator(count = 0) {
        const depth = conversationDepthSelect.value;
        const maxDepth = getMaxDepth(depth);
        const percentage = Math.min((count / maxDepth) * 100, 100);
        
        depthProgress.style.width = `${percentage}%`;
        
        // Update progress bar color based on depth setting and progress
        const colorMap = {
            'short': 'info',
            'medium': 'warning',
            'long': 'danger',
            'extended': 'primary',
            'longform': 'secondary',
            'marathon': 'dark'
        };
        
        depthProgress.className = `progress-bar bg-${colorMap[depth] || 'info'}`;
        
        // Add success class when conversation is complete
        if (percentage >= 100) {
            depthProgress.classList.add('bg-success');
        }
    }

    if (conversationDepthSelect) {
        conversationDepthSelect.addEventListener('change', function() {
            maxConversationDepth = getMaxDepth(this.value);
            updateDepthIndicator(currentConversationCount);
        });
    }

    function updateStatus(message, type = 'info') {
        statusIndicator.textContent = message;
        statusIndicator.className = `alert alert-${type}`;
        statusIndicator.style.display = 'block';
    }
    
    function showLoading(show) {
        loadingIndicator.style.display = show ? 'block' : 'none';
    }

    function formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleTimeString();
    }

    function createInteractionElement(interaction) {
        const interactionDiv = document.createElement('div');
        interactionDiv.className = 'interaction-item mb-3 fade-in';
        
        const headerDiv = document.createElement('div');
        headerDiv.className = 'd-flex justify-content-between align-items-start mb-2';
        
        const participantsDiv = document.createElement('div');
        participantsDiv.innerHTML = `
            <span class="fw-bold">${interaction.initiator}</span>
            <i class="fas fa-arrow-right mx-2"></i>
            <span class="fw-bold">${interaction.receiver}</span>
        `;
        
        const timestampSpan = document.createElement('span');
        timestampSpan.className = 'text-muted small';
        timestampSpan.textContent = formatTimestamp(interaction.timestamp);
        
        headerDiv.appendChild(participantsDiv);
        headerDiv.appendChild(timestampSpan);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'interaction-content';
        contentDiv.textContent = interaction.content;
        
        const footerDiv = document.createElement('div');
        footerDiv.className = 'd-flex justify-content-between align-items-center mt-2';
        
        const sentimentBadge = document.createElement('span');
        sentimentBadge.className = `badge bg-${
            interaction.sentiment === 'positive' ? 'success' :
            interaction.sentiment === 'negative' ? 'danger' : 'secondary'
        }`;
        sentimentBadge.textContent = interaction.sentiment;
        
        const contextBadge = document.createElement('span');
        contextBadge.className = 'badge bg-info';
        contextBadge.textContent = `Depth: ${++currentConversationCount}/${maxConversationDepth}`;
        
        footerDiv.appendChild(sentimentBadge);
        footerDiv.appendChild(contextBadge);
        
        interactionDiv.appendChild(headerDiv);
        interactionDiv.appendChild(contentDiv);
        interactionDiv.appendChild(footerDiv);
        
        // Update depth indicator
        updateDepthIndicator(currentConversationCount);
        
        return interactionDiv;
    }

    // WebSocket event handlers
    socket.on('new_interaction', function(data) {
        const interaction = data.interaction;
        const interactionElement = createInteractionElement(interaction);
        
        if (simulationFeed.firstChild) {
            simulationFeed.insertBefore(interactionElement, simulationFeed.firstChild);
        } else {
            simulationFeed.appendChild(interactionElement);
        }
        
        // Fade in animation
        requestAnimationFrame(() => {
            interactionElement.classList.add('show');
        });
        
        // Update interaction count
        const countElement = document.getElementById('interaction-count');
        if (countElement) {
            const count = simulationFeed.children.length;
            countElement.textContent = `${count} interaction${count !== 1 ? 's' : ''}`;
        }
    });

    function updateParticipantCount() {
        if (!currentScenario) return false;

        const selectedCount = document.querySelectorAll('.persona-checkbox:checked').length;
        const min = parseInt(currentScenario.dataset.min);
        const max = parseInt(currentScenario.dataset.max);
        const countElement = document.getElementById('participant-count');
        const progressBar = document.getElementById('participant-progress');
        
        if (countElement) {
            countElement.textContent = `Currently selected: ${selectedCount} participant${selectedCount !== 1 ? 's' : ''}`;
        }
        
        if (progressBar) {
            const percentage = Math.min((selectedCount / max) * 100, 100);
            progressBar.style.width = `${percentage}%`;
            
            if (selectedCount < min) {
                progressBar.className = 'progress-bar bg-danger';
            } else if (selectedCount > max) {
                progressBar.className = 'progress-bar bg-warning';
            } else {
                progressBar.className = 'progress-bar bg-success';
            }
        }

        return validateParticipants(selectedCount, min, max);
    }

    function validateParticipants(selectedCount, min, max) {
        if (!currentScenario) return false;

        if (selectedCount < min || selectedCount > max) {
            const message = selectedCount < min 
                ? `Need at least ${min - selectedCount} more participant${min - selectedCount !== 1 ? 's' : ''}`
                : `Please remove ${selectedCount - max} participant${selectedCount - max !== 1 ? 's' : ''}`;
                
            if (participantWarning) {
                participantWarning.innerHTML = `
                    <strong>Participant Requirements Not Met:</strong><br>
                    ${message} for this scenario.<br>
                    <small>This scenario requires ${min} to ${max} participants.</small>
                `;
                participantWarning.style.display = 'block';
            }
            return false;
        }

        if (participantWarning) {
            participantWarning.style.display = 'none';
        }
        return true;
    }

    function getCombinedContext(scenarioContext, customContext) {
        if (!customContext || customContext.trim() === '') {
            return scenarioContext;
        }
        return `${scenarioContext}\n\nAdditional Context:\n${customContext.trim()}`;
    }

    function updateScenarioDetails(selectedOption) {
        if (!selectedOption || !selectedOption.value) {
            if (scenarioDetails) {
                scenarioDetails.style.display = 'none';
            }
            if (document.getElementById('scenario-custom-context')) {
                document.getElementById('scenario-custom-context').style.display = 'none';
            }
            return;
        }

        currentScenario = selectedOption;
        const description = selectedOption.dataset.description;
        const difficulty = selectedOption.dataset.difficulty;
        const duration = selectedOption.dataset.duration;
        const min = selectedOption.dataset.min;
        const max = selectedOption.dataset.max;
        const context = selectedOption.dataset.context;

        const descriptionEl = document.getElementById('scenario-description');
        const difficultyEl = document.getElementById('scenario-difficulty');
        const durationEl = document.getElementById('scenario-duration');
        const participantRangeEl = document.getElementById('participant-range');
        const customContextContainer = document.getElementById('scenario-custom-context');

        if (descriptionEl) descriptionEl.textContent = description;
        if (difficultyEl) difficultyEl.textContent = `Difficulty: ${difficulty}`;
        if (durationEl) durationEl.textContent = `${duration} minutes`;
        if (participantRangeEl) participantRangeEl.textContent = `${min} to ${max}`;

        if (customContextInput) {
            customContextInput.placeholder = `Default context:\n${context}\n\nAdd custom context to modify the scenario behavior...`;
        }

        if (customContextContainer) {
            customContextContainer.style.display = 'block';
        }

        if (scenarioDetails) {
            scenarioDetails.style.display = 'block';
        }
        updateParticipantCount();
    }

    function filterPersonas() {
        // Get and normalize filter values with proper null checks
        const searchTerm = (personaSearch?.value || '').toLowerCase().trim();
        const behaviorValue = (behaviorFilter?.value || '').toLowerCase().trim();
        const interactionValue = (interactionFilter?.value || '').toLowerCase().trim();
        const communicationValue = (communicationFilter?.value || '').toLowerCase().trim();

        // Log filter criteria for debugging
        console.log('Applying filters:', {
            search: searchTerm,
            behavior: behaviorValue,
            interaction: interactionValue,
            communication: communicationValue
        });

        let visibleCount = 0;
        const noResultsMessage = document.getElementById('no-results-message');

        try {
            personaItems.forEach(item => {
                // Get and normalize data attributes with proper null checks
                const name = (item.dataset.name || '').toLowerCase();
                const behavior = (item.dataset.behavior || '').toLowerCase();
                const interaction = (item.dataset.interaction || '').toLowerCase();
                const communication = (item.dataset.communication || '').toLowerCase();
                const personality = (item.dataset.personality || '').toLowerCase();
                const interests = (item.dataset.interests || '').toLowerCase();
                const goals = (item.dataset.goals || '').toLowerCase();
                const tags = (item.dataset.tags || '').toLowerCase();

                // Use exact match for behavior, interaction, and communication filters
                const behaviorMatch = !behaviorValue || behavior === behaviorValue;
                const interactionMatch = !interactionValue || interaction === interactionValue;
                const communicationMatch = !communicationValue || communication === communicationValue;

                // Use includes for search term to allow partial matches
                const searchMatch = !searchTerm || 
                    name.includes(searchTerm) || 
                    personality.includes(searchTerm) || 
                    interests.includes(searchTerm) || 
                    goals.includes(searchTerm) ||
                    tags.includes(searchTerm);

                const matches = searchMatch && behaviorMatch && interactionMatch && communicationMatch;

                // Update visibility and highlight
                if (matches) {
                    item.classList.remove('filtered-out');
                    item.classList.add('highlight-match');
                    visibleCount++;
                } else {
                    item.classList.remove('highlight-match');
                    item.classList.add('filtered-out');
                }
            });

            // Show/hide no results message
            if (noResultsMessage) {
                noResultsMessage.style.display = visibleCount === 0 ? 'block' : 'none';
            }

            console.log(`Filter results: ${visibleCount} personas visible`);
            return visibleCount;
        } catch (error) {
            console.error('Error in filterPersonas:', error);
            return 0;
        }
    }

    function resetFilters() {
        // Reset all filter inputs
        if (personaSearch) personaSearch.value = '';
        if (behaviorFilter) behaviorFilter.value = '';
        if (interactionFilter) interactionFilter.value = '';
        if (communicationFilter) communicationFilter.value = '';

        // Remove filtered-out and highlight classes from all items
        personaItems.forEach(item => {
            item.classList.remove('filtered-out', 'highlight-match');
        });

        // Hide no results message
        const noResultsMessage = document.getElementById('no-results-message');
        if (noResultsMessage) {
            noResultsMessage.style.display = 'none';
        }

        console.log('Filters reset');
    }

    function updatePersonaPreviews() {
        if (!previewContainer) return;
        
        const selectedCheckboxes = document.querySelectorAll('.persona-checkbox:checked');
        previewContainer.innerHTML = '';
        
        if (selectedCheckboxes.length === 0) {
            if (personaPreview) {
                personaPreview.style.display = 'none';
            }
            return;
        }
        
        selectedCheckboxes.forEach(checkbox => {
            const personaItem = checkbox.closest('.persona-item');
            if (!personaItem) return;

            const previewCard = document.createElement('div');
            previewCard.className = 'persona-preview-card fade-in';
            
            const traits = [
                { text: personaItem.dataset.behavior, class: 'bg-primary' },
                { text: personaItem.dataset.interaction, class: 'bg-info' },
                { text: personaItem.dataset.communication, class: 'bg-success' }
            ];
            
            previewCard.innerHTML = `
                <h5 class="mb-2">${personaItem.dataset.name}</h5>
                <p class="mb-2">${personaItem.dataset.personality}</p>
                <div class="preview-traits mb-2">
                    ${traits.map(trait => 
                        `<span class="badge ${trait.class}">${trait.text}</span>`
                    ).join('')}
                </div>
                <div class="mb-2">
                    <strong>Interests:</strong><br>
                    ${personaItem.dataset.interests}
                </div>
                <div class="mb-2">
                    <strong>Goals:</strong><br>
                    ${personaItem.dataset.goals}
                </div>
                <div class="preview-tags">
                    ${personaItem.dataset.tags.split(',')
                        .map(tag => `<span class="badge bg-secondary">${tag.trim()}</span>`)
                        .join('')}
                </div>
            `;
            
            previewContainer.appendChild(previewCard);
            
            requestAnimationFrame(() => {
                previewCard.classList.add('show');
            });
        });
        
        if (personaPreview) {
            personaPreview.style.display = 'block';
        }
    }

    if (scenarioSelect) {
        scenarioSelect.addEventListener('change', function() {
            const selectedOption = this.options[this.selectedIndex];
            updateScenarioDetails(selectedOption);
        });
    }

    if (personaSearch) personaSearch.addEventListener('input', filterPersonas);
    if (behaviorFilter) behaviorFilter.addEventListener('change', filterPersonas);
    if (interactionFilter) interactionFilter.addEventListener('change', filterPersonas);
    if (communicationFilter) communicationFilter.addEventListener('change', filterPersonas);

    personaItems.forEach(item => {
        item.addEventListener('click', function(e) {
            if (e.target.type !== 'checkbox') {
                const checkbox = this.querySelector('.persona-checkbox');
                if (checkbox) {
                    checkbox.checked = !checkbox.checked;
                    updateParticipantCount();
                    updatePersonaPreviews();
                }
            }
        });
        
        const checkbox = item.querySelector('.persona-checkbox');
        if (checkbox) {
            checkbox.addEventListener('change', () => {
                updateParticipantCount();
                updatePersonaPreviews();
            });
        }
    });

    if (startButton) {
        startButton.addEventListener('click', function() {
            const name = document.getElementById('simulation-name').value;
            const scenarioId = scenarioSelect.value;
            const selectedPersonas = Array.from(document.querySelectorAll('.persona-checkbox:checked'))
                .map(checkbox => parseInt(checkbox.value));
            const customContext = customContextInput?.value;
            const conversationDepth = conversationDepthSelect?.value || 'medium';
            
            if (name && scenarioId && updateParticipantCount()) {
                showLoading(true);
                updateStatus('Starting simulation...', 'info');
                
                // Get combined context
                const selectedOption = scenarioSelect.options[scenarioSelect.selectedIndex];
                const scenarioContext = selectedOption.dataset.context;
                const combinedContext = getCombinedContext(scenarioContext, customContext);
                
                // Make the start request with conversation depth
                fetch('/simulation/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        name: name,
                        scenario_id: parseInt(scenarioId),
                        personas: selectedPersonas,
                        custom_context: combinedContext,
                        conversation_depth: conversationDepth  // Include conversation depth in request
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        throw new Error(data.error);
                    }
                    currentSimulationId = data.simulation_id;
                    startButton.disabled = true;
                    stopButton.disabled = false;
                    updateStatus('Simulation started successfully', 'success');
                })
                .catch(error => {
                    updateStatus(`Error starting simulation: ${error.message}`, 'danger');
                    showLoading(false);
                });
            } else {
                updateStatus('Please fill in all required fields and select appropriate number of participants', 'warning');
            }
        });
    }
    
    if (stopButton) {
        stopButton.addEventListener('click', function() {
            if (currentSimulationId) {
                showLoading(true);
                updateStatus('Stopping simulation...', 'info');
                
                fetch(`/simulation/${currentSimulationId}/stop`, {
                    method: 'POST'
                })
                .then(() => {
                    if (startButton) startButton.disabled = false;
                    if (stopButton) stopButton.disabled = true;
                    currentSimulationId = null;
                    updateStatus('Simulation stopped', 'info');
                })
                .catch(error => {
                    updateStatus('Failed to stop simulation', 'danger');
                    console.error('Error:', error);
                })
                .finally(() => {
                    showLoading(false);
                });
            }
        });
    }

    if (!previewContainer && personaPreview) {
        const container = document.createElement('div');
        container.id = 'preview-container';
        container.className = 'preview-scroll-container';
        personaPreview.appendChild(container);
    }

    window.addInteractionToFeed = function(interaction) {
        if (!simulationFeed) return;

        const interactionElement = document.createElement('div');
        interactionElement.className = 'interaction-item mb-3';
        
        const sentimentClass = interaction.sentiment === 'positive' ? 'border-success' :
                             interaction.sentiment === 'negative' ? 'border-danger' : 'border-info';
        
        // Check if there's custom context in the interaction
        const hasCustomContext = customContextInput && customContextInput.value.trim() !== '';
        
        interactionElement.innerHTML = `
            <div class="interaction-header">
                <small class="text-muted">${new Date(interaction.timestamp).toLocaleTimeString()}</small>
                <div class="interaction-participants">
                    <strong>${interaction.initiator}</strong>
                    <i class="fas fa-arrow-right mx-2"></i>
                    <strong>${interaction.receiver}</strong>
                    ${hasCustomContext ? '<span class="badge bg-info ms-2">Custom Context</span>' : ''}
                </div>
            </div>
            <div class="interaction-content ${sentimentClass} mt-2">
                ${interaction.content}
            </div>
        `;
        
        interactionElement.style.opacity = '0';
        interactionElement.style.transform = 'translateY(20px)';
        
        simulationFeed.insertBefore(interactionElement, simulationFeed.firstChild);
        
        requestAnimationFrame(() => {
            interactionElement.style.transition = 'all 0.5s ease-out';
            interactionElement.style.opacity = '1';
            interactionElement.style.transform = 'translateY(0)';
        });
        
        interactionElement.style.backgroundColor = 'rgba(var(--bs-primary-rgb), 0.1)';
        setTimeout(() => {
            interactionElement.style.backgroundColor = '';
        }, 1000);
        
        const countElement = document.getElementById('interaction-count');
        if (countElement) {
            const currentCount = parseInt(countElement.textContent) || 0;
            countElement.textContent = `${currentCount + 1} interactions`;
        }
    };
});