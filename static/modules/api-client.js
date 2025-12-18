/**
 * APIClient - Handles all API calls to the backend
 */
export class APIClient {
    async checkHealth() {
        try {
            const response = await fetch('/api/health');
            return await response.json();
        } catch (error) {
            console.error('Health check error:', error);
            return { status: 'unhealthy', error: error.message };
        }
    }
    
    async loadModels() {
        try {
            const response = await fetch('/api/models');
            return await response.json();
        } catch (error) {
            console.error('Failed to load models:', error);
            return [];
        }
    }
    
    async loadExternalApiKeyStatus() {
        try {
            const response = await fetch('/api/external-api-key-status');
            return await response.json();
        } catch (error) {
            console.error('Failed to load external API key status:', error);
            return { has_key: false, masked_key: '' };
        }
    }
    
    async loadFigures() {
        try {
            const response = await fetch('/api/figures');
            return await response.json();
        } catch (error) {
            console.error('Failed to load figures:', error);
            return [];
        }
    }
    
    async loadCurrentFigure() {
        try {
            // Always reset to General Chat on page load
            await fetch('/api/figure/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ figure_id: null })
            });
            return null;
        } catch (error) {
            console.error('Failed to reset figure:', error);
            return null;
        }
    }
    
    async selectFigure(figureId) {
        try {
            const response = await fetch('/api/figure/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ figure_id: figureId || null })
            });
            return await response.json();
        } catch (error) {
            console.error('Error selecting figure:', error);
            throw error;
        }
    }
    
    async updateRagStatus(currentFigure) {
        try {
            if (currentFigure) {
                const figureId = currentFigure.figure_id || currentFigure;
                const response = await fetch(`/api/figure/${figureId}`);
                if (response.ok) {
                    const figure = await response.json();
                    return { count: figure.document_count || 0, status: 'success' };
                }
            }
            return { count: 0, status: 'no_figure' };
        } catch (error) {
            console.error('Error fetching RAG stats:', error);
            return { count: 0, status: 'error' };
        }
    }
    
    async sendChatMessage(config, abortController) {
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
                signal: abortController.signal
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return response;
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('Request was cancelled');
            } else {
                console.error('Error in sendMessage:', error);
            }
            throw error;
        }
    }
}

