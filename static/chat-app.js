/**
 * ChatApp - Main application class
 * Core class definition, initialization, and event handling
 * 
 * Additional methods are added via prototype from:
 * - chat-api.js: API/server communication
 * - chat-ui.js: UI interactions and streaming
 */

class ChatApp {
    constructor() {
        // DOM Elements - Chat
        this.chatMessages = document.getElementById('chat-messages');
        this.messageInput = document.getElementById('message-input');
        this.chatForm = document.getElementById('chat-form');
        this.sendButton = document.getElementById('send-button');
        this.stopButton = document.getElementById('stop-button');
        
        // DOM Elements - Model/Source Selection
        this.modelSelect = document.getElementById('model-select');
        this.modelSourceSelect = document.getElementById('model-source-select');
        this.externalApiConfig = document.getElementById('external-api-config');
        this.externalApiUrl = document.getElementById('external-api-url');
        this.customModelName = document.getElementById('custom-model-name');
        this.externalApiKey = document.getElementById('external-api-key');
        this.apiKeyStatus = document.getElementById('api-key-status');
        
        // DOM Elements - Status
        this.statusDot = document.getElementById('status-dot');
        this.statusText = document.getElementById('status-text');
        this.ragStatus = document.getElementById('rag-status');
        
        // DOM Elements - Documents Panel
        this.documentsPanel = document.getElementById('documents-panel');
        this.documentsContent = document.getElementById('documents-content');
        this.documentsEmpty = document.getElementById('documents-empty');
        
        // DOM Elements - Source Modal
        this.sourceModal = document.getElementById('source-modal');
        this.sourceModalTitle = document.getElementById('source-modal-title');
        this.sourceModalText = document.getElementById('source-modal-text');
        this.sourceModalClose = document.getElementById('source-modal-close');
        
        // DOM Elements - Figure Selection
        this.figureSelect = document.getElementById('figure-select');
        this.figureName = document.getElementById('figure-name');
        this.figureDescription = document.getElementById('figure-description');
        
        // DOM Elements - Toggles
        this.ragToggleContainer = document.getElementById('rag-toggle-container');
        this.ragToggleSwitch = document.getElementById('rag-toggle-switch');
        this.thinkingToggleContainer = document.getElementById('thinking-toggle-container');
        this.thinkingToggleSwitch = document.getElementById('thinking-toggle-switch');
        this.queryAugmentationToggleContainer = document.getElementById('query-augmentation-toggle-container');
        this.queryAugmentationToggleSwitch = document.getElementById('query-augmentation-toggle-switch');
        
        // DOM Elements - Augmented Query
        this.augmentedQueryPanel = document.getElementById('augmented-query-panel');
        this.augmentedQueryText = document.getElementById('augmented-query-text');
        this.augmentedQueryModelSpan = document.getElementById('augmented-query-model');
        
        // DOM Elements - Settings
        this.docsCountSelect = document.getElementById('docs-count-select');
        this.thinkingIntensitySelect = document.getElementById('thinking-intensity-select');
        this.temperatureSlider = document.getElementById('temperature-slider');
        this.temperatureValue = document.getElementById('temperature-value');
        this.saveConversationBtn = document.getElementById('save-conversation-btn');
        
        // DOM Elements - Control Panel
        this.controlPanel = document.getElementById('control-panel');
        this.controlToggleBtn = document.getElementById('control-toggle-btn');
        this.controlCloseBtn = document.getElementById('control-close-btn');
        this.overlay = document.getElementById('overlay');
        
        // DOM Elements - Figure Panel
        this.figurePanel = document.getElementById('figure-panel');
        this.figureToggleBtn = document.getElementById('figure-toggle-btn');
        this.figureCloseBtn = document.getElementById('figure-close-btn');
        this.figureEmpty = document.getElementById('figure-empty');
        this.figureDisplayInfo = document.getElementById('figure-info');
        this.figureImage = document.getElementById('figure-image');
        this.figureDisplayName = document.getElementById('figure-display-name');
        this.figureYears = document.getElementById('figure-years');
        this.figureDisplayDescription = document.getElementById('figure-display-description');
        this.figureDisplayPersonality = document.getElementById('figure-display-personality');
        
        // Model Data
        this.localModels = [];
        this.externalModels = null;
        this.currentSource = 'external';
        
        // State - Streaming
        this.isStreaming = false;
        this.currentMessageElement = null;
        this.currentSourcesElement = null;
        this.isInThinking = false;
        this.thinkingContent = '';
        this.thinkingBuffer = '';
        this.currentThinkingElement = null;
        this.currentResponseElement = null;
        this.currentSources = {};
        this.paragraphBuffer = '';
        this.responseContentElement = null;
        this.abortController = null;
        
        // State - Documents
        this.allRetrievedDocuments = new Map();
        this.currentMessageDocuments = [];
        
        // State - Figure
        this.currentFigure = null;
        
        // State - Toggles
        this.ragEnabled = true;
        this.thinkingVisible = true;
        this.queryAugmentationEnabled = true;
        this.queryAugmentationModel = '';
        
        // State - Panels
        this.controlPanelOpen = false;
        this.figurePanelOpen = false;
        
        // State - Settings
        this.thinkingIntensity = 'normal';
        this.temperature = 1.0;
        
        // Feature Flags (from server config)
        this.configRagEnabled = true;
        this.configQueryAugmentationEnabled = true;
        this.docsToRetrieveOptions = [3, 5, 10, 15, 20];
        
        this.init();
    }

    async init() {
        this.setupEventListeners();
        this.checkHealth();
        await this.loadFeatureFlags();
        await this.loadModels();
        this.loadFigures();
        await this.loadCurrentFigure();
        this.autoResizeTextarea();
        this.updateRagStatus();
        this.loadPanelState();
        this.initializeToggles();
        this.updateFigurePanel();
        
        // Desktop initialization
        if (window.innerWidth > 1024 && this.figurePanel) {
            this.figurePanel.classList.remove('open', 'closed');
        }
    }

    setupEventListeners() {
        // Chat form submission
        this.chatForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSubmit(e);
            }
        });
        this.messageInput.addEventListener('input', () => this.autoResizeTextarea());

        // Mobile keyboard handling
        this.setupMobileKeyboardHandling();

        // Toggle listeners
        this.ragToggleContainer.addEventListener('click', () => this.toggleRAG());
        this.thinkingToggleContainer.addEventListener('click', () => this.toggleThinking());
        if (this.queryAugmentationToggleContainer) {
            this.queryAugmentationToggleContainer.addEventListener('click', () => this.toggleQueryAugmentation());
        }
        this.figureSelect.addEventListener('change', (e) => this.handleFigureChange(e));
        
        // Model source selection
        if (this.modelSourceSelect) {
            this.modelSourceSelect.addEventListener('change', (e) => {
                this.currentSource = e.target.value;
                this.updateModelListForSource();
                
                if (e.target.value === 'external') {
                    this.externalApiConfig.style.display = 'block';
                    this.updateApiKeyStatus();
                    this.loadExternalApiKeyStatus();
                } else {
                    this.externalApiConfig.style.display = 'none';
                    if (this.apiKeyStatus) {
                        this.apiKeyStatus.style.display = 'none';
                    }
                }
            });
        }
        
        // Model selection - show/hide custom model input
        this.modelSelect.addEventListener('change', (e) => {
            if (e.target.value === 'Other') {
                this.customModelName.style.display = 'block';
                this.customModelName.value = '';
                this.customModelName.focus();
            } else {
                this.customModelName.style.display = 'none';
            }
        });
        
        // API Key input
        if (this.externalApiKey) {
            this.externalApiKey.addEventListener('input', (e) => {
                if (this.externalApiKey.getAttribute('data-is-masked') === 'true') {
                    this.externalApiKey.value = '';
                    this.externalApiKey.removeAttribute('data-is-masked');
                    this.externalApiKey.setAttribute('placeholder', 'Enter your API key');
                }
                this.updateApiKeyStatus();
            });
        }
        
        // Thinking intensity
        if (this.thinkingIntensitySelect) {
            this.thinkingIntensitySelect.addEventListener('change', (e) => {
                this.thinkingIntensity = e.target.value;
                this.savePanelState();
            });
        }
        
        // Temperature slider
        if (this.temperatureSlider) {
            this.temperatureSlider.addEventListener('input', (e) => {
                this.temperature = parseFloat(e.target.value);
                if (this.temperatureValue) {
                    this.temperatureValue.textContent = this.temperature.toFixed(1);
                }
                this.savePanelState();
            });
        }
        
        // Stop button
        if (this.stopButton) {
            this.stopButton.addEventListener('click', () => this.stopGeneration());
        }
        
        // Save conversation
        if (this.saveConversationBtn) {
            this.saveConversationBtn.addEventListener('click', () => this.saveConversation());
        }

        // Control panel
        this.controlToggleBtn.addEventListener('click', () => this.toggleControlPanel());
        this.controlCloseBtn.addEventListener('click', () => this.closeControlPanel());
        
        // Figure panel
        if (this.figureToggleBtn) {
            this.figureToggleBtn.addEventListener('click', () => this.toggleFigurePanel());
        }
        if (this.figureCloseBtn) {
            this.figureCloseBtn.addEventListener('click', () => this.closeFigurePanel());
        }
        
        // Overlay
        this.overlay.addEventListener('click', () => {
            this.closeControlPanel();
            this.closeFigurePanel();
        });

        // Source modal
        this.sourceModalClose.addEventListener('click', () => this.closeSourceModal());
        this.sourceModal.addEventListener('click', (e) => {
            if (e.target === this.sourceModal) {
                this.closeSourceModal();
            }
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                if (this.sourceModal.style.display === 'block') {
                    this.closeSourceModal();
                } else if (this.controlPanelOpen) {
                    this.closeControlPanel();
                } else if (this.figurePanelOpen) {
                    this.closeFigurePanel();
                }
            }
            if ((e.ctrlKey || e.metaKey) && e.key === '/') {
                e.preventDefault();
                this.toggleControlPanel();
            }
        });

        // Save state on visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.savePanelState();
            }
        });
    }

    getSelectedModelName() {
        if (this.modelSelect.value === 'Other') {
            return this.customModelName.value || '';
        }
        return this.modelSelect.value || '';
    }

    hasValidModel() {
        const modelName = this.getSelectedModelName();
        return modelName && modelName.trim() !== '';
    }

    handleSubmit(e) {
        e.preventDefault();
        if (this.isStreaming) return;
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        if (!this.hasValidModel()) {
            const sourceName = this.currentSource === 'local' ? 'local' : 'external';
            this.showError(`No ${sourceName} model available. Please select a different source or configure models.`);
            return;
        }
        
        if (this.currentSource === 'external') {
            const apiKey = this.externalApiKey ? this.externalApiKey.value.trim() : '';
            const isMasked = this.externalApiKey && this.externalApiKey.getAttribute('data-is-masked') === 'true';
            if (!apiKey && !isMasked) {
                this.showApiKeyWarning('Please provide an API key to use External API');
                return;
            }
        }
        
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.autoResizeTextarea();
        this.sendMessage(message);
    }
}

// Window resize handler
window.addEventListener('resize', () => {
    const app = window.chatApp;
    if (!app) return;
    
    if (window.innerWidth > 1024) {
        const overlay = document.getElementById('overlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
        
        if (app.figurePanel) {
            app.figurePanel.classList.remove('open', 'closed');
        }
        
        if (app.figureToggleBtn) {
            app.figureToggleBtn.style.display = 'none';
        }
    } else {
        if (app.figureToggleBtn) {
            app.figureToggleBtn.style.display = '';
        }
        
        if (app.figurePanel) {
            if (app.figurePanelOpen) {
                app.figurePanel.classList.add('open');
                app.figurePanel.classList.remove('closed');
            } else {
                app.figurePanel.classList.remove('open');
                app.figurePanel.classList.add('closed');
            }
        }
    }
});

// Global error handling
window.addEventListener('unhandledrejection', event => {
    console.error('Unhandled promise rejection:', event.reason);
    event.preventDefault();
});

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
