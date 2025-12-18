/**
 * StateManager - Manages application state including session data, settings, and toggles
 */
export class StateManager {
    constructor() {
        // State variables
        this.isStreaming = false;
        this.currentFigure = null;
        this.ragEnabled = true;
        this.thinkingVisible = true;
        this.documentsVisible = true;
        this.controlPanelOpen = false;
        this.figurePanelOpen = false;
        this.thinkingIntensity = 'normal';
        this.temperature = 1.0;
        this.abortController = null;
        
        // Message state
        this.currentMessageElement = null;
        this.currentSourcesElement = null;
        this.isInThinking = false;
        this.thinkingContent = '';
        this.thinkingBuffer = '';
        this.currentThinkingElement = null;
        this.currentResponseElement = null;
        this.paragraphBuffer = '';
        this.responseContentElement = null;
        
        // Document tracking
        this.currentSources = {};
        this.allRetrievedDocuments = new Map();
        this.currentMessageDocuments = [];
    }
    
    savePanelState() {
        localStorage.setItem('controlPanelOpen', this.controlPanelOpen);
        localStorage.setItem('figurePanelOpen', this.figurePanelOpen);
        localStorage.setItem('ragEnabled', this.ragEnabled);
        localStorage.setItem('thinkingVisible', this.thinkingVisible);
        localStorage.setItem('documentsVisible', this.documentsVisible);
        localStorage.setItem('thinkingIntensity', this.thinkingIntensity);
        localStorage.setItem('temperature', this.temperature);
    }
    
    loadPanelState() {
        // Load panel open state (default closed on mobile, open on desktop)
        const savedPanelState = localStorage.getItem('controlPanelOpen');
        if (savedPanelState !== null) {
            this.controlPanelOpen = savedPanelState === 'true';
        } else {
            this.controlPanelOpen = window.innerWidth > 1024;
        }
        
        // Load figure panel state (only apply on mobile/tablet)
        if (window.innerWidth <= 1024) {
            const savedFigurePanelState = localStorage.getItem('figurePanelOpen');
            if (savedFigurePanelState !== null) {
                this.figurePanelOpen = savedFigurePanelState === 'true';
            } else {
                this.figurePanelOpen = false;
            }
        } else {
            this.figurePanelOpen = true;
        }
        
        // Load toggle states
        const savedRagState = localStorage.getItem('ragEnabled');
        if (savedRagState !== null) {
            this.ragEnabled = savedRagState === 'true';
        }
        
        const savedThinkingState = localStorage.getItem('thinkingVisible');
        if (savedThinkingState !== null) {
            this.thinkingVisible = savedThinkingState === 'true';
        } else {
            this.thinkingVisible = true;
        }
        
        const savedDocumentsState = localStorage.getItem('documentsVisible');
        if (savedDocumentsState !== null) {
            this.documentsVisible = savedDocumentsState === 'true';
        }
        
        const savedThinkingIntensity = localStorage.getItem('thinkingIntensity');
        if (savedThinkingIntensity !== null) {
            this.thinkingIntensity = savedThinkingIntensity;
        }
        
        const savedTemperature = localStorage.getItem('temperature');
        if (savedTemperature !== null) {
            this.temperature = parseFloat(savedTemperature);
        }
    }
    
    resetMessageState() {
        this.currentResponseElement = null;
        this.paragraphBuffer = '';
        this.responseContentElement = null;
        this.isInThinking = false;
        this.thinkingContent = '';
        this.currentThinkingElement = null;
        this.currentMessageDocuments = [];
    }
}

