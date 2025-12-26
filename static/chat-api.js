/**
 * API/Server communication methods for ChatApp
 * Handles all backend interactions: health checks, models, figures, chat, exports
 */

ChatApp.prototype.checkHealth = async function() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        if (data.status === 'healthy') {
            if (this.statusDot) this.statusDot.classList.add('connected');
            if (this.statusText) this.statusText.textContent = 'Connected';
        } else {
            if (this.statusDot) this.statusDot.classList.remove('connected');
            if (this.statusText) this.statusText.textContent = 'Disconnected';
        }
    } catch (error) {
        if (this.statusDot) this.statusDot.classList.remove('connected');
        if (this.statusText) this.statusText.textContent = 'Error';
    }
};

ChatApp.prototype.loadModels = async function() {
    try {
        const response = await fetch('/api/models-by-source');
        const data = await response.json();
        
        this.localModels = data.local || [];
        this.externalModels = data.external;
        
        const hasLocalModels = this.localModels && this.localModels.length > 0;
        const hasExternalModels = this.externalModels && this.externalModels.length > 0;
        
        this.updateSourceSelectorOptions(hasLocalModels, hasExternalModels);
        
        // Default: prefer external if available, otherwise local
        if (hasExternalModels || !hasLocalModels) {
            this.currentSource = 'external';
        } else {
            this.currentSource = 'local';
        }
        
        if (this.modelSourceSelect) {
            this.modelSourceSelect.value = this.currentSource;
        }
        
        this.updateModelListForSource();
        
        if (this.externalApiConfig) {
            this.externalApiConfig.style.display = this.currentSource === 'external' ? 'block' : 'none';
        }
        if (this.currentSource === 'external') {
            this.loadExternalApiKeyStatus();
        }
    } catch (error) {
        console.error('Failed to load models:', error);
        this.localModels = [];
        this.externalModels = null;
        this.updateSourceSelectorOptions(false, false);
        this.updateModelListForSource();
    }
};

ChatApp.prototype.updateSourceSelectorOptions = function(hasLocalModels, hasExternalModels) {
    if (!this.modelSourceSelect) return;
    
    const externalOption = this.modelSourceSelect.querySelector('option[value="external"]');
    const localOption = this.modelSourceSelect.querySelector('option[value="local"]');
    
    if (localOption) {
        if (!hasLocalModels) {
            localOption.textContent = 'Local (no models)';
            localOption.style.color = '#888';
        } else {
            localOption.textContent = 'Local';
            localOption.style.color = '';
        }
    }
    
    if (externalOption) {
        if (this.externalModels && this.externalModels.length === 0) {
            externalOption.textContent = 'External API (no models configured)';
            externalOption.style.color = '#888';
        } else {
            externalOption.textContent = 'External API';
            externalOption.style.color = '';
        }
    }
};

ChatApp.prototype.loadExternalModelsFromApi = async function() {
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
            
            const otherOption = document.createElement('option');
            otherOption.value = 'Other';
            otherOption.textContent = 'Other';
            this.modelSelect.appendChild(otherOption);
            return;
        }
    } catch (e) {
        console.log('Could not fetch models from external API');
    }
    
    // Fallback: show "Other" option only
    this.modelSelect.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Enter model name below';
    placeholder.disabled = true;
    placeholder.selected = true;
    this.modelSelect.appendChild(placeholder);
    
    const otherOption = document.createElement('option');
    otherOption.value = 'Other';
    otherOption.textContent = 'Other (enter custom)';
    this.modelSelect.appendChild(otherOption);
    
    this.modelSelect.value = 'Other';
    if (this.customModelName) {
        this.customModelName.style.display = 'block';
    }
};

ChatApp.prototype.loadExternalApiKeyStatus = async function() {
    try {
        const response = await fetch('/api/external-api-key-status');
        const data = await response.json();
        
        if (this.currentSource === 'external' && data.has_key && data.masked_key) {
            if (this.externalApiKey && !this.externalApiKey.value.trim()) {
                this.externalApiKey.value = data.masked_key;
                this.externalApiKey.setAttribute('data-is-masked', 'true');
                this.externalApiKey.setAttribute('placeholder', 'Pre-configured API key (masked)');
                
                this.updateApiKeyStatus();
                
                if (this.apiKeyStatus) {
                    this.apiKeyStatus.style.display = 'block';
                    this.apiKeyStatus.innerHTML = '<span style="color: #27ae60;">✓ Using pre-configured API key</span>';
                }
            }
        }
    } catch (error) {
        console.error('Failed to load external API key status:', error);
    }
};

ChatApp.prototype.loadFeatureFlags = async function() {
    try {
        const response = await fetch('/api/feature-flags');
        const data = await response.json();
        
        this.configRagEnabled = data.rag_enabled;
        this.configQueryAugmentationEnabled = data.query_augmentation_enabled;
        this.queryAugmentationModel = data.query_augmentation_model || '';
        
        if (data.docs_to_retrieve && Array.isArray(data.docs_to_retrieve) && data.docs_to_retrieve.length > 0) {
            this.docsToRetrieveOptions = data.docs_to_retrieve;
        }
        this.populateDocsCountSelect();
        
        if (!this.configRagEnabled) {
            this.ragEnabled = false;
        }
        
        if (!this.configQueryAugmentationEnabled) {
            this.queryAugmentationEnabled = false;
        }
        
        this.updateFeatureToggleStates();
        
    } catch (error) {
        console.error('Failed to load feature flags:', error);
        this.populateDocsCountSelect();
    }
};

ChatApp.prototype.loadFigures = async function() {
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
};

ChatApp.prototype.loadCurrentFigure = async function() {
    try {
        // Reset to General Chat on page load
        const resetResponse = await fetch('/api/figure/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ figure_id: null })
        });
        
        this.figureSelect.value = '';
        this.currentFigure = null;
        this.updateFigurePanel();
        this.updateRagStatus();
    } catch (error) {
        console.error('Failed to reset figure:', error);
    }
};

ChatApp.prototype.handleFigureChange = async function(e) {
    const figureId = e.target.value;
    
    try {
        const response = await fetch('/api/figure/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ figure_id: figureId || null })
        });
        
        const result = await response.json();
        
        if (result.success) {
            this.currentFigure = result.current_figure;
            this.updateFigurePanel();
            this.updateRagStatus();
            
            this.clearDocuments();
            this.currentSources = {};
            this.allRetrievedDocuments.clear();
            
            if (this.augmentedQueryPanel) {
                this.augmentedQueryPanel.style.display = 'none';
            }
            if (this.augmentedQueryText) {
                this.augmentedQueryText.textContent = '';
            }
            
            this.chatMessages.innerHTML = '';
        } else {
            console.error('Failed to select figure:', result.error);
        }
    } catch (error) {
        console.error('Error selecting figure:', error);
    }
};

ChatApp.prototype.sendMessage = async function(message) {
    this.isStreaming = true;
    this.sendButton.disabled = true;
    this.sendButton.style.display = 'none';
    this.stopButton.style.display = 'inline-block';
    
    this.abortController = new AbortController();
    
    this.currentMessageElement = this.addMessage('', 'assistant');
    this.showLoadingIndicator();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                model: this.getSelectedModelName(),
                use_rag: this.ragEnabled,
                k: parseInt(this.docsCountSelect.value),
                thinking_intensity: this.thinkingIntensity || 'normal',
                temperature: this.temperature || 1.0,
                query_augmentation: this.queryAugmentationEnabled,
                ...(this.currentSource === 'external' && {
                    external_config: {
                        base_url: this.externalApiUrl ? this.externalApiUrl.value : 'https://api.poe.com/v1',
                        model: this.getSelectedModelName(),
                        api_key: this.externalApiKey && this.externalApiKey.getAttribute('data-is-masked') === 'true' 
                            ? '' 
                            : (this.externalApiKey ? this.externalApiKey.value : '')
                    }
                })
            }),
            signal: this.abortController.signal
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
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
                            this.hideLoadingIndicator();
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
                            if (this.loadingIndicator && fullContent.length >= 10) {
                                this.hideLoadingIndicator();
                            }
                            this.processStreamingContent(data.content);
                            this.scrollToBottom();
                        }
                        
                        if (data.done) {
                            this.hideLoadingIndicator();
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
        this.hideLoadingIndicator();
        
        if (error.name === 'AbortError') {
            console.log('Request was cancelled');
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
};

ChatApp.prototype.updateRagStatus = async function() {
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
};

ChatApp.prototype.saveConversation = async function() {
    try {
        if (this.saveConversationBtn) {
            this.saveConversationBtn.disabled = true;
            this.saveConversationBtn.textContent = 'Saving...';
        }
        
        const messages = [];
        const messageElements = this.chatMessages.querySelectorAll('.message');
        
        messageElements.forEach(msgElement => {
            const isUser = msgElement.classList.contains('user');
            const contentElement = msgElement.querySelector('.message-content');
            
            if (contentElement) {
                let content;
                if (isUser) {
                    content = contentElement.textContent.trim();
                } else {
                    const htmlContent = contentElement.innerHTML;
                    content = htmlContent
                        .replace(/<br\s*\/?>/gi, '\n')
                        .replace(/<[^>]*>/g, '')
                        .replace(/&amp;/g, '&')
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
                    
                    if (!isUser && msgElement.retrievedDocuments && msgElement.retrievedDocuments.length > 0) {
                        message.retrieved_documents = msgElement.retrievedDocuments;
                    }
                    
                    messages.push(message);
                }
            }
        });
        
        const figureNameWithDocs = this.figureSelect.selectedOptions[0]?.text || 'General Chat';
        const cleanFigureName = figureNameWithDocs.split(' (')[0];
        const docCountMatch = figureNameWithDocs.match(/\((\d+) docs?\)/);
        const documentCount = docCountMatch ? docCountMatch[1] : '0';
        
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

        const conversationData = {
            title: `Chat with ${cleanFigureName}`,
            date: new Date().toLocaleString(),
            messages: messages,
            figure: cleanFigureName,
            figure_name: cleanFigureName,
            figure_data: figureData,
            document_count: documentCount,
            model: this.getSelectedModelName(),
            temperature: this.temperature.toString(),
            thinking_enabled: this.thinkingVisible,
            rag_enabled: this.ragEnabled,
            retrieved_documents: []
        };
        
        const response = await fetch('/api/export/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(conversationData)
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chat_${cleanFigureName.replace(/[^a-z0-9]/gi, '_')}_${Date.now()}.pdf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            
            if (this.saveConversationBtn) {
                this.saveConversationBtn.textContent = 'Saved!';
                setTimeout(() => { this.saveConversationBtn.textContent = 'Save'; }, 2000);
            }
        } else {
            throw new Error('Failed to generate PDF');
        }
        
    } catch (error) {
        console.error('Error saving conversation:', error);
        if (this.saveConversationBtn) {
            this.saveConversationBtn.textContent = 'Error';
            setTimeout(() => { this.saveConversationBtn.textContent = 'Save'; }, 2000);
        }
    } finally {
        if (this.saveConversationBtn) {
            this.saveConversationBtn.disabled = false;
        }
    }
};

