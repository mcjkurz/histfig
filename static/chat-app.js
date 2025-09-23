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
        this.documentsToggleContainer = document.getElementById('documents-toggle-container');
        this.documentsToggleSwitch = document.getElementById('documents-toggle-switch');
        this.docsCountSelect = document.getElementById('docs-count-select');
        this.thinkingIntensitySelect = document.getElementById('thinking-intensity-select');
        this.stopButton = document.getElementById('stop-button');
        this.temperatureSlider = document.getElementById('temperature-slider');
        this.temperatureValue = document.getElementById('temperature-value');
        this.saveConversationBtn = document.getElementById('save-conversation-btn');
        
        // Control panel elements
        this.controlPanel = document.getElementById('control-panel');
        this.controlToggleBtn = document.getElementById('control-toggle-btn');
        this.controlCloseBtn = document.getElementById('control-close-btn');
        this.overlay = document.getElementById('overlay');
        
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
        this.documentsVisible = true;
        this.controlPanelOpen = false;
        this.thinkingIntensity = 'normal';
        this.temperature = 1.0;  // Default temperature
        this.abortController = null;
        
        this.init();
    }

    async init() {
        this.setupEventListeners();
        this.checkHealth();
        this.loadModels();
        this.loadFigures();
        await this.loadCurrentFigure();
        this.autoResizeTextarea();
        this.updateRagStatus();
        this.loadPanelState();  // Load saved state first
        this.initializeToggles();  // Then update UI to match the loaded state
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

        // Control toggles
        this.ragToggleContainer.addEventListener('click', () => this.toggleRAG());
        this.thinkingToggleContainer.addEventListener('click', () => this.toggleThinking());
        this.documentsToggleContainer.addEventListener('click', () => this.toggleDocuments());
        this.figureSelect.addEventListener('change', (e) => this.handleFigureChange(e));
        
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
        this.overlay.addEventListener('click', () => this.closeControlPanel());

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
        this.overlay.classList.remove('active');
        this.savePanelState();
    }

    savePanelState() {
        localStorage.setItem('controlPanelOpen', this.controlPanelOpen);
        localStorage.setItem('ragEnabled', this.ragEnabled);
        localStorage.setItem('thinkingVisible', this.thinkingVisible);
        localStorage.setItem('documentsVisible', this.documentsVisible);
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
        
        // Load toggle states
        const savedRagState = localStorage.getItem('ragEnabled');
        if (savedRagState !== null) {
            this.ragEnabled = savedRagState === 'true';
        }
        
        const savedThinkingState = localStorage.getItem('thinkingVisible');
        if (savedThinkingState !== null) {
            this.thinkingVisible = savedThinkingState === 'true';
        } else {
            // If no saved state, ensure default is true (show thinking by default)
            this.thinkingVisible = true;
        }
        
        const savedDocumentsState = localStorage.getItem('documentsVisible');
        if (savedDocumentsState !== null) {
            this.documentsVisible = savedDocumentsState === 'true';
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

    async checkHealth() {
        try {
            const response = await fetch('/api/health');
            const data = await response.json();
            
            if (data.status === 'healthy') {
                this.statusDot.classList.add('connected');
                this.statusText.textContent = 'Connected';
            } else {
                this.statusDot.classList.remove('connected');
                this.statusText.textContent = 'Disconnected';
            }
        } catch (error) {
            this.statusDot.classList.remove('connected');
            this.statusText.textContent = 'Error';
        }
    }

    async loadModels() {
        try {
            const response = await fetch('/api/models');
            const models = await response.json();
            
            this.modelSelect.innerHTML = '';
            let defaultModelFound = false;
            
            models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                this.modelSelect.appendChild(option);
                
                // Check for preferred default model (exactly qwen3:30b)
                if (model === 'qwen3:30b') {
                    this.modelSelect.value = model;
                    defaultModelFound = true;
                }
            });
            
            // If qwen3:30b not found, just use the first available model
            if (!defaultModelFound && models.length > 0) {
                this.modelSelect.value = models[0];
            }
        } catch (error) {
            console.error('Failed to load models:', error);
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
            const response = await fetch('/api/figure/current');
            const current = await response.json();
            
            if (current.figure_id) {
                this.figureSelect.value = current.figure_id;
                this.currentFigure = current.figure_id;
                this.updateRagStatus();
            } else {
                this.figureSelect.value = '';
                this.currentFigure = null;
            }
        } catch (error) {
            console.error('Failed to load current figure:', error);
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
                this.updateWelcomeMessage(result.current_figure, result.figure_name);
                this.updateRagStatus();
            } else {
                console.error('Failed to select figure:', result.error);
            }
        } catch (error) {
            console.error('Error selecting figure:', error);
        }
    }

    updateWelcomeMessage(currentFigure, figureName) {
        const firstAssistantMessage = this.chatMessages.querySelector('.message.assistant .message-content');
        if (firstAssistantMessage) {
            if (currentFigure) {
                firstAssistantMessage.textContent = `Hello! I am ${figureName}. How may I help you today?`;
                this.figureInfo.style.display = 'none';
            } else {
                firstAssistantMessage.textContent = "Hello! I'm your AI assistant powered by Ollama. How can I help you today?";
                this.figureInfo.style.display = 'none';
            }
        }
    }

    toggleRAG() {
        this.ragEnabled = !this.ragEnabled;
        if (this.ragEnabled) {
            this.ragToggleSwitch.classList.add('active');
        } else {
            this.ragToggleSwitch.classList.remove('active');
        }
        this.updateDocumentsVisibility();
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

    toggleDocuments() {
        this.documentsVisible = !this.documentsVisible;
        if (this.documentsVisible) {
            this.documentsToggleSwitch.classList.add('active');
            this.documentsPanel.classList.add('visible');
        } else {
            this.documentsToggleSwitch.classList.remove('active');
            this.documentsPanel.classList.remove('visible');
        }
        this.savePanelState();
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
        if (this.ragEnabled) {
            if (this.documentsVisible) {
                this.documentsPanel.classList.add('visible');
            }
        } else {
            this.documentsPanel.classList.remove('visible');
        }
    }

    initializeToggles() {
        // Update RAG toggle
        if (this.ragEnabled) {
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
        
        // Update documents toggle
        if (this.documentsVisible) {
            this.documentsToggleSwitch.classList.add('active');
            this.documentsPanel.classList.add('visible');
        } else {
            this.documentsToggleSwitch.classList.remove('active');
            this.documentsPanel.classList.remove('visible');
        }
        
        // Ensure thinking visibility is applied
        this.updateThinkingVisibility();
    }

    handleSubmit(e) {
        e.preventDefault();
        if (this.isStreaming) return;
        const message = this.messageInput.value.trim();
        if (!message) return;
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
        avatar.textContent = sender === 'user' ? 'You' : 'AI';
        
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
                    model: this.modelSelect.value,
                    use_rag: this.ragEnabled,
                    k: parseInt(this.docsCountSelect.value),
                    thinking_intensity: this.thinkingIntensity || 'normal',
                    temperature: this.temperature || 1.0
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
                                throw new Error(data.error);
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
        this.responseContentElement.textContent = this.paragraphBuffer;
    }

    async processFinalContent() {
        // Final processing of content
        if (this.paragraphBuffer.trim()) {
            // Could add markdown processing here if needed
            this.scrollToBottom();
        }
    }

    addSources(sources) {
        if (!sources || sources.length === 0) return;
        
        this.currentSources = {};
        sources.forEach(source => {
            this.currentSources[source.doc_id] = source;
        });
        
        this.clearDocuments();
        this.updateDocumentsVisibility();
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
            
            const similarity = document.createElement('div');
            similarity.style.fontSize = '0.75rem';
            similarity.style.color = '#999';
            const similarityPercent = Math.round(source.similarity * 100);
            similarity.textContent = `${similarityPercent}% match`;
            
            documentItem.appendChild(filename);
            documentItem.appendChild(preview);
            documentItem.appendChild(similarity);
            
            this.documentsContent.appendChild(documentItem);
        });
    }

    clearDocuments() {
        const documentItems = this.documentsContent.querySelectorAll('.document-item');
        documentItems.forEach(item => item.remove());
        
        if (this.documentsContent.children.length === 1) {
            this.documentsEmpty.style.display = 'block';
        } else {
            this.documentsEmpty.style.display = 'none';
        }
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
                const response = await fetch(`/api/figure/${this.currentFigure}`);
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
                    // Get text content
                    let content = contentElement.textContent.trim();
                    
                    if (content) {
                        messages.push({
                            role: isUser ? 'user' : 'assistant',
                            content: content,
                            timestamp: new Date().toISOString()
                        });
                    }
                }
            });
            
            // Get current figure name if selected
            const figureName = this.figureSelect.selectedOptions[0]?.text || 'General Chat';
            
            // Create conversation data
            const conversationData = {
                title: `Chat with ${figureName}`,
                date: new Date().toLocaleString(),
                messages: messages,
                figure: figureName,
                figure_name: figureName,
                model: this.modelSelect.value,
                temperature: this.temperature.toString(),
                thinking_enabled: this.thinkingVisible,
                rag_enabled: this.ragEnabled
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
                a.download = `chat_${figureName.replace(/[^a-z0-9]/gi, '_')}_${Date.now()}.pdf`;
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
    // Close overlay on desktop resize
    if (window.innerWidth > 768) {
        const overlay = document.getElementById('overlay');
        if (overlay) {
            overlay.classList.remove('active');
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
