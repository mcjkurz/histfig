/**
 * UI interaction methods for ChatApp
 * Handles panels, toggles, modals, streaming content, and formatting
 */

// Panel Management
ChatApp.prototype.toggleControlPanel = function() {
    this.controlPanelOpen = !this.controlPanelOpen;
    
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
        this.overlay.classList.remove('active');
    }
    
    this.savePanelState();
};

ChatApp.prototype.closeControlPanel = function() {
    this.controlPanelOpen = false;
    this.controlPanel.classList.remove('open');
    this.controlPanel.classList.add('closed');
    this.controlToggleBtn.classList.remove('panel-open');
    if (!this.figurePanelOpen) {
        this.overlay.classList.remove('active');
    }
    this.savePanelState();
};

ChatApp.prototype.toggleFigurePanel = function() {
    if (window.innerWidth > 1024) return;
    
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
    
    this.savePanelState();
};

ChatApp.prototype.closeFigurePanel = function() {
    if (window.innerWidth > 1024) return;
    
    this.figurePanelOpen = false;
    this.figurePanel.classList.remove('open');
    this.figurePanel.classList.add('closed');
    this.figureToggleBtn.classList.remove('panel-open');
    if (!this.controlPanelOpen) {
        this.overlay.classList.remove('active');
    }
    this.savePanelState();
};

// State Persistence
ChatApp.prototype.savePanelState = function() {
    localStorage.setItem('controlPanelOpen', this.controlPanelOpen);
    localStorage.setItem('figurePanelOpen', this.figurePanelOpen);
    localStorage.setItem('ragEnabled', this.ragEnabled);
    localStorage.setItem('thinkingVisible', this.thinkingVisible);
    localStorage.setItem('queryAugmentationEnabled', this.queryAugmentationEnabled);
    localStorage.setItem('thinkingIntensity', this.thinkingIntensity);
    localStorage.setItem('temperature', this.temperature);
};

ChatApp.prototype.loadPanelState = function() {
    const savedPanelState = localStorage.getItem('controlPanelOpen');
    if (savedPanelState !== null) {
        this.controlPanelOpen = savedPanelState === 'true';
    } else {
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
    
    if (window.innerWidth <= 1024) {
        const savedFigurePanelState = localStorage.getItem('figurePanelOpen');
        if (savedFigurePanelState !== null) {
            this.figurePanelOpen = savedFigurePanelState === 'true';
        } else {
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
        this.figurePanelOpen = true;
        if (this.figurePanel) {
            this.figurePanel.classList.remove('open', 'closed');
        }
    }
    
    // Load toggle states
    const savedRagState = localStorage.getItem('ragEnabled');
    if (savedRagState !== null && this.configRagEnabled) {
        this.ragEnabled = savedRagState === 'true';
    } else if (!this.configRagEnabled) {
        this.ragEnabled = false;
    }
    
    const savedThinkingState = localStorage.getItem('thinkingVisible');
    if (savedThinkingState !== null) {
        this.thinkingVisible = savedThinkingState === 'true';
    } else {
        this.thinkingVisible = true;
    }
    
    const savedQueryAugmentationState = localStorage.getItem('queryAugmentationEnabled');
    if (savedQueryAugmentationState !== null && this.configQueryAugmentationEnabled) {
        this.queryAugmentationEnabled = savedQueryAugmentationState === 'true';
    } else if (!this.configQueryAugmentationEnabled) {
        this.queryAugmentationEnabled = false;
    } else {
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
};

// Input Handling
ChatApp.prototype.autoResizeTextarea = function() {
    this.messageInput.style.height = 'auto';
    this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
};

ChatApp.prototype.setupMobileKeyboardHandling = function() {
    if (!('ontouchstart' in window)) return;

    const inputContainer = document.querySelector('.chat-input-container');
    if (!inputContainer) return;

    let initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    
    const handleViewportChange = () => {
        const currentViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        const isInputFocused = document.activeElement === this.messageInput;

        if (!isInputFocused) {
            initialViewportHeight = currentViewportHeight;
            inputContainer.style.transform = 'translateY(0)';
            inputContainer.style.transition = 'transform 0.3s ease';
            return;
        }

        const heightDifference = initialViewportHeight - currentViewportHeight;
        
        if (heightDifference > 150) {
            inputContainer.style.transform = `translateY(-${Math.max(0, heightDifference - 150)}px)`;
            inputContainer.style.transition = 'transform 0.3s ease';
        } else {
            inputContainer.style.transform = 'translateY(0)';
            inputContainer.style.transition = 'transform 0.3s ease';
        }
    };

    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', handleViewportChange);
    } else {
        window.addEventListener('resize', handleViewportChange);
    }

    this.messageInput.addEventListener('focus', () => {
        initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        setTimeout(() => {
            this.messageInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 300);
    });

    this.messageInput.addEventListener('blur', () => {
        inputContainer.style.transform = 'translateY(0)';
        inputContainer.style.transition = 'transform 0.3s ease';
        initialViewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    });

    this.messageInput.addEventListener('touchstart', (e) => {
        if (this.messageInput.style.fontSize !== '16px') {
            this.messageInput.style.fontSize = '16px';
        }
    });
};

// Model List UI
ChatApp.prototype.updateModelListForSource = function() {
    const source = this.currentSource;
    this.modelSelect.innerHTML = '';
    
    if (source === 'local') {
        if (this.localModels && this.localModels.length > 0) {
            this.localModels.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                this.modelSelect.appendChild(option);
            });
            this.modelSelect.disabled = false;
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No local models available';
            option.disabled = true;
            this.modelSelect.appendChild(option);
            this.modelSelect.disabled = true;
        }
        if (this.customModelName) {
            this.customModelName.style.display = 'none';
        }
    } else {
        this.modelSelect.disabled = false;
        if (this.externalModels && this.externalModels.length > 0) {
            this.externalModels.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                this.modelSelect.appendChild(option);
            });
            const otherOption = document.createElement('option');
            otherOption.value = 'Other';
            otherOption.textContent = 'Other';
            this.modelSelect.appendChild(otherOption);
        } else if (this.externalModels === null) {
            this.loadExternalModelsFromApi();
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No external models configured';
            option.disabled = true;
            this.modelSelect.appendChild(option);
            const otherOption = document.createElement('option');
            otherOption.value = 'Other';
            otherOption.textContent = 'Other (enter custom)';
            this.modelSelect.appendChild(otherOption);
        }
    }
};

ChatApp.prototype.populateDocsCountSelect = function() {
    if (!this.docsCountSelect) return;
    
    this.docsCountSelect.innerHTML = '';
    const defaultValue = this.docsToRetrieveOptions.includes(5) ? 5 : this.docsToRetrieveOptions[0];
    
    this.docsToRetrieveOptions.forEach((num) => {
        const option = document.createElement('option');
        option.value = num.toString();
        option.textContent = num.toString();
        if (num === defaultValue) {
            option.selected = true;
        }
        this.docsCountSelect.appendChild(option);
    });
};

// Feature Toggle States
ChatApp.prototype.updateFeatureToggleStates = function() {
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
    
    const qaConfigDisabledLabel = document.getElementById('query-augmentation-config-disabled');
    if (this.queryAugmentationToggleContainer) {
        if (!this.configQueryAugmentationEnabled) {
            this.queryAugmentationToggleContainer.classList.add('disabled');
            this.queryAugmentationToggleContainer.style.opacity = '0.5';
            this.queryAugmentationToggleContainer.style.pointerEvents = 'none';
            this.queryAugmentationToggleSwitch.classList.remove('active');
            this.queryAugmentationToggleContainer.title = 'Query augmentation is disabled in server configuration';
            if (qaConfigDisabledLabel) qaConfigDisabledLabel.style.display = 'inline';
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
};

// Figure Panel
ChatApp.prototype.updateFigurePanel = function() {
    if (!this.figureEmpty || !this.figureDisplayInfo) return;

    if (!this.currentFigure) {
        this.figureEmpty.style.display = 'block';
        this.figureDisplayInfo.classList.remove('visible');
        return;
    }

    this.figureEmpty.style.display = 'none';
    this.figureDisplayInfo.classList.add('visible');

    const figure = this.currentFigure;
    
    if (figure.name && this.figureDisplayName) {
        this.figureDisplayName.textContent = figure.name;
    }

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

    if (figure.description && this.figureDisplayDescription) {
        this.figureDisplayDescription.textContent = figure.description;
    } else if (this.figureDisplayDescription) {
        this.figureDisplayDescription.textContent = '';
    }

    if (figure.personality_prompt && this.figureDisplayPersonality) {
        this.figureDisplayPersonality.textContent = figure.personality_prompt;
    } else if (this.figureDisplayPersonality) {
        this.figureDisplayPersonality.textContent = '';
    }

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
};

// Toggle Functions
ChatApp.prototype.toggleRAG = function() {
    if (!this.configRagEnabled) return;
    
    this.ragEnabled = !this.ragEnabled;
    if (this.ragEnabled) {
        this.ragToggleSwitch.classList.add('active');
    } else {
        this.ragToggleSwitch.classList.remove('active');
    }
    this.savePanelState();
};

ChatApp.prototype.toggleThinking = function() {
    this.thinkingVisible = !this.thinkingVisible;
    if (this.thinkingVisible) {
        this.thinkingToggleSwitch.classList.add('active');
    } else {
        this.thinkingToggleSwitch.classList.remove('active');
    }
    this.updateThinkingVisibility();
    this.savePanelState();
};

ChatApp.prototype.toggleQueryAugmentation = function() {
    if (!this.configQueryAugmentationEnabled) return;
    
    this.queryAugmentationEnabled = !this.queryAugmentationEnabled;
    if (this.queryAugmentationEnabled) {
        this.queryAugmentationToggleSwitch.classList.add('active');
        if (this.augmentedQueryPanel && this.augmentedQueryText && this.augmentedQueryText.textContent) {
            this.augmentedQueryPanel.style.display = 'block';
        }
    } else {
        this.queryAugmentationToggleSwitch.classList.remove('active');
        if (this.augmentedQueryPanel) {
            this.augmentedQueryPanel.style.display = 'none';
        }
    }
    this.savePanelState();
};

ChatApp.prototype.updateAugmentedQuery = function(augmentedQuery) {
    if (!this.queryAugmentationEnabled || !augmentedQuery) {
        if (this.augmentedQueryPanel) {
            this.augmentedQueryPanel.style.display = 'none';
        }
        return;
    }
    
    if (this.augmentedQueryPanel && this.augmentedQueryText) {
        this.augmentedQueryText.textContent = augmentedQuery;
        this.augmentedQueryPanel.style.display = 'block';
        if (this.augmentedQueryModelSpan && this.queryAugmentationModel) {
            this.augmentedQueryModelSpan.textContent = `(${this.queryAugmentationModel})`;
        }
    }
};

ChatApp.prototype.updateThinkingVisibility = function() {
    const thinkingTextElements = document.querySelectorAll('.thinking-text');
    thinkingTextElements.forEach(element => {
        element.style.display = this.thinkingVisible ? 'block' : 'none';
    });
    
    const thinkingIndicators = document.querySelectorAll('.thinking-indicator');
    thinkingIndicators.forEach(indicator => {
        if (indicator.textContent.includes('Thought process')) {
            indicator.innerHTML = '💭 Thought process' + (this.thinkingVisible ? ':' : ' (hidden)');
        }
    });
};

ChatApp.prototype.updateDocumentsVisibility = function() {
    // Documents panel visibility is automatic based on retrieved sources
};

ChatApp.prototype.initializeToggles = function() {
    if (this.configRagEnabled && this.ragEnabled) {
        this.ragToggleSwitch.classList.add('active');
    } else {
        this.ragToggleSwitch.classList.remove('active');
    }
    
    if (this.thinkingVisible) {
        this.thinkingToggleSwitch.classList.add('active');
    } else {
        this.thinkingToggleSwitch.classList.remove('active');
    }
    
    if (this.queryAugmentationToggleSwitch) {
        if (this.configQueryAugmentationEnabled && this.queryAugmentationEnabled) {
            this.queryAugmentationToggleSwitch.classList.add('active');
        } else {
            this.queryAugmentationToggleSwitch.classList.remove('active');
        }
    }
    
    this.updateFeatureToggleStates();
    this.updateThinkingVisibility();
};

// Message Display
ChatApp.prototype.addMessage = function(content, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    
    if (sender === 'user') {
        avatar.textContent = 'You';
    } else {
        if (this.currentFigure && this.currentFigure.metadata && this.currentFigure.metadata.image) {
            const img = document.createElement('img');
            img.src = `/figure_images/${this.currentFigure.metadata.image}`;
            img.alt = this.currentFigure.name || 'AI';
            img.style.width = '100%';
            img.style.height = '100%';
            img.style.borderRadius = '50%';
            img.style.objectFit = 'cover';
            img.onerror = () => {
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
    
    if (sender === 'assistant') {
        messageDiv.retrievedDocuments = [];
    }
    
    this.chatMessages.appendChild(messageDiv);
    this.scrollToBottom();
    
    return contentDiv;
};

// Streaming Content Processing
ChatApp.prototype.processStreamingContent = function(content) {
    let remainingContent = content;
    
    while (remainingContent.includes('<think>') || remainingContent.includes('</think>')) {
        if (!this.isInThinking && remainingContent.includes('<think>')) {
            const thinkStart = remainingContent.indexOf('<think>');
            if (thinkStart !== -1) {
                const beforeThink = remainingContent.substring(0, thinkStart);
                if (beforeThink) {
                    this.addToResponseBuffer(beforeThink);
                }
                
                this.isInThinking = true;
                
                this.currentThinkingElement = document.createElement('div');
                this.currentThinkingElement.className = 'thinking-content';
                
                const thinkingIndicator = document.createElement('div');
                thinkingIndicator.className = 'thinking-indicator';
                thinkingIndicator.innerHTML = '💭 Thinking...';
                thinkingIndicator.style.fontSize = '0.9em';
                thinkingIndicator.style.color = '#7dd3fc';
                thinkingIndicator.style.fontStyle = 'italic';
                thinkingIndicator.style.marginBottom = '8px';
                
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
                const thinkContent = remainingContent.substring(0, thinkEnd);
                this.thinkingBuffer += thinkContent;
                if (this.thinkingTextElement) {
                    this.thinkingTextElement.textContent = this.thinkingBuffer;
                }
                
                const indicator = this.currentThinkingElement?.querySelector('.thinking-indicator');
                if (indicator && this.thinkingBuffer.trim()) {
                    indicator.innerHTML = '💭 Thought process' + (this.thinkingVisible ? ':' : ' (hidden)');
                } else if (indicator && !this.thinkingBuffer.trim()) {
                    this.currentThinkingElement.style.display = 'none';
                }
                
                this.isInThinking = false;
                this.currentThinkingElement = null;
                this.thinkingTextElement = null;
                this.thinkingBuffer = '';
                
                remainingContent = remainingContent.substring(thinkEnd + 8);
            }
        } else {
            if (this.isInThinking) {
                this.thinkingBuffer += remainingContent;
                if (this.thinkingTextElement) {
                    this.thinkingTextElement.textContent = this.thinkingBuffer;
                }
            } else {
                this.addToResponseBuffer(remainingContent);
            }
            break;
        }
    }
    
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
};

ChatApp.prototype.addToResponseBuffer = function(content) {
    if (!this.responseContentElement) {
        this.responseContentElement = document.createElement('div');
        this.responseContentElement.className = 'response-text';
        this.currentMessageElement.appendChild(this.responseContentElement);
    }
    
    this.paragraphBuffer = (this.paragraphBuffer || '') + content;
    const formattedContent = this.applyBasicFormatting(this.paragraphBuffer);
    this.responseContentElement.innerHTML = formattedContent;
};

ChatApp.prototype.applyBasicFormatting = function(text) {
    if (!text) return '';
    
    let formatted = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    
    formatted = formatted
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*\s][^*]*[^*\s])\*/g, '<strong>$1</strong>')
        .replace(/\*([^*\s])\*/g, '<strong>$1</strong>')
        .replace(/_([^_\s][^_]*[^_\s])_/g, '<em>$1</em>')
        .replace(/_([^_\s])_/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
    
    return formatted;
};

ChatApp.prototype.processFinalContent = async function() {
    if (this.paragraphBuffer.trim()) {
        this.scrollToBottom();
    }
    
    if (this.currentMessageElement && this.currentMessageDocuments.length > 0) {
        const messageDiv = this.currentMessageElement.parentElement;
        if (messageDiv && messageDiv.classList.contains('assistant')) {
            messageDiv.retrievedDocuments = [...this.currentMessageDocuments];
        }
    }
};

// Sources/Documents Display
ChatApp.prototype.addSources = function(sources) {
    if (!sources || sources.length === 0) return;
    
    this.currentSources = {};
    this.currentMessageDocuments = [];
    
    sources.forEach(source => {
        this.currentSources[source.doc_id] = source;
        
        this.currentMessageDocuments.push({
            ...source,
            timestamp: new Date().toISOString()
        });
        
        const uniqueKey = `${source.filename}_${source.chunk_id || source.document_id || source.doc_id}`;
        if (!this.allRetrievedDocuments.has(uniqueKey)) {
            this.allRetrievedDocuments.set(uniqueKey, {
                ...source,
                timestamp: new Date().toISOString()
            });
        }
    });
    
    this.clearDocuments();
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
        
        const cosineDiv = document.createElement('div');
        cosineDiv.style.fontSize = '0.75rem';
        cosineDiv.style.color = '#4CAF50';
        cosineDiv.style.marginBottom = '4px';
        const cosineSimilarity = source.cosine_similarity || source.similarity || 0;
        const cosinePercent = Math.round(cosineSimilarity * 100);
        cosineDiv.textContent = `Match (cosine): ${cosinePercent}%`;
        
        const keywordsDiv = document.createElement('div');
        keywordsDiv.style.fontSize = '0.75rem';
        keywordsDiv.style.color = '#FF9800';
        const topWords = source.top_matching_words || [];
        keywordsDiv.textContent = topWords.length > 0 ? `Keywords: ${topWords.join(', ')}` : 'Keywords: none';
        
        documentItem.appendChild(filename);
        documentItem.appendChild(preview);
        documentItem.appendChild(cosineDiv);
        documentItem.appendChild(keywordsDiv);
        
        this.documentsContent.appendChild(documentItem);
    });
};

ChatApp.prototype.clearDocuments = function() {
    const documentItems = this.documentsContent.querySelectorAll('.document-item');
    documentItems.forEach(item => item.remove());
    
    this.documentsPanel.classList.remove('visible');
    this.documentsEmpty.style.display = 'block';
};

// Modals
ChatApp.prototype.showSourceModal = function(source) {
    const chunkId = source.document_id || source.chunk_id || 'unknown';
    this.sourceModalTitle.textContent = `${source.filename} - Chunk ${chunkId}`;
    this.sourceModalText.textContent = source.full_text || source.text;
    this.sourceModal.style.display = 'block';
};

ChatApp.prototype.closeSourceModal = function() {
    this.sourceModal.style.display = 'none';
};

ChatApp.prototype.showDocumentModal = function(docId) {
    const source = this.currentSources[docId];
    if (source) {
        this.showSourceModal(source);
    } else {
        console.warn(`Document ${docId} not found in current sources`);
    }
};

// Error/Warning Display
ChatApp.prototype.showError = function(message) {
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
};

ChatApp.prototype.showApiKeyWarning = function(message) {
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
    
    setTimeout(() => {
        if (warningDiv.parentNode) {
            warningDiv.parentNode.removeChild(warningDiv);
        }
    }, 5000);
};

ChatApp.prototype.updateApiKeyStatus = function() {
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
};

// Utility
ChatApp.prototype.scrollToBottom = function() {
    this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
};

ChatApp.prototype.showLoadingIndicator = function() {
    if (!this.currentMessageElement) return;
    
    this.loadingIndicator = document.createElement('div');
    this.loadingIndicator.className = 'loading-indicator';
    this.loadingIndicator.innerHTML = `
        <span class="loading-dots">
            <span class="dot">●</span>
            <span class="dot">●</span>
            <span class="dot">●</span>
        </span>
    `;
    this.currentMessageElement.appendChild(this.loadingIndicator);
    this.scrollToBottom();
};

ChatApp.prototype.hideLoadingIndicator = function() {
    if (this.loadingIndicator && this.loadingIndicator.parentNode) {
        this.loadingIndicator.parentNode.removeChild(this.loadingIndicator);
        this.loadingIndicator = null;
    }
};

ChatApp.prototype.stopGeneration = function() {
    if (this.abortController) {
        this.abortController.abort();
        this.abortController = null;
    }
};

