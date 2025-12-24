console.log('Loading ChatApp v3.0 - Mobile Optimized');

class ChatApp {
    constructor() {
        // Get all DOM elements
        this.chatMessages = document.getElementById('chat-messages');
        this.messageInput = document.getElementById('message-input');
        this.chatForm = document.getElementById('chat-form');
        this.sendButton = document.getElementById('send-button');
        this.modelSelect = document.getElementById('model-select');
        this.statusDot = document.getElementById('status-dot');
        this.statusText = document.getElementById('status-text');
        this.ragStatus = document.getElementById('rag-status');
        this.documentsPanel = document.getElementById('documents-panel');
        this.documentsContent = document.getElementById('documents-content');
        this.documentsEmpty = document.getElementById('documents-empty');
        this.sourceModal = document.getElementById('source-modal');
        this.sourceModalTitle = document.getElementById('source-modal-title');
        this.sourceModalText = document.getElementById('source-modal-text');
        this.sourceModalClose = document.getElementById('source-modal-close');
        this.figureSelect = document.getElementById('figure-select');
        this.figureInfo = document.getElementById('figure-info');
        this.figureName = document.getElementById('figure-name');
        this.figureDescription = document.getElementById('figure-description');
        this.ragToggleContainer = document.getElementById('rag-toggle-container');
        this.ragToggleSwitch = document.getElementById('rag-toggle-switch');
        this.thinkingToggleContainer = document.getElementById('thinking-toggle-container');
        this.thinkingToggleSwitch = document.getElementById('thinking-toggle-switch');
        this.queryAugmentationToggleContainer = document.getElementById('query-augmentation-toggle-container');
        this.queryAugmentationToggleSwitch = document.getElementById('query-augmentation-toggle-switch');
        this.augmentedQueryPanel = document.getElementById('augmented-query-panel');
        this.augmentedQueryText = document.getElementById('augmented-query-text');
        this.augmentedQueryModelSpan = document.getElementById('augmented-query-model');
        this.docsCountSelect = document.getElementById('docs-count-select');
        this.thinkingIntensitySelect = document.getElementById('thinking-intensity-select');
        this.stopButton = document.getElementById('stop-button');
        this.temperatureSlider = document.getElementById('temperature-slider');
        this.temperatureValue = document.getElementById('temperature-value');
        this.saveConversationBtn = document.getElementById('save-conversation-btn');
        
        // Model source and API configuration elements
        this.modelSourceSelect = document.getElementById('model-source-select');
        this.externalApiConfig = document.getElementById('external-api-config');
        this.externalApiUrl = document.getElementById('external-api-url');
        this.customModelName = document.getElementById('custom-model-name');
        this.externalApiKey = document.getElementById('external-api-key');
        this.apiKeyStatus = document.getElementById('api-key-status');
        
        // Model lists from server
        this.localModels = [];
        this.externalModels = null;  // null means fetch dynamically
        this.currentSource = 'external';  // default source
        
        // Control panel elements
        this.controlPanel = document.getElementById('control-panel');
        this.controlToggleBtn = document.getElementById('control-toggle-btn');
        this.controlCloseBtn = document.getElementById('control-close-btn');
        this.overlay = document.getElementById('overlay');
        
        // Figure panel elements
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
        
        // State variables
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
        this.currentFigure = null;
        this.ragEnabled = true;
        this.thinkingVisible = true;  // Show Thinking ON by default
        this.queryAugmentationEnabled = true;  // Query Augmentation ON by default
        this.queryAugmentationModel = '';  // Model used for query augmentation
        this.controlPanelOpen = false;
        this.figurePanelOpen = false;
        this.thinkingIntensity = 'normal';
        this.temperature = 1.0;  // Default temperature
        this.abortController = null;
        this.allRetrievedDocuments = new Map();  // Track all documents retrieved during conversation
        this.currentMessageDocuments = [];  // Track documents for the current response
        
        // Feature flags from server config (defaults, will be updated from server)
        this.configRagEnabled = true;
        this.configQueryAugmentationEnabled = true;
        
        this.init();
    }

    async init() {
        this.setupEventListeners();
        this.checkHealth();
        await this.loadFeatureFlags();  // Load config-based feature flags first
        await this.loadModels();  // Load models and update UI
        this.loadFigures();
        await this.loadCurrentFigure();
        this.autoResizeTextarea();
        this.updateRagStatus();
        this.loadPanelState();  // Load saved state first
        this.initializeToggles();  // Then update UI to match the loaded state
        this.updateFigurePanel();  // Ensure figure panel shows correct state
        
        // Ensure proper desktop/mobile initialization
        if (window.innerWidth > 1024 && this.figurePanel) {
            // Desktop: ensure figure panel is visible
            this.figurePanel.classList.remove('open', 'closed');
        }
    }

    setupEventListeners() {
        // Chat form
        this.chatForm.addEventListener('submit', (e) => this.handleSubmit(e));
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSubmit(e);
            }
        });
        this.messageInput.addEventListener('input', () => this.autoResizeTextarea());

        // Mobile virtual keyboard handling
        this.setupMobileKeyboardHandling();

        // Control toggles
        this.ragToggleContainer.addEventListener('click', () => this.toggleRAG());
        this.thinkingToggleContainer.addEventListener('click', () => this.toggleThinking());
        if (this.queryAugmentationToggleContainer) {
            this.queryAugmentationToggleContainer.addEventListener('click', () => this.toggleQueryAugmentation());
        }
        this.figureSelect.addEventListener('change', (e) => this.handleFigureChange(e));
        
        // Source select - show/hide external API configuration
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
        
        // Model select - show/hide custom model name input for "Other"
        this.modelSelect.addEventListener('change', (e) => {
            if (e.target.value === 'Other') {
                this.customModelName.style.display = 'block';
                this.customModelName.value = '';
                this.customModelName.focus();
            } else {
                this.customModelName.style.display = 'none';
            }
        });
        
        // API Key input validation
        if (this.externalApiKey) {
            this.externalApiKey.addEventListener('input', (e) => {
                // Clear masked value when user starts typing
                if (this.externalApiKey.getAttribute('data-is-masked') === 'true') {
                    this.externalApiKey.value = '';
                    this.externalApiKey.removeAttribute('data-is-masked');
                    this.externalApiKey.setAttribute('placeholder', 'Enter your API key');
                }
                this.updateApiKeyStatus();
            });
        }
        
        // Thinking intensity selector
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
        
        // Save conversation button
        if (this.saveConversationBtn) {
            this.saveConversationBtn.addEventListener('click', () => this.saveConversation());
        }

        // Control panel toggle
        this.controlToggleBtn.addEventListener('click', () => this.toggleControlPanel());
        this.controlCloseBtn.addEventListener('click', () => this.closeControlPanel());
        
        // Figure panel toggle
        if (this.figureToggleBtn) {
            this.figureToggleBtn.addEventListener('click', () => this.toggleFigurePanel());
        }
        if (this.figureCloseBtn) {
            this.figureCloseBtn.addEventListener('click', () => this.closeFigurePanel());
        }
        
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
            // Ctrl/Cmd + / to toggle control panel
            if ((e.ctrlKey || e.metaKey) && e.key === '/') {
                e.preventDefault();
                this.toggleControlPanel();
            }
        });

        // Save panel state on visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.savePanelState();
            }
        });
    }

    getSelectedModelName() {
        // If "Other" is selected, use the custom input value
        if (this.modelSelect.value === 'Other') {
            return this.customModelName.value || 'GPT-5-mini';  // fallback
        }
        // Otherwise use the selected dropdown value
        return this.modelSelect.value || 'GPT-5-mini';
    }

    updateModelListForSource() {
        const source = this.currentSource;
        this.modelSelect.innerHTML = '';
        
        if (source === 'local') {
            // Show local models
            if (this.localModels && this.localModels.length > 0) {
                this.localModels.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    this.modelSelect.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No local models available';
                this.modelSelect.appendChild(option);
            }
            // Hide custom model name input for local
            if (this.customModelName) {
                this.customModelName.style.display = 'none';
            }
        } else {
            // Show external models
            if (this.externalModels && this.externalModels.length > 0) {
                // Use configured external models
                this.externalModels.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    this.modelSelect.appendChild(option);
                });
                // Add "Other" option for custom model
                const otherOption = document.createElement('option');
                otherOption.value = 'Other';
                otherOption.textContent = 'Other';
                this.modelSelect.appendChild(otherOption);
            } else {
                // No configured external models - fetch from external API or show defaults
                this.loadExternalModelsFromApi();
            }
        }
    }

    async loadExternalModelsFromApi() {
        // Try to fetch models from external API
        try {
            const apiUrl = this.externalApiUrl ? this.externalApiUrl.value : 'https://api.poe.com/v1';
            const apiKey = this.externalApiKey ? this.externalApiKey.value : '';
            
            const headers = { 'Content-Type': 'application/json' };
            if (apiKey && apiKey.trim()) {
                headers['Authorization'] = `Bearer ${apiKey}`;
            }
            
            const response = await fetch(`${apiUrl}/models`, { headers });
            if (response.ok) {
                const data = await response.json();
                const models = data.data || [];
                
                this.modelSelect.innerHTML = '';
                models.forEach(model => {
                    const modelId = model.id || model.name || model;
                    const option = document.createElement('option');
                    option.value = modelId;
                    option.textContent = modelId;
                    this.modelSelect.appendChild(option);
                });
                
                // Add "Other" option
                const otherOption = document.createElement('option');
                otherOption.value = 'Other';
                otherOption.textContent = 'Other';
                this.modelSelect.appendChild(otherOption);
                return;
            }
        } catch (e) {
            console.log('Could not fetch models from external API, using defaults');
        }
        
        // Fallback to default external models
        const defaultModels = [
            'GPT-5-mini',
            'GPT-5-nano',
            'GPT-4.1-mini',
            'Gemini-2.5-Flash',
            'Nova-Micro-1.0',
            'Grok-4-Fast-Non-Reasoning'
        ];
        
        this.modelSelect.innerHTML = '';
        defaultModels.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            this.modelSelect.appendChild(option);
        });
        
        // Add "Other" option
        const otherOption = document.createElement('option');
        otherOption.value = 'Other';
        otherOption.textContent = 'Other';
        this.modelSelect.appendChild(otherOption);
    }

    toggleControlPanel() {
        this.controlPanelOpen = !this.controlPanelOpen;
        
        if (this.controlPanelOpen) {
            this.controlPanel.classList.add('open');
            this.controlPanel.classList.remove('closed');
            this.controlToggleBtn.classList.add('panel-open');
            
            // Show overlay on mobile
            if (window.innerWidth <= 768) {
                this.overlay.classList.add('active');
            }
        } else {
            this.controlPanel.classList.remove('open');
            this.controlPanel.classList.add('closed');
            this.controlToggleBtn.classList.remove('panel-open');
            this.overlay.classList.remove('active');
        }
        
        // Save state
        this.savePanelState();
    }

    closeControlPanel() {
        this.controlPanelOpen = false;
        this.controlPanel.classList.remove('open');
        this.controlPanel.classList.add('closed');
        this.controlToggleBtn.classList.remove('panel-open');
        if (!this.figurePanelOpen) {
            this.overlay.classList.remove('active');
        }
        this.savePanelState();
    }

    toggleFigurePanel() {
        // Only toggle on mobile/tablet
        if (window.innerWidth > 1024) {
            return; // Figure panel is always visible on desktop
        }
        
        this.figurePanelOpen = !this.figurePanelOpen;
        
        if (this.figurePanelOpen) {
            this.figurePanel.classList.add('open');
            this.figurePanel.classList.remove('closed');
            this.figureToggleBtn.classList.add('panel-open');
            this.overlay.classList.add('active');
        } else {
            this.figurePanel.classList.remove('open');
            this.figurePanel.classList.add('closed');
            this.figureToggleBtn.classList.remove('panel-open');
            if (!this.controlPanelOpen) {
                this.overlay.classList.remove('active');
            }
        }
        
        // Save state
        this.savePanelState();
    }

    closeFigurePanel() {
        // Only close on mobile/tablet
        if (window.innerWidth > 1024) {
            return; // Figure panel is always visible on desktop
        }
        
        this.figurePanelOpen = false;
        this.figurePanel.classList.remove('open');
        this.figurePanel.classList.add('closed');
        this.figureToggleBtn.classList.remove('panel-open');
        if (!this.controlPanelOpen) {
            this.overlay.classList.remove('active');
        }
        this.savePanelState();
    }

    savePanelState() {
        localStorage.setItem('controlPanelOpen', this.controlPanelOpen);
        localStorage.setItem('figurePanelOpen', this.figurePanelOpen);
        localStorage.setItem('ragEnabled', this.ragEnabled);
        localStorage.setItem('thinkingVisible', this.thinkingVisible);
        localStorage.setItem('queryAugmentationEnabled', this.queryAugmentationEnabled);
        localStorage.setItem('thinkingIntensity', this.thinkingIntensity);
        localStorage.setItem('temperature', this.temperature);
    }

    loadPanelState() {
        // For debugging: uncomment the next line to reset to defaults
        // localStorage.clear();
        
        // Load panel open state (default closed on mobile, open on desktop)
        const savedPanelState = localStorage.getItem('controlPanelOpen');
        if (savedPanelState !== null) {
            this.controlPanelOpen = savedPanelState === 'true';
        } else {
            // Default: closed on mobile, open on desktop
            this.controlPanelOpen = window.innerWidth > 1024;
        }
        
        if (this.controlPanelOpen) {
            this.controlPanel.classList.add('open');
            this.controlPanel.classList.remove('closed');
            this.controlToggleBtn.classList.add('panel-open');
            if (window.innerWidth <= 768) {
                this.overlay.classList.add('active');
            }
        } else {
            this.controlPanel.classList.remove('open');
            this.controlPanel.classList.add('closed');
            this.controlToggleBtn.classList.remove('panel-open');
        }
        
        // Load figure panel state (only apply on mobile/tablet)
        if (window.innerWidth <= 1024) {
            const savedFigurePanelState = localStorage.getItem('figurePanelOpen');
            if (savedFigurePanelState !== null) {
                this.figurePanelOpen = savedFigurePanelState === 'true';
            } else {
                // Default: closed on mobile/tablet
                this.figurePanelOpen = false;
            }
            
            if (this.figurePanel) {
                if (this.figurePanelOpen) {
                    this.figurePanel.classList.add('open');
                    this.figurePanel.classList.remove('closed');
                    if (this.figureToggleBtn) {
                        this.figureToggleBtn.classList.add('panel-open');
                    }
                    this.overlay.classList.add('active');
                } else {
                    this.figurePanel.classList.remove('open');
                    this.figurePanel.classList.add('closed');
                    if (this.figureToggleBtn) {
                        this.figureToggleBtn.classList.remove('panel-open');
                    }
                }
            }
        } else {
            // On desktop, figure panel is always visible
            this.figurePanelOpen = true;
            if (this.figurePanel) {
                // Remove mobile classes on desktop
                this.figurePanel.classList.remove('open', 'closed');
            }
        }
        
        // Load toggle states (respecting config constraints)
        const savedRagState = localStorage.getItem('ragEnabled');
        if (savedRagState !== null && this.configRagEnabled) {
            this.ragEnabled = savedRagState === 'true';
        } else if (!this.configRagEnabled) {
            // Force off if config disables it
            this.ragEnabled = false;
        }
        
        const savedThinkingState = localStorage.getItem('thinkingVisible');
        if (savedThinkingState !== null) {
            this.thinkingVisible = savedThinkingState === 'true';
        } else {
            // If no saved state, ensure default is true (show thinking by default)
            this.thinkingVisible = true;
        }
        
        const savedQueryAugmentationState = localStorage.getItem('queryAugmentationEnabled');
        if (savedQueryAugmentationState !== null && this.configQueryAugmentationEnabled) {
            this.queryAugmentationEnabled = savedQueryAugmentationState === 'true';
        } else if (!this.configQueryAugmentationEnabled) {
            // Force off if config disables it
            this.queryAugmentationEnabled = false;
        } else {
            // If no saved state but config allows it, default to true
            this.queryAugmentationEnabled = true;
        }
        
        const savedThinkingIntensity = localStorage.getItem('thinkingIntensity');
        if (savedThinkingIntensity !== null) {
            this.thinkingIntensity = savedThinkingIntensity;
            if (this.thinkingIntensitySelect) {
                this.thinkingIntensitySelect.value = savedThinkingIntensity;
            }
        }
        
        const savedTemperature = localStorage.getItem('temperature');
        if (savedTemperature !== null) {
            this.temperature = parseFloat(savedTemperature);
            if (this.temperatureSlider) {
                this.temperatureSlider.value = this.temperature;
            }
            if (this.temperatureValue) {
                this.temperatureValue.textContent = this.temperature.toFixed(1);
            }
        }
    }

    autoResizeTextarea() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
    }

    setupMobileKeyboardHandling() {
        // Only apply mobile keyboard handling on touch devices
        if (!('ontouchstart' in window)) return;

        const inputContainer = document.querySelector('.chat-input-container');
        if (!inputContainer) return;

        // Handle virtual keyboard showing/hiding
        let initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        
        const handleViewportChange = () => {
            const currentViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
            const isInputFocused = document.activeElement === this.messageInput;

            // If the input is not focused, viewport changes are usually caused by the browser UI
            // (address bar show/hide, orientation changes). Don't move the composer in that case.
            if (!isInputFocused) {
                initialViewportHeight = currentViewportHeight;
                inputContainer.style.transform = 'translateY(0)';
                inputContainer.style.transition = 'transform 0.3s ease';
                return;
            }

            const heightDifference = initialViewportHeight - currentViewportHeight;
            
            // If viewport height decreased significantly (keyboard is likely open)
            if (heightDifference > 150) {
                // Ensure input container stays visible
                inputContainer.style.transform = `translateY(-${Math.max(0, heightDifference - 150)}px)`;
                inputContainer.style.transition = 'transform 0.3s ease';
            } else {
                // Reset position when keyboard is closed
                inputContainer.style.transform = 'translateY(0)';
                inputContainer.style.transition = 'transform 0.3s ease';
            }
        };

        // Use Visual Viewport API if available (modern browsers)
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', handleViewportChange);
        } else {
            // Fallback for older browsers
            window.addEventListener('resize', handleViewportChange);
        }

        // Handle input focus to ensure it's visible
        this.messageInput.addEventListener('focus', () => {
            // Capture the "no keyboard" baseline right before the keyboard resize happens
            initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
            setTimeout(() => {
                // Scroll the input into view
                this.messageInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300); // Delay to allow keyboard animation
        });

        // When focus is lost, ensure we reset any transform so the bar doesn't "float"
        this.messageInput.addEventListener('blur', () => {
            inputContainer.style.transform = 'translateY(0)';
            inputContainer.style.transition = 'transform 0.3s ease';
            initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        });

        // Prevent zoom on input focus (iOS Safari)
        this.messageInput.addEventListener('touchstart', (e) => {
            // Ensure input has minimum font size to prevent zoom
            if (this.messageInput.style.fontSize !== '16px') {
                this.messageInput.style.fontSize = '16px';
            }
        });
    }

    async checkHealth() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();
            
            if (data.status === 'healthy') {
                if (this.statusDot) {
                    this.statusDot.classList.add('connected');
                }
                if (this.statusText) {
                    this.statusText.textContent = 'Connected';
                }
            } else {
                if (this.statusDot) {
                    this.statusDot.classList.remove('connected');
                }
                if (this.statusText) {
                    this.statusText.textContent = 'Disconnected';
                }
            }
        } catch (error) {
            if (this.statusDot) {
                this.statusDot.classList.remove('connected');
            }
            if (this.statusText) {
                this.statusText.textContent = 'Error';
            }
        }
    }

    async loadModels() {
        try {
            const response = await fetch('/api/models-by-source');
            const data = await response.json();
            
            console.log('Models loaded from server:', data);
            
            // Store model lists
            this.localModels = data.local || [];
            this.externalModels = data.external;  // null means fetch dynamically
            
            console.log('Local models:', this.localModels);
            console.log('External models:', this.externalModels);
            
            // Set default source to external
            this.currentSource = 'external';
            if (this.modelSourceSelect) {
                this.modelSourceSelect.value = 'external';
            }
            
            // Update model list for current source
            this.updateModelListForSource();
            
            // Show external API config since it's the default
            if (this.externalApiConfig) {
                this.externalApiConfig.style.display = 'block';
            }
            this.loadExternalApiKeyStatus();
        } catch (error) {
            console.error('Failed to load models:', error);
            // Fallback to default behavior
            this.localModels = [];
            this.externalModels = null;
            this.updateModelListForSource();
        }
    }

    async loadExternalApiKeyStatus() {
        try {
            const response = await fetch('/api/external-api-key-status');
            const data = await response.json();
            
            // Only pre-populate if external source is selected and we have a pre-configured key
            if (this.currentSource === 'external' && data.has_key && data.masked_key) {
                // Pre-populate the API key field with masked value
                if (this.externalApiKey && !this.externalApiKey.value.trim()) {
                    this.externalApiKey.value = data.masked_key;
                    this.externalApiKey.setAttribute('data-is-masked', 'true');
                    this.externalApiKey.setAttribute('placeholder', 'Pre-configured API key (masked)');
                    
                    // Update status to show it's pre-configured
                    this.updateApiKeyStatus();
                    
                    // Add visual indicator that it's pre-configured
                    if (this.apiKeyStatus) {
                        this.apiKeyStatus.style.display = 'block';
                        this.apiKeyStatus.innerHTML = '<span style="color: #27ae60;">✓ Using pre-configured API key</span>';
                    }
                }
            }
        } catch (error) {
            console.error('Failed to load external API key status:', error);
        }
    }

    async loadFeatureFlags() {
        try {
            const response = await fetch('/api/feature-flags');
            const data = await response.json();
            
            this.configRagEnabled = data.rag_enabled;
            this.configQueryAugmentationEnabled = data.query_augmentation_enabled;
            this.queryAugmentationModel = data.query_augmentation_model || '';
            
            // If RAG is disabled in config, force user state to false
            if (!this.configRagEnabled) {
                this.ragEnabled = false;
            }
            
            // If query augmentation is disabled in config, force user state to false
            if (!this.configQueryAugmentationEnabled) {
                this.queryAugmentationEnabled = false;
            }
            
            // Update toggle UI based on config
            this.updateFeatureToggleStates();
            
        } catch (error) {
            console.error('Failed to load feature flags:', error);
        }
    }

    updateFeatureToggleStates() {
        // Update RAG toggle based on config
        const ragConfigDisabledLabel = document.getElementById('rag-config-disabled');
        if (this.ragToggleContainer) {
            if (!this.configRagEnabled) {
                this.ragToggleContainer.classList.add('disabled');
                this.ragToggleContainer.style.opacity = '0.5';
                this.ragToggleContainer.style.pointerEvents = 'none';
                this.ragToggleSwitch.classList.remove('active');
                this.ragToggleContainer.title = 'RAG is disabled in server configuration';
                if (ragConfigDisabledLabel) ragConfigDisabledLabel.style.display = 'inline';
            } else {
                this.ragToggleContainer.classList.remove('disabled');
                this.ragToggleContainer.style.opacity = '1';
                this.ragToggleContainer.style.pointerEvents = 'auto';
                this.ragToggleContainer.title = '';
                if (ragConfigDisabledLabel) ragConfigDisabledLabel.style.display = 'none';
            }
        }
        
        // Update Query Augmentation toggle based on config
        const qaConfigDisabledLabel = document.getElementById('query-augmentation-config-disabled');
        if (this.queryAugmentationToggleContainer) {
            if (!this.configQueryAugmentationEnabled) {
                this.queryAugmentationToggleContainer.classList.add('disabled');
                this.queryAugmentationToggleContainer.style.opacity = '0.5';
                this.queryAugmentationToggleContainer.style.pointerEvents = 'none';
                this.queryAugmentationToggleSwitch.classList.remove('active');
                this.queryAugmentationToggleContainer.title = 'Query augmentation is disabled in server configuration';
                if (qaConfigDisabledLabel) qaConfigDisabledLabel.style.display = 'inline';
                // Hide augmented query panel
                if (this.augmentedQueryPanel) {
                    this.augmentedQueryPanel.style.display = 'none';
                }
            } else {
                this.queryAugmentationToggleContainer.classList.remove('disabled');
                this.queryAugmentationToggleContainer.style.opacity = '1';
                this.queryAugmentationToggleContainer.style.pointerEvents = 'auto';
                this.queryAugmentationToggleContainer.title = '';
                if (qaConfigDisabledLabel) qaConfigDisabledLabel.style.display = 'none';
            }
        }
    }

    async loadFigures() {
        try {
            this.figureSelect.innerHTML = '<option value="">Loading figures...</option>';
            this.figureSelect.disabled = true;
            
            const response = await fetch('/api/figures');
            const figures = await response.json();
            
            this.figureSelect.innerHTML = '<option value="">General Chat</option>';
            
            figures.forEach(figure => {
                const option = document.createElement('option');
                option.value = figure.figure_id;
                option.textContent = `${figure.name} (${figure.document_count || 0} docs)`;
                this.figureSelect.appendChild(option);
            });
            
            this.figureSelect.disabled = false;
        } catch (error) {
            console.error('Failed to load figures:', error);
            this.figureSelect.innerHTML = '<option value="">Error loading figures</option>';
            this.figureSelect.disabled = false;
        }
    }

    async loadCurrentFigure() {
        try {
            // Always reset to General Chat on page load
            const resetResponse = await fetch('/api/figure/select', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ figure_id: null })
            });
            
            // Now set the UI to General Chat
            this.figureSelect.value = '';
            this.currentFigure = null;
            this.updateFigurePanel();
            this.updateRagStatus();
        } catch (error) {
            console.error('Failed to reset figure:', error);
        }
    }

    async handleFigureChange(e) {
        const figureId = e.target.value;
        
        try {
            const response = await fetch('/api/figure/select', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ figure_id: figureId || null })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.currentFigure = result.current_figure;
                this.updateFigurePanel();
                this.updateRagStatus();
                
                // Clear cached documents and sources when switching figures
                this.clearDocuments();
                this.currentSources = {};
                this.allRetrievedDocuments.clear();  // Clear all retrieved documents
                
                // Clear augmented query panel
                if (this.augmentedQueryPanel) {
                    this.augmentedQueryPanel.style.display = 'none';
                }
                if (this.augmentedQueryText) {
                    this.augmentedQueryText.textContent = '';
                }
                
                // Clear conversation history in the UI
                this.chatMessages.innerHTML = '';
            } else {
                console.error('Failed to select figure:', result.error);
            }
        } catch (error) {
            console.error('Error selecting figure:', error);
        }
    }

    updateFigurePanel() {
        // Check if figure panel elements exist
        if (!this.figureEmpty || !this.figureDisplayInfo) {
            return; // Figure panel elements not available
        }

        if (!this.currentFigure) {
            // No figure selected - show empty state
            this.figureEmpty.style.display = 'block';
            this.figureDisplayInfo.classList.remove('visible');
            return;
        }

        // Hide empty state and show figure info
        this.figureEmpty.style.display = 'none';
        this.figureDisplayInfo.classList.add('visible');

        // Update figure information
        const figure = this.currentFigure;
        
        // Set figure name
        if (figure.name && this.figureDisplayName) {
            this.figureDisplayName.textContent = figure.name;
        }

        // Set birth and death years (check both direct and nested metadata)
        if (this.figureYears) {
            const birthYear = figure.birth_year || (figure.metadata && figure.metadata.birth_year);
            const deathYear = figure.death_year || (figure.metadata && figure.metadata.death_year);
            if (birthYear || deathYear) {
                const birthDisplay = birthYear || '?';
                const deathDisplay = deathYear || '?';
                this.figureYears.textContent = `(${birthDisplay} - ${deathDisplay})`;
            } else {
                this.figureYears.textContent = '';
            }
        }

        // Set description
        if (figure.description && this.figureDisplayDescription) {
            this.figureDisplayDescription.textContent = figure.description;
        } else if (this.figureDisplayDescription) {
            this.figureDisplayDescription.textContent = '';
        }

        // Set personality prompt
        if (figure.personality_prompt && this.figureDisplayPersonality) {
            this.figureDisplayPersonality.textContent = figure.personality_prompt;
        } else if (this.figureDisplayPersonality) {
            this.figureDisplayPersonality.textContent = '';
        }

        // Set image if available (check both figure.image and figure.metadata.image for compatibility)
        const imageFile = figure.image || (figure.metadata && figure.metadata.image);
        if (imageFile && this.figureImage) {
            this.figureImage.src = `/figure_images/${imageFile}`;
            this.figureImage.style.display = 'block';
            this.figureImage.onerror = () => {
                this.figureImage.style.display = 'none';
            };
        } else if (this.figureImage) {
            this.figureImage.style.display = 'none';
        }
    }

    toggleRAG() {
        // Only allow toggle if config permits
        if (!this.configRagEnabled) {
            return;
        }
        
        this.ragEnabled = !this.ragEnabled;
        if (this.ragEnabled) {
            this.ragToggleSwitch.classList.add('active');
        } else {
            this.ragToggleSwitch.classList.remove('active');
        }
        this.savePanelState();
    }

    toggleThinking() {
        this.thinkingVisible = !this.thinkingVisible;
        if (this.thinkingVisible) {
            this.thinkingToggleSwitch.classList.add('active');
        } else {
            this.thinkingToggleSwitch.classList.remove('active');
        }
        this.updateThinkingVisibility();
        this.savePanelState();
    }

    toggleQueryAugmentation() {
        // Only allow toggle if config permits
        if (!this.configQueryAugmentationEnabled) {
            return;
        }
        
        this.queryAugmentationEnabled = !this.queryAugmentationEnabled;
        if (this.queryAugmentationEnabled) {
            this.queryAugmentationToggleSwitch.classList.add('active');
            // Restore panel if there's existing content
            if (this.augmentedQueryPanel && this.augmentedQueryText && this.augmentedQueryText.textContent) {
                this.augmentedQueryPanel.style.display = 'block';
            }
        } else {
            this.queryAugmentationToggleSwitch.classList.remove('active');
            // Hide augmented query panel when disabled
            if (this.augmentedQueryPanel) {
                this.augmentedQueryPanel.style.display = 'none';
            }
        }
        this.savePanelState();
    }

    updateAugmentedQuery(augmentedQuery) {
        if (!this.queryAugmentationEnabled || !augmentedQuery) {
            if (this.augmentedQueryPanel) {
                this.augmentedQueryPanel.style.display = 'none';
            }
            return;
        }
        
        if (this.augmentedQueryPanel && this.augmentedQueryText) {
            this.augmentedQueryText.textContent = augmentedQuery;
            this.augmentedQueryPanel.style.display = 'block';
            // Update model name in header
            if (this.augmentedQueryModelSpan && this.queryAugmentationModel) {
                this.augmentedQueryModelSpan.textContent = `(${this.queryAugmentationModel})`;
            }
        }
    }

    updateThinkingVisibility() {
        // Update visibility of thinking text, but keep indicators visible
        const thinkingTextElements = document.querySelectorAll('.thinking-text');
        thinkingTextElements.forEach(element => {
            if (this.thinkingVisible) {
                element.style.display = 'block';
            } else {
                element.style.display = 'none';
            }
        });
        
        // Update indicator text to reflect visibility state
        const thinkingIndicators = document.querySelectorAll('.thinking-indicator');
        thinkingIndicators.forEach(indicator => {
            if (indicator.textContent.includes('Thought process')) {
                indicator.innerHTML = '💭 Thought process' + (this.thinkingVisible ? ':' : ' (hidden)');
            }
        });
    }

    updateDocumentsVisibility() {
        // Documents panel is shown automatically when documents are retrieved
        // No toggle needed - visibility is based on k > 0 and having sources
    }

    initializeToggles() {
        // Update RAG toggle (respecting config)
        if (this.configRagEnabled && this.ragEnabled) {
            this.ragToggleSwitch.classList.add('active');
        } else {
            this.ragToggleSwitch.classList.remove('active');
        }
        
        // Update thinking toggle
        if (this.thinkingVisible) {
            this.thinkingToggleSwitch.classList.add('active');
        } else {
            this.thinkingToggleSwitch.classList.remove('active');
        }
        
        // Update query augmentation toggle (respecting config)
        if (this.queryAugmentationToggleSwitch) {
            if (this.configQueryAugmentationEnabled && this.queryAugmentationEnabled) {
                this.queryAugmentationToggleSwitch.classList.add('active');
            } else {
                this.queryAugmentationToggleSwitch.classList.remove('active');
            }
        }
        
        // Apply feature toggle states based on config
        this.updateFeatureToggleStates();
        
        // Ensure thinking visibility is applied
        this.updateThinkingVisibility();
    }

    handleSubmit(e) {
        e.preventDefault();
        if (this.isStreaming) return;
        const message = this.messageInput.value.trim();
        if (!message) return;
        
        // Check if External API is selected but no API key provided
        if (this.currentSource === 'external') {
            const apiKey = this.externalApiKey ? this.externalApiKey.value.trim() : '';
            const isMasked = this.externalApiKey && this.externalApiKey.getAttribute('data-is-masked') === 'true';
            // If no API key and it's not a masked pre-configured key, show warning
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

    addMessage(content, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        
        if (sender === 'user') {
            avatar.textContent = 'You';
        } else {
            // For AI messages, use figure image if available
            if (this.currentFigure && this.currentFigure.metadata && this.currentFigure.metadata.image) {
                const img = document.createElement('img');
                img.src = `/figure_images/${this.currentFigure.metadata.image}`;
                img.alt = this.currentFigure.name || 'AI';
                img.style.width = '100%';
                img.style.height = '100%';
                img.style.borderRadius = '50%';
                img.style.objectFit = 'cover';
                img.onerror = () => {
                    // Fallback to text if image fails to load
                    avatar.innerHTML = '';
                    avatar.textContent = 'AI';
                    console.error('Failed to load figure image in addMessage:', img.src);
                };
                avatar.appendChild(img);
            } else {
                avatar.textContent = 'AI';
            }
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (sender === 'user') {
            contentDiv.textContent = content;
        } else {
            if (content) {
                contentDiv.textContent = content;
            }
        }
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);
        
        // Store reference to the message div for later document association
        if (sender === 'assistant') {
            messageDiv.retrievedDocuments = [];  // Initialize empty, will be populated when response completes
        }
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        return contentDiv;
    }

    async sendMessage(message) {
        this.isStreaming = true;
        this.sendButton.disabled = true;
        this.sendButton.style.display = 'none';
        this.stopButton.style.display = 'inline-block';
        
        // Create abort controller for this request
        this.abortController = new AbortController();
        
        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    model: this.getSelectedModelName(),
                    use_rag: this.ragEnabled,
                    k: parseInt(this.docsCountSelect.value),
                    thinking_intensity: this.thinkingIntensity || 'normal',
                    temperature: this.temperature || 1.0,
                    query_augmentation: this.queryAugmentationEnabled,
                    // Include external API config if using external source
                    ...(this.currentSource === 'external' && {
                        external_config: {
                            base_url: this.externalApiUrl ? this.externalApiUrl.value : 'https://api.poe.com/v1',
                            model: this.getSelectedModelName(),
                            // If the API key is masked, send empty string (server will use pre-configured key)
                            api_key: this.externalApiKey && this.externalApiKey.getAttribute('data-is-masked') === 'true' ? '' : (this.externalApiKey ? this.externalApiKey.value : '')
                        }
                    })
                }),
                signal: this.abortController.signal
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            this.currentMessageElement = this.addMessage('', 'assistant');
            
            // Reset streaming state
            this.currentResponseElement = null;
            this.currentResponseContent = '';
            this.paragraphBuffer = '';
            this.responseContentElement = null;
            this.isInThinking = false;
            this.thinkingContent = '';
            this.currentThinkingElement = null;
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let fullContent = '';
            
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) break;
                
                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            if (data.error) {
                                // Check if it's an API key related error
                                const errorMsg = data.error.toLowerCase();
                                if (this.currentSource === 'external' && 
                                    (errorMsg.includes('api key') || 
                                     errorMsg.includes('unauthorized') || 
                                     errorMsg.includes('401') ||
                                     errorMsg.includes('authentication'))) {
                                    this.showApiKeyWarning('Invalid or missing API key. Please check your API key and try again.');
                                } else {
                                    throw new Error(data.error);
                                }
                                return;
                            }
                            
                            if (data.augmented_query) {
                                this.updateAugmentedQuery(data.augmented_query);
                            }
                            
                            if (data.sources) {
                                this.addSources(data.sources);
                            }
                            
                            if (data.content) {
                                fullContent += data.content;
                                this.processStreamingContent(data.content);
                                this.scrollToBottom();
                            }
                            
                            if (data.done) {
                                await this.processFinalContent();
                                break;
                            }
                        } catch (e) {
                            console.error('Error parsing SSE data:', e);
                        }
                    }
                }
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.log('Request was cancelled');
                // Add a message indicating generation was stopped
                const stoppedMsg = document.createElement('div');
                stoppedMsg.style.color = '#e74c3c';
                stoppedMsg.style.fontStyle = 'italic';
                stoppedMsg.style.fontSize = '0.9em';
                stoppedMsg.style.marginTop = '8px';
                stoppedMsg.textContent = '(Generation stopped by user)';
                if (this.currentMessageElement) {
                    this.currentMessageElement.appendChild(stoppedMsg);
                }
            } else {
                console.error('Error in sendMessage:', error);
                this.showError(`Error: ${error.message}`);
            }
        } finally {
            this.isStreaming = false;
            this.sendButton.disabled = false;
            this.sendButton.style.display = 'inline-block';
            this.stopButton.style.display = 'none';
            this.abortController = null;
        }
    }

    processStreamingContent(content) {
        // Check for thinking tags
        let processedContent = content;
        let remainingContent = content;
        
        // Process thinking tags
        while (remainingContent.includes('<think>') || remainingContent.includes('</think>')) {
            if (!this.isInThinking && remainingContent.includes('<think>')) {
                const thinkStart = remainingContent.indexOf('<think>');
                if (thinkStart !== -1) {
                    // Add content before thinking tag
                    const beforeThink = remainingContent.substring(0, thinkStart);
                    if (beforeThink) {
                        this.addToResponseBuffer(beforeThink);
                    }
                    
                    // Start thinking mode
                    this.isInThinking = true;
                    
                    // Create thinking container
                    this.currentThinkingElement = document.createElement('div');
                    this.currentThinkingElement.className = 'thinking-content';
                    
                    // Create thinking indicator (always visible)
                    const thinkingIndicator = document.createElement('div');
                    thinkingIndicator.className = 'thinking-indicator';
                    thinkingIndicator.innerHTML = '💭 Thinking...';
                    thinkingIndicator.style.fontSize = '0.9em';
                    thinkingIndicator.style.color = '#7dd3fc';
                    thinkingIndicator.style.fontStyle = 'italic';
                    thinkingIndicator.style.marginBottom = '8px';
                    
                    // Create thinking text container
                    this.thinkingTextElement = document.createElement('div');
                    this.thinkingTextElement.className = 'thinking-text';
                    if (!this.thinkingVisible) {
                        this.thinkingTextElement.style.display = 'none';
                    }
                    
                    this.currentThinkingElement.appendChild(thinkingIndicator);
                    this.currentThinkingElement.appendChild(this.thinkingTextElement);
                    this.currentMessageElement.appendChild(this.currentThinkingElement);
                    this.thinkingBuffer = '';
                    
                    remainingContent = remainingContent.substring(thinkStart + 7);
                }
            } else if (this.isInThinking && remainingContent.includes('</think>')) {
                const thinkEnd = remainingContent.indexOf('</think>');
                if (thinkEnd !== -1) {
                    // Add thinking content
                    const thinkContent = remainingContent.substring(0, thinkEnd);
                    this.thinkingBuffer += thinkContent;
                    if (this.thinkingTextElement) {
                        this.thinkingTextElement.textContent = this.thinkingBuffer;
                    }
                    
                    // Update indicator to show thinking is complete
                    const indicator = this.currentThinkingElement?.querySelector('.thinking-indicator');
                    if (indicator && this.thinkingBuffer.trim()) {
                        indicator.innerHTML = '💭 Thought process' + (this.thinkingVisible ? ':' : ' (hidden)');
                    } else if (indicator && !this.thinkingBuffer.trim()) {
                        // If thinking was empty, hide the whole thinking element
                        this.currentThinkingElement.style.display = 'none';
                    }
                    
                    // End thinking mode
                    this.isInThinking = false;
                    this.currentThinkingElement = null;
                    this.thinkingTextElement = null;
                    this.thinkingBuffer = '';
                    
                    remainingContent = remainingContent.substring(thinkEnd + 8);
                }
            } else {
                // No more tags to process
                if (this.isInThinking) {
                    // Add to thinking buffer
                    this.thinkingBuffer += remainingContent;
                    if (this.thinkingTextElement) {
                        this.thinkingTextElement.textContent = this.thinkingBuffer;
                    }
                } else {
                    // Add to response buffer
                    this.addToResponseBuffer(remainingContent);
                }
                break;
            }
        }
        
        // If no tags, just add to appropriate buffer
        if (!remainingContent.includes('<think>') && !remainingContent.includes('</think>')) {
            if (this.isInThinking) {
                this.thinkingBuffer = (this.thinkingBuffer || '') + remainingContent;
                if (this.thinkingTextElement) {
                    this.thinkingTextElement.textContent = this.thinkingBuffer;
                }
            } else {
                this.addToResponseBuffer(remainingContent);
            }
        }
    }
    
    addToResponseBuffer(content) {
        if (!this.responseContentElement) {
            this.responseContentElement = document.createElement('div');
            this.responseContentElement.className = 'response-text';
            this.currentMessageElement.appendChild(this.responseContentElement);
        }
        
        this.paragraphBuffer = (this.paragraphBuffer || '') + content;
        // Apply basic formatting and display as HTML
        const formattedContent = this.applyBasicFormatting(this.paragraphBuffer);
        this.responseContentElement.innerHTML = formattedContent;
    }

    applyBasicFormatting(text) {
        if (!text) return '';
        
        // Escape HTML to prevent XSS
        let formatted = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
        
        // Apply basic markdown-style formatting
        formatted = formatted
            // Bold: **text** or *text* (only if not already in HTML tags)
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*\s][^*]*[^*\s])\*/g, '<strong>$1</strong>')
            .replace(/\*([^*\s])\*/g, '<strong>$1</strong>')
            // Italic: _text_
            .replace(/_([^_\s][^_]*[^_\s])_/g, '<em>$1</em>')
            .replace(/_([^_\s])_/g, '<em>$1</em>')
            // Line breaks
            .replace(/\n/g, '<br>');
        
        return formatted;
    }

    async processFinalContent() {
        // Final processing of content
        if (this.paragraphBuffer.trim()) {
            // Could add markdown processing here if needed
            this.scrollToBottom();
        }
        
        // Associate retrieved documents with the current assistant message
        if (this.currentMessageElement && this.currentMessageDocuments.length > 0) {
            const messageDiv = this.currentMessageElement.parentElement;
            if (messageDiv && messageDiv.classList.contains('assistant')) {
                messageDiv.retrievedDocuments = [...this.currentMessageDocuments];
            }
        }
    }

    addSources(sources) {
        if (!sources || sources.length === 0) return;
        
        this.currentSources = {};
        this.currentMessageDocuments = [];  // Reset for new message
        
        sources.forEach(source => {
            this.currentSources[source.doc_id] = source;
            
            // Store document for the current message
            this.currentMessageDocuments.push({
                ...source,
                timestamp: new Date().toISOString()
            });
            
            // Store document in our global tracking Map with a unique key
            const uniqueKey = `${source.filename}_${source.chunk_id || source.document_id || source.doc_id}`;
            if (!this.allRetrievedDocuments.has(uniqueKey)) {
                this.allRetrievedDocuments.set(uniqueKey, {
                    ...source,
                    timestamp: new Date().toISOString()
                });
            }
        });
        
        this.clearDocuments();
        // Show documents panel automatically when documents are retrieved
        this.documentsPanel.classList.add('visible');
        this.documentsEmpty.style.display = 'none';
        
        sources.forEach((source) => {
            const documentItem = document.createElement('div');
            documentItem.className = 'document-item';
            documentItem.onclick = () => this.showSourceModal(source);
            
            const filename = document.createElement('div');
            filename.style.fontWeight = '600';
            filename.style.color = '#7dd3fc';
            filename.style.marginBottom = '8px';
            const docId = source.document_id || source.doc_id || source.chunk_id || 'unknown';
            filename.textContent = `${docId}: ${source.filename}`;
            
            const preview = document.createElement('div');
            preview.style.color = '#a8c5d9';
            preview.style.fontSize = '0.85rem';
            preview.style.marginBottom = '8px';
            preview.textContent = source.text;
            
            // Cosine similarity
            const cosineDiv = document.createElement('div');
            cosineDiv.style.fontSize = '0.75rem';
            cosineDiv.style.color = '#4CAF50';
            cosineDiv.style.marginBottom = '4px';
            const cosineSimilarity = source.cosine_similarity || source.similarity || 0;
            const cosinePercent = Math.round(cosineSimilarity * 100);
            cosineDiv.textContent = `Match (cosine): ${cosinePercent}%`;
            
            // Top matching words from BM25
            const keywordsDiv = document.createElement('div');
            keywordsDiv.style.fontSize = '0.75rem';
            keywordsDiv.style.color = '#FF9800';
            const topWords = source.top_matching_words || [];
            if (topWords.length > 0) {
                keywordsDiv.textContent = `Keywords: ${topWords.join(', ')}`;
            } else {
                keywordsDiv.textContent = 'Keywords: none';
            }
            
            documentItem.appendChild(filename);
            documentItem.appendChild(preview);
            documentItem.appendChild(cosineDiv);
            documentItem.appendChild(keywordsDiv);
            
            this.documentsContent.appendChild(documentItem);
        });
    }

    clearDocuments() {
        const documentItems = this.documentsContent.querySelectorAll('.document-item');
        documentItems.forEach(item => item.remove());
        
        // Hide documents panel when cleared
        this.documentsPanel.classList.remove('visible');
        this.documentsEmpty.style.display = 'block';
    }

    showSourceModal(source) {
        const chunkId = source.document_id || source.chunk_id || 'unknown';
        this.sourceModalTitle.textContent = `${source.filename} - Chunk ${chunkId}`;
        this.sourceModalText.textContent = source.full_text || source.text;
        this.sourceModal.style.display = 'block';
    }

    closeSourceModal() {
        this.sourceModal.style.display = 'none';
    }

    showDocumentModal(docId) {
        const source = this.currentSources[docId];
        if (source) {
            this.showSourceModal(source);
        } else {
            console.warn(`Document ${docId} not found in current sources`);
        }
    }

    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.style.background = '#e74c3c';
        errorDiv.style.color = 'white';
        errorDiv.style.padding = '12px 16px';
        errorDiv.style.borderRadius = '8px';
        errorDiv.style.margin = '10px 0';
        errorDiv.style.textAlign = 'center';
        errorDiv.textContent = message;
        this.chatMessages.appendChild(errorDiv);
        this.scrollToBottom();
    }

    showApiKeyWarning(message) {
        const warningDiv = document.createElement('div');
        warningDiv.style.background = '#f39c12';
        warningDiv.style.color = 'white';
        warningDiv.style.padding = '12px 16px';
        warningDiv.style.borderRadius = '8px';
        warningDiv.style.margin = '10px 0';
        warningDiv.style.textAlign = 'center';
        warningDiv.style.fontSize = '14px';
        warningDiv.innerHTML = `<strong>⚠️ API Key Required</strong><br>${message}`;
        this.chatMessages.appendChild(warningDiv);
        this.scrollToBottom();
        
        // Auto-remove warning after 5 seconds
        setTimeout(() => {
            if (warningDiv.parentNode) {
                warningDiv.parentNode.removeChild(warningDiv);
            }
        }, 5000);
    }

    updateApiKeyStatus() {
        if (!this.apiKeyStatus || !this.externalApiKey) return;
        
        const apiKey = this.externalApiKey.value.trim();
        const isExternalSelected = this.currentSource === 'external';
        const isMasked = this.externalApiKey.getAttribute('data-is-masked') === 'true';
        
        if (isExternalSelected) {
            if (isMasked) {
                this.apiKeyStatus.style.display = 'block';
                this.apiKeyStatus.innerHTML = '<span style="color: #27ae60;">✓ Using pre-configured API key</span>';
            } else if (!apiKey) {
                this.apiKeyStatus.style.display = 'block';
                this.apiKeyStatus.innerHTML = '<span style="color: #e74c3c;">⚠️ API key is required to use External API</span>';
            } else if (apiKey.length < 10) {
                this.apiKeyStatus.style.display = 'block';
                this.apiKeyStatus.innerHTML = '<span style="color: #f39c12;">⚠️ API key seems too short</span>';
            } else {
                this.apiKeyStatus.style.display = 'block';
                this.apiKeyStatus.innerHTML = '<span style="color: #27ae60;">✓ API key provided</span>';
            }
        } else {
            this.apiKeyStatus.style.display = 'none';
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    stopGeneration() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    async updateRagStatus() {
        try {
            if (this.currentFigure) {
                const figureId = this.currentFigure.figure_id || this.currentFigure;
                const response = await fetch(`/api/figure/${figureId}`);
                if (response.ok) {
                    const figure = await response.json();
                    const docCount = figure.document_count || 0;
                    this.ragStatus.textContent = `${docCount} docs`;
                    this.ragStatus.style.color = docCount > 0 ? '#27ae60' : '#a8c5d9';
                } else {
                    this.ragStatus.textContent = '0 docs';
                    this.ragStatus.style.color = '#a8c5d9';
                }
            } else {
                this.ragStatus.textContent = 'No Figure';
                this.ragStatus.style.color = '#a8c5d9';
            }
        } catch (error) {
            console.error('Error fetching RAG stats:', error);
            this.ragStatus.textContent = 'Error';
            this.ragStatus.style.color = '#e74c3c';
        }
    }
    
    async saveConversation() {
        try {
            // Disable button while saving
            if (this.saveConversationBtn) {
                this.saveConversationBtn.disabled = true;
                this.saveConversationBtn.textContent = 'Saving...';
            }
            
            // Collect all messages
            const messages = [];
            const messageElements = this.chatMessages.querySelectorAll('.message');
            
            messageElements.forEach(msgElement => {
                const isUser = msgElement.classList.contains('user');
                const contentElement = msgElement.querySelector('.message-content');
                
                if (contentElement) {
                    // Get text content, preserving line breaks
                    let content;
                    if (isUser) {
                        content = contentElement.textContent.trim();
                    } else {
                        // For assistant messages, get HTML and convert <br> tags to newlines
                        const htmlContent = contentElement.innerHTML;
                        content = htmlContent
                            .replace(/<br\s*\/?>/gi, '\n')  // Convert <br> tags to newlines
                            .replace(/<[^>]*>/g, '')        // Strip other HTML tags
                            .replace(/&amp;/g, '&')        // Decode HTML entities
                            .replace(/&lt;/g, '<')
                            .replace(/&gt;/g, '>')
                            .replace(/&quot;/g, '"')
                            .replace(/&#x27;/g, "'")
                            .trim();
                    }
                    
                    if (content) {
                        const message = {
                            role: isUser ? 'user' : 'assistant',
                            content: content,
                            timestamp: new Date().toISOString()
                        };
                        
                        // Add retrieved documents for assistant messages
                        if (!isUser && msgElement.retrievedDocuments && msgElement.retrievedDocuments.length > 0) {
                            message.retrieved_documents = msgElement.retrievedDocuments;
                        }
                        
                        messages.push(message);
                    }
                }
            });
            
            // Get current figure name if selected
            const figureNameWithDocs = this.figureSelect.selectedOptions[0]?.text || 'General Chat';
            
            // Extract clean figure name without document count
            const cleanFigureName = figureNameWithDocs.split(' (')[0];
            
            // Extract document count if present
            const docCountMatch = figureNameWithDocs.match(/\((\d+) docs?\)/);
            const documentCount = docCountMatch ? docCountMatch[1] : '0';
            
            // Get figure description data if available
            let figureData = null;
            if (this.currentFigure) {
                figureData = {
                    name: this.currentFigure.name,
                    birth_year: this.currentFigure.birth_year,
                    death_year: this.currentFigure.death_year,
                    description: this.currentFigure.description,
                    personality_prompt: this.currentFigure.personality_prompt
                };
            }

            // Create conversation data
            const conversationData = {
                title: `Chat with ${cleanFigureName}`,
                date: new Date().toLocaleString(),
                messages: messages,  // Messages now include per-response retrieved documents
                figure: cleanFigureName,
                figure_name: cleanFigureName,
                figure_data: figureData,
                document_count: documentCount,
                model: this.getSelectedModelName(),
                temperature: this.temperature.toString(),
                thinking_enabled: this.thinkingVisible,
                rag_enabled: this.ragEnabled,
                retrieved_documents: []  // Keep empty since documents are now per-message
            };
            
            // Send to server to generate PDF
            const response = await fetch('/api/export/pdf', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(conversationData)
            });
            
            if (response.ok) {
                // Get the PDF blob
                const blob = await response.blob();
                
                // Create download link
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `chat_${cleanFigureName.replace(/[^a-z0-9]/gi, '_')}_${Date.now()}.pdf`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                
                // Show success feedback
                if (this.saveConversationBtn) {
                    this.saveConversationBtn.textContent = 'Saved!';
                    setTimeout(() => {
                        this.saveConversationBtn.textContent = 'Save';
                    }, 2000);
                }
            } else {
                throw new Error('Failed to generate PDF');
            }
            
        } catch (error) {
            console.error('Error saving conversation:', error);
            
            // Show error feedback
            if (this.saveConversationBtn) {
                this.saveConversationBtn.textContent = 'Error';
                setTimeout(() => {
                    this.saveConversationBtn.textContent = 'Save';
                }, 2000);
            }
        } finally {
            if (this.saveConversationBtn) {
                this.saveConversationBtn.disabled = false;
            }
        }
    }
}

// Handle window resize
window.addEventListener('resize', () => {
    const app = window.chatApp;
    if (!app) return;
    
    if (window.innerWidth > 1024) {
        // Desktop view
        const overlay = document.getElementById('overlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
        
        // Remove mobile classes from figure panel on desktop
        if (app.figurePanel) {
            app.figurePanel.classList.remove('open', 'closed');
        }
        
        // Hide toggle button on desktop
        if (app.figureToggleBtn) {
            app.figureToggleBtn.style.display = 'none';
        }
    } else {
        // Mobile/tablet view
        // Show toggle button on mobile
        if (app.figureToggleBtn) {
            app.figureToggleBtn.style.display = '';
        }
        
        // Apply mobile state to figure panel
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

// Initialize the chat app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});
