/**
 * UIManager - Manages all UI interactions and updates
 */
export class UIManager {
    constructor(elements, state) {
        this.elements = elements;
        this.state = state;
    }
    
    initializePanelState() {
        // Apply control panel state
        if (this.state.controlPanelOpen) {
            this.elements.controlPanel.classList.add('open');
            this.elements.controlPanel.classList.remove('closed');
            this.elements.controlToggleBtn.classList.add('panel-open');
            if (window.innerWidth <= 768) {
                this.elements.overlay.classList.add('active');
            }
        } else {
            this.elements.controlPanel.classList.remove('open');
            this.elements.controlPanel.classList.add('closed');
            this.elements.controlToggleBtn.classList.remove('panel-open');
        }
        
        // Apply figure panel state (only on mobile/tablet)
        if (window.innerWidth <= 1024) {
            if (this.elements.figurePanel) {
                if (this.state.figurePanelOpen) {
                    this.elements.figurePanel.classList.add('open');
                    this.elements.figurePanel.classList.remove('closed');
                    if (this.elements.figureToggleBtn) {
                        this.elements.figureToggleBtn.classList.add('panel-open');
                    }
                    this.elements.overlay.classList.add('active');
                } else {
                    this.elements.figurePanel.classList.remove('open');
                    this.elements.figurePanel.classList.add('closed');
                    if (this.elements.figureToggleBtn) {
                        this.elements.figureToggleBtn.classList.remove('panel-open');
                    }
                }
            }
        } else {
            // On desktop, figure panel is always visible
            this.state.figurePanelOpen = true;
            if (this.elements.figurePanel) {
                this.elements.figurePanel.classList.remove('open', 'closed');
            }
        }
    }
    
    initializeToggles() {
        // Update RAG toggle
        if (this.state.ragEnabled) {
            this.elements.ragToggleSwitch.classList.add('active');
        } else {
            this.elements.ragToggleSwitch.classList.remove('active');
        }
        
        // Update thinking toggle
        if (this.state.thinkingVisible) {
            this.elements.thinkingToggleSwitch.classList.add('active');
        } else {
            this.elements.thinkingToggleSwitch.classList.remove('active');
        }
        
        // Update documents toggle
        if (this.state.documentsVisible) {
            this.elements.documentsToggleSwitch.classList.add('active');
            this.elements.documentsPanel.classList.add('visible');
        } else {
            this.elements.documentsToggleSwitch.classList.remove('active');
            this.elements.documentsPanel.classList.remove('visible');
        }
        
        // Update thinking intensity
        if (this.elements.thinkingIntensitySelect) {
            this.elements.thinkingIntensitySelect.value = this.state.thinkingIntensity;
        }
        
        // Update temperature
        if (this.elements.temperatureSlider) {
            this.elements.temperatureSlider.value = this.state.temperature;
        }
        if (this.elements.temperatureValue) {
            this.elements.temperatureValue.textContent = this.state.temperature.toFixed(1);
        }
    }
    
    updateRagStatusDisplay(stats) {
        if (stats.status === 'success') {
            this.elements.ragStatus.textContent = `${stats.count} docs`;
            this.elements.ragStatus.style.color = stats.count > 0 ? '#27ae60' : '#a8c5d9';
        } else if (stats.status === 'no_figure') {
            this.elements.ragStatus.textContent = 'No Figure';
            this.elements.ragStatus.style.color = '#a8c5d9';
        } else {
            this.elements.ragStatus.textContent = 'Error';
            this.elements.ragStatus.style.color = '#e74c3c';
        }
    }
    
    updateHealthStatus(data) {
        if (data.status === 'healthy') {
            if (this.elements.statusDot) {
                this.elements.statusDot.classList.add('connected');
            }
            if (this.elements.statusText) {
                this.elements.statusText.textContent = 'Connected';
            }
        } else {
            if (this.elements.statusDot) {
                this.elements.statusDot.classList.remove('connected');
            }
            if (this.elements.statusText) {
                this.elements.statusText.textContent = data.status === 'unhealthy' ? 'Disconnected' : 'Error';
            }
        }
    }
    
    updateModelSelect(models, defaultModel = 'external') {
        this.elements.modelSelect.innerHTML = '';
        
        // Add External API option first
        const externalOption = document.createElement('option');
        externalOption.value = 'external';
        externalOption.textContent = 'External API';
        this.elements.modelSelect.appendChild(externalOption);
        
        // Add local models
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            this.elements.modelSelect.appendChild(option);
        });
        
        // Set default
        this.elements.modelSelect.value = defaultModel;
    }
    
    updateFigureSelect(figures) {
        this.elements.figureSelect.innerHTML = '<option value="">General Chat</option>';
        
        figures.forEach(figure => {
            const option = document.createElement('option');
            option.value = figure.figure_id;
            option.textContent = `${figure.name} (${figure.document_count || 0} docs)`;
            this.elements.figureSelect.appendChild(option);
        });
        
        this.elements.figureSelect.disabled = false;
    }
    
    updateFigurePanel(figureData) {
        if (!this.elements.figureEmpty || !this.elements.figureDisplayInfo) {
            return;
        }

        if (!figureData) {
            this.elements.figureEmpty.style.display = 'block';
            this.elements.figureDisplayInfo.classList.remove('visible');
            return;
        }

        this.elements.figureEmpty.style.display = 'none';
        this.elements.figureDisplayInfo.classList.add('visible');

        const figure = figureData;
        
        if (figure.name && this.elements.figureDisplayName) {
            this.elements.figureDisplayName.textContent = figure.name;
        }

        if (this.elements.figureYears) {
            const birthYear = figure.birth_year || (figure.metadata && figure.metadata.birth_year);
            const deathYear = figure.death_year || (figure.metadata && figure.metadata.death_year);
            if (birthYear || deathYear) {
                const birthDisplay = birthYear || '?';
                const deathDisplay = deathYear || '?';
                this.elements.figureYears.textContent = `(${birthDisplay} - ${deathDisplay})`;
            } else {
                this.elements.figureYears.textContent = '';
            }
        }

        if (figure.description && this.elements.figureDisplayDescription) {
            this.elements.figureDisplayDescription.textContent = figure.description;
        } else if (this.elements.figureDisplayDescription) {
            this.elements.figureDisplayDescription.textContent = '';
        }

        if (figure.personality_prompt && this.elements.figureDisplayPersonality) {
            this.elements.figureDisplayPersonality.textContent = figure.personality_prompt;
        } else if (this.elements.figureDisplayPersonality) {
            this.elements.figureDisplayPersonality.textContent = '';
        }

        const imageFile = figure.image || (figure.metadata && figure.metadata.image);
        if (imageFile && this.elements.figureImage) {
            this.elements.figureImage.src = `/figure_images/${imageFile}`;
            this.elements.figureImage.style.display = 'block';
            this.elements.figureImage.onerror = () => {
                this.elements.figureImage.style.display = 'none';
            };
        } else if (this.elements.figureImage) {
            this.elements.figureImage.style.display = 'none';
        }
    }
    
    scrollToBottom() {
        this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
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
        this.elements.chatMessages.appendChild(errorDiv);
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
        this.elements.chatMessages.appendChild(warningDiv);
        this.scrollToBottom();
        
        setTimeout(() => {
            if (warningDiv.parentNode) {
                warningDiv.parentNode.removeChild(warningDiv);
            }
        }, 5000);
    }
}

