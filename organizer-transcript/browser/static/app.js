// Transcript Browser - Frontend Logic

// State
let companies = [];
let selectedCompany = null;
let selectedTranscripts = new Set();
let notesEditorOpen = false;
let lastSavedObsidianUri = null;
let lastGeneratedFiles = [];  // Store PDF paths from last prompt generation

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadCompanies();

    // Search input handler
    const searchInput = document.getElementById('searchInput');
    let searchTimeout;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            loadCompanies(e.target.value);
        }, 200);
    });
});

// Load companies from API
async function loadCompanies(search = '') {
    try {
        const url = search
            ? `/api/companies?search=${encodeURIComponent(search)}`
            : '/api/companies';

        const response = await fetch(url);
        const data = await response.json();

        companies = data.companies;
        renderCompanyList();

        // Update count
        document.getElementById('companyCount').textContent =
            `${data.total} companies`;
    } catch (error) {
        console.error('Failed to load companies:', error);
    }
}

// Render company list
function renderCompanyList() {
    const container = document.getElementById('companyList');
    container.innerHTML = '';

    let addedRecentHeader = false;
    let addedAllHeader = false;

    for (const company of companies) {
        // Add section headers
        if (company.is_recent && !addedRecentHeader) {
            const header = document.createElement('div');
            header.className = 'list-section-header recent';
            header.innerHTML = '✨ Recently Added';
            container.appendChild(header);
            addedRecentHeader = true;
        } else if (!company.is_recent && addedRecentHeader && !addedAllHeader) {
            const header = document.createElement('div');
            header.className = 'list-section-header';
            header.innerHTML = 'All Companies';
            container.appendChild(header);
            addedAllHeader = true;
        }

        const item = document.createElement('div');
        item.className = 'company-item';
        if (selectedCompany && selectedCompany.ticker === company.ticker) {
            item.classList.add('selected');
        }
        if (company.is_recent) {
            item.classList.add('recent');
        }

        const notesIndicator = company.has_notes ? '<span class="notes-indicator" title="Has notes">📝</span>' : '';
        const newBadge = company.is_recent ? '<span class="new-badge">NEW</span>' : '';

        item.innerHTML = `
            <div class="ticker">${company.ticker} ${notesIndicator} ${newBadge}</div>
            <div class="name">${company.company}</div>
            <div class="stats">
                <span class="count">${company.count} transcript${company.count !== 1 ? 's' : ''}</span>
                <span class="latest">${company.latest_quarter || 'N/A'}</span>
            </div>
        `;

        item.addEventListener('click', () => selectCompany(company.ticker));
        container.appendChild(item);
    }
}

// Select a company
async function selectCompany(ticker) {
    try {
        const response = await fetch(`/api/companies/${ticker}`);
        if (!response.ok) throw new Error('Company not found');

        selectedCompany = await response.json();
        selectedTranscripts = new Set();
        notesEditorOpen = false;

        // Update UI
        document.getElementById('noSelection').style.display = 'none';
        document.getElementById('companyDetail').style.display = 'block';
        document.getElementById('promptOutput').style.display = 'none';
        document.getElementById('analysisSection').style.display = 'none';

        document.getElementById('detailCompanyName').textContent = selectedCompany.company;
        document.getElementById('detailTicker').textContent = selectedCompany.ticker;

        // Render notes
        renderNotes();

        // Render transcripts
        renderTranscriptGrid();

        // Render analysis history
        renderAnalysisHistory();

        renderCompanyList(); // Update selection highlight
    } catch (error) {
        console.error('Failed to load company:', error);
        showToast('Failed to load company');
    }
}

// Render company notes
function renderNotes() {
    const notesPreview = document.getElementById('notesPreview');
    const followUpList = document.getElementById('followUpList');
    const notesInput = document.getElementById('notesInput');
    const followUpInput = document.getElementById('followUpInput');

    // Set current values
    notesInput.value = selectedCompany.notes || '';
    followUpInput.value = (selectedCompany.follow_up_questions || []).join('\n');

    // Update display
    if (selectedCompany.notes) {
        notesPreview.textContent = selectedCompany.notes;
        notesPreview.classList.remove('empty');
    } else {
        notesPreview.textContent = 'No notes yet. Click Edit to add.';
        notesPreview.classList.add('empty');
    }

    // Render follow-up questions
    followUpList.innerHTML = '';
    if (selectedCompany.follow_up_questions && selectedCompany.follow_up_questions.length > 0) {
        const ul = document.createElement('ul');
        for (const q of selectedCompany.follow_up_questions) {
            const li = document.createElement('li');
            li.textContent = q;
            ul.appendChild(li);
        }
        followUpList.appendChild(ul);
    }

    // Reset editor state
    document.getElementById('notesDisplay').style.display = 'block';
    document.getElementById('notesEditor').style.display = 'none';
    document.getElementById('notesToggleText').textContent = 'Edit';
}

// Toggle notes editor
function toggleNotes() {
    notesEditorOpen = !notesEditorOpen;
    document.getElementById('notesDisplay').style.display = notesEditorOpen ? 'none' : 'block';
    document.getElementById('notesEditor').style.display = notesEditorOpen ? 'block' : 'none';
    document.getElementById('notesToggleText').textContent = notesEditorOpen ? 'Cancel' : 'Edit';
}

// Save company notes
async function saveNotes() {
    const notes = document.getElementById('notesInput').value.trim();
    const followUpText = document.getElementById('followUpInput').value.trim();
    const followUpQuestions = followUpText ? followUpText.split('\n').filter(q => q.trim()) : [];

    try {
        const response = await fetch(`/api/companies/${selectedCompany.ticker}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: selectedCompany.ticker,
                notes: notes,
                follow_up_questions: followUpQuestions
            })
        });

        if (!response.ok) throw new Error('Failed to save notes');

        // Update local state
        selectedCompany.notes = notes;
        selectedCompany.follow_up_questions = followUpQuestions;

        // Re-render
        renderNotes();
        loadCompanies(document.getElementById('searchInput').value); // Refresh list to update indicator

        showToast('Notes saved!');
    } catch (error) {
        console.error('Failed to save notes:', error);
        showToast('Failed to save notes');
    }
}

// Build selection label for a transcript (includes event_type to prevent collisions)
function getTranscriptLabel(t) {
    if (t.quarter && t.year) {
        return `${t.event_type}|${t.quarter} ${t.year}`;
    }
    return `${t.event_type}|${t.filename}`;
}

// Get display label (without event_type prefix)
function getDisplayLabel(t) {
    if (t.quarter && t.year) {
        return `${t.quarter} ${t.year}`;
    }
    if (t.date) {
        return t.date;
    }
    return t.filename.substring(0, 30);
}

// Render transcript grid - separated into Earnings Calls and Conferences
function renderTranscriptGrid() {
    const container = document.getElementById('transcriptGrid');
    container.innerHTML = '';

    if (!selectedCompany || !selectedCompany.transcripts.length) {
        container.innerHTML = '<p class="no-selection">No transcripts available</p>';
        return;
    }

    // Split into earnings calls and other events
    const earningsCalls = selectedCompany.transcripts.filter(t => t.event_type === 'Earnings Call');
    const conferences = selectedCompany.transcripts.filter(t => t.event_type !== 'Earnings Call');

    // Render Earnings Calls section
    if (earningsCalls.length > 0) {
        const section = document.createElement('div');
        section.className = 'transcript-section earnings-section';
        section.innerHTML = `<h3 class="section-title earnings-title">Earnings Calls (${earningsCalls.length})</h3>`;
        renderTranscriptCards(section, earningsCalls);
        container.appendChild(section);
    }

    // Render Conferences section (collapsed by default)
    if (conferences.length > 0) {
        const section = document.createElement('div');
        section.className = 'transcript-section conference-section';

        const header = document.createElement('h3');
        header.className = 'section-title conference-title collapsible';
        header.innerHTML = `Conferences & Other (${conferences.length}) <span class="collapse-icon">▸</span>`;
        header.addEventListener('click', () => {
            const content = section.querySelector('.conference-content');
            const icon = header.querySelector('.collapse-icon');
            if (content.style.display === 'none') {
                content.style.display = 'block';
                icon.textContent = '▾';
            } else {
                content.style.display = 'none';
                icon.textContent = '▸';
            }
        });
        section.appendChild(header);

        const content = document.createElement('div');
        content.className = 'conference-content';
        content.style.display = 'none';
        renderTranscriptCards(content, conferences);
        section.appendChild(content);

        container.appendChild(section);
    }
}

// Render transcript cards grouped by year into a container
function renderTranscriptCards(container, transcripts) {
    const byYear = {};
    for (const t of transcripts) {
        const year = t.year || (t.date ? t.date.substring(0, 4) : 'Unknown');
        if (!byYear[year]) byYear[year] = [];
        byYear[year].push(t);
    }

    const years = Object.keys(byYear).sort((a, b) => b - a);

    for (const year of years) {
        const yearGroup = document.createElement('div');
        yearGroup.className = 'year-group';
        yearGroup.innerHTML = `<h4>${year}</h4>`;

        const quarterRow = document.createElement('div');
        quarterRow.className = 'quarter-row';

        for (const t of byYear[year]) {
            const label = getTranscriptLabel(t);
            const displayLabel = getDisplayLabel(t);
            const isSelected = selectedTranscripts.has(label);
            const isConference = t.event_type !== 'Earnings Call';

            const card = document.createElement('label');
            card.className = 'transcript-card' + (isSelected ? ' selected' : '') + (isConference ? ' conference-card' : '');

            const badgeClass = t.transcript_type === 'CORRECTED' ? 'corrected' : 'raw';

            // For conferences, show the specific event name from indexer
            const eventDisplay = isConference
                ? (t.event_name || t.event_type).substring(0, 40)
                : t.event_type;

            card.innerHTML = `
                <input type="checkbox" ${isSelected ? 'checked' : ''} data-label="${label}">
                <span class="quarter">${displayLabel}</span>
                <span class="type ${isConference ? 'type-conference' : ''}">${eventDisplay}</span>
                <span class="badge ${badgeClass}">${t.transcript_type}</span>
            `;

            card.querySelector('input').addEventListener('change', (e) => {
                if (e.target.checked) {
                    selectedTranscripts.add(label);
                    card.classList.add('selected');
                } else {
                    selectedTranscripts.delete(label);
                    card.classList.remove('selected');
                }
            });

            quarterRow.appendChild(card);
        }

        yearGroup.appendChild(quarterRow);
        container.appendChild(yearGroup);
    }
}

// Render analysis history
function renderAnalysisHistory() {
    const historyList = document.getElementById('historyList');
    historyList.innerHTML = '';

    if (!selectedCompany.analysis_history || selectedCompany.analysis_history.length === 0) {
        historyList.innerHTML = '<p class="empty">No previous analyses recorded.</p>';
        return;
    }

    for (const record of selectedCompany.analysis_history.reverse()) {
        const item = document.createElement('div');
        item.className = 'history-item';

        const quarters = record.quarters ? record.quarters.join(', ') : 'N/A';
        const date = new Date(record.timestamp).toLocaleDateString();

        item.innerHTML = `
            <div class="history-header">
                <span class="history-quarters">${quarters}</span>
                <span class="history-date">${date}</span>
            </div>
            ${record.user_comments ? `<div class="history-comments">${record.user_comments}</div>` : ''}
        `;

        item.addEventListener('click', () => {
            // Could expand to show full AI response
            if (record.ai_response) {
                showToast('Full analysis available');
            }
        });

        historyList.appendChild(item);
    }
}

// Quick select: Latest 2 quarters (earnings only)
function selectLatestTwo() {
    if (!selectedCompany) return;

    selectedTranscripts.clear();

    // Find latest 2 earnings calls
    const earnings = selectedCompany.transcripts
        .filter(t => t.event_type === 'Earnings Call' && t.quarter && t.year);

    const latest = earnings.slice(0, 2);
    for (const t of latest) {
        selectedTranscripts.add(getTranscriptLabel(t));
    }

    renderTranscriptGrid();
}

// Quick select: All earnings calls
function selectAllEarnings() {
    if (!selectedCompany) return;

    selectedTranscripts.clear();

    for (const t of selectedCompany.transcripts) {
        if (t.event_type === 'Earnings Call' && t.quarter && t.year) {
            selectedTranscripts.add(getTranscriptLabel(t));
        }
    }

    renderTranscriptGrid();
}

// Clear selection
function clearSelection() {
    selectedTranscripts.clear();
    renderTranscriptGrid();
}

// Generate analysis prompt
async function generatePrompt() {
    if (!selectedCompany) {
        showToast('Please select a company');
        return;
    }

    if (selectedTranscripts.size === 0) {
        showToast('Please select at least one transcript');
        return;
    }

    try {
        const response = await fetch('/api/prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: selectedCompany.ticker,
                transcripts: Array.from(selectedTranscripts)
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate prompt');
        }

        const data = await response.json();

        // Display prompt
        document.getElementById('promptText').textContent = data.prompt;

        // Display file list
        const fileList = document.getElementById('fileList');
        fileList.innerHTML = '';
        for (const file of data.files) {
            const li = document.createElement('li');
            li.textContent = file;
            fileList.appendChild(li);
        }

        document.getElementById('promptOutput').style.display = 'block';
        document.getElementById('aiAnalysisSection').style.display = 'block';
        document.getElementById('analysisSection').style.display = 'block';

        // Store PDF paths for later use
        lastGeneratedFiles = data.files;

        // Clear previous inputs and reset state
        document.getElementById('aiResponseInput').value = '';
        document.getElementById('userCommentsInput').value = '';
        document.getElementById('openObsidianBtn').style.display = 'none';
        lastSavedObsidianUri = null;

        // Scroll to prompt
        document.getElementById('promptOutput').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Failed to generate prompt:', error);
        showToast(error.message);
    }
}

// Save analysis record
async function saveAnalysis() {
    const aiResponse = document.getElementById('aiResponseInput').value.trim();
    const userComments = document.getElementById('userCommentsInput').value.trim();
    const aiProvider = document.getElementById('aiProviderSelect').value;
    const saveToObsidian = document.getElementById('saveToObsidian').checked;

    if (!aiResponse && !userComments) {
        showToast('Please add AI response or comments');
        return;
    }

    try {
        const response = await fetch(`/api/analysis/${selectedCompany.ticker}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: selectedCompany.ticker,
                quarters: Array.from(selectedTranscripts),
                timestamp: new Date().toISOString(),
                ai_response: aiResponse,
                user_comments: userComments,
                pdf_paths: lastGeneratedFiles,
                ai_provider: aiProvider,
                save_to_obsidian: saveToObsidian
            })
        });

        if (!response.ok) throw new Error('Failed to save analysis');

        const result = await response.json();

        // Show Obsidian button if saved to Obsidian
        if (result.obsidian_uri) {
            lastSavedObsidianUri = result.obsidian_uri;
            document.getElementById('openObsidianBtn').style.display = 'inline-block';
            showToast('Analysis saved to Obsidian!');
        } else if (saveToObsidian) {
            showToast('Analysis saved (Obsidian write failed)');
        } else {
            showToast('Analysis saved!');
        }

        // Refresh company data
        selectCompany(selectedCompany.ticker);
    } catch (error) {
        console.error('Failed to save analysis:', error);
        showToast('Failed to save analysis');
    }
}

// Open last saved analysis in Obsidian
function openInObsidian() {
    if (lastSavedObsidianUri) {
        window.open(lastSavedObsidianUri, '_blank');
    } else {
        showToast('No Obsidian file to open');
    }
}

// Run direct AI analysis
async function runAnalysis(provider) {
    if (!selectedCompany) {
        showToast('Please select a company');
        return;
    }

    if (selectedTranscripts.size === 0) {
        showToast('Please select transcripts first');
        return;
    }

    // Show loading state
    const progressDiv = document.getElementById('analysisProgress');
    const progressText = document.getElementById('progressText');
    const claudeBtn = document.getElementById('claudeBtn');
    const geminiBtn = document.getElementById('geminiBtn');

    progressDiv.style.display = 'flex';
    claudeBtn.disabled = true;
    geminiBtn.disabled = true;

    const providerName = provider === 'claude' ? 'Claude Opus 4.5' : 'Gemini 2.5 Pro';
    progressText.textContent = `Analyzing with ${providerName}... (this may take 1-2 minutes)`;

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker: selectedCompany.ticker,
                transcripts: Array.from(selectedTranscripts),
                provider: provider
            })
        });

        const result = await response.json();

        if (result.status === 'ok' && result.response) {
            // Success - populate the response field
            document.getElementById('aiResponseInput').value = result.response;
            document.getElementById('aiProviderSelect').value = provider;

            const usage = result.usage ?
                ` (${result.usage.input_tokens} in / ${result.usage.output_tokens} out tokens)` : '';
            showToast(`Analysis complete!${usage}`);

            // Scroll to response area
            document.getElementById('analysisSection').scrollIntoView({ behavior: 'smooth' });
        } else {
            // Error
            showToast(result.error || 'Analysis failed');
            console.error('Analysis error:', result.error);
        }
    } catch (error) {
        console.error('Analysis request failed:', error);
        showToast('Failed to run analysis: ' + error.message);
    } finally {
        // Hide loading state
        progressDiv.style.display = 'none';
        claudeBtn.disabled = false;
        geminiBtn.disabled = false;
    }
}

// Copy prompt to clipboard
async function copyPrompt() {
    const promptText = document.getElementById('promptText').textContent;

    try {
        await navigator.clipboard.writeText(promptText);
        showToast('Copied to clipboard!');
    } catch (error) {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = promptText;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('Copied to clipboard!');
    }
}

// Show toast notification
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 2000);
}
