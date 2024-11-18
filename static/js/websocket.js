// Initialize socket in global scope
let socket;

document.addEventListener('DOMContentLoaded', function() {
    // Initialize socket with reconnection options
    socket = io({
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 20000
    });

    const interactionCount = document.getElementById('interaction-count');
    let count = 0;
    
    socket.on('connect', function() {
        console.log('WebSocket connected');
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').className = 'alert alert-success';
            document.getElementById('simulation-status').textContent = 'Connected to server';
        }
    });
    
    socket.on('connect_error', function(error) {
        console.error('Connection error:', error);
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').className = 'alert alert-danger';
            document.getElementById('simulation-status').textContent = 'Connection error. Attempting to reconnect...';
        }
    });

    socket.on('generating_interaction', function(data) {
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').textContent = 
                `Generating interaction between ${data.initiator} and ${data.receiver}... (${data.conversation_depth})`;
            
            // Update depth progress if available
            const depthProgress = document.getElementById('depth-progress');
            if (depthProgress && data.conversation_depth) {
                const [current, max] = data.conversation_depth.split('/').map(Number);
                const percentage = (current / max) * 100;
                depthProgress.style.width = `${percentage}%`;
                
                // Update progress bar color based on completion
                if (percentage >= 100) {
                    depthProgress.className = 'progress-bar bg-success';
                }
            }
        }
    });
    
    socket.on('new_interaction', function(data) {
        const interaction = data.interaction;
        
        // Update conversation depth display
        if (interaction.conversation_depth) {
            const depthProgress = document.getElementById('depth-progress');
            if (depthProgress) {
                const [current, max] = interaction.conversation_depth.split('/').map(Number);
                const percentage = (current / max) * 100;
                depthProgress.style.width = `${percentage}%`;
                
                if (percentage >= 100) {
                    depthProgress.className = 'progress-bar bg-success';
                }
            }
        }
        
        if (typeof addInteractionToFeed === 'function') {
            addInteractionToFeed(interaction);
            count++;
            if (interactionCount) {
                interactionCount.textContent = `${count} interaction${count !== 1 ? 's' : ''}`;
            }
        }
    });
    
    socket.on('simulation_warning', function(data) {
        console.warn('Simulation warning:', data.message);
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').className = 'alert alert-warning';
            document.getElementById('simulation-status').textContent = data.message;
        }
    });
    
    socket.on('simulation_ended', function(data) {
        console.log('Simulation ended:', data);
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').className = 'alert alert-info';
            document.getElementById('simulation-status').textContent = data.message;
        }
        
        // Reset depth progress
        const depthProgress = document.getElementById('depth-progress');
        if (depthProgress) {
            depthProgress.style.width = '0%';
            depthProgress.className = 'progress-bar';
        }
        
        window.location.href = '/results';
    });
    
    socket.on('simulation_error', function(data) {
        console.error('Simulation error:', data.error);
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').className = 'alert alert-danger';
            document.getElementById('simulation-status').textContent = data.error;
        }
    });
    
    socket.on('disconnect', function() {
        console.log('WebSocket disconnected');
        if (document.getElementById('simulation-status')) {
            document.getElementById('simulation-status').className = 'alert alert-danger';
            document.getElementById('simulation-status').textContent = 'Disconnected from server. Attempting to reconnect...';
        }
    });
});

// Export socket for other modules
window.socket = socket;
