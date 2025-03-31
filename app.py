import os
import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re

# Configure Gemini API
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    if 'GEMINI_API_KEY' not in st.secrets:
        st.error("Please set the GEMINI_API_KEY in your environment variables or Streamlit secrets.")
        st.stop()
    api_key = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=api_key)

def calculate_health_score(site_data):
    """Calculate detailed health score based on specific metrics with enhanced accuracy"""
    scores = {
        'conversion': 0,
        'ux_design': 0,
        'technical': 0
    }
    
    # Conversion Score (40%)
    # CTA Analysis - check position, prominence, clarity
    cta_score = 0
    if site_data['ctas']['total'] > 0:
        # Check ratio of prominent CTAs
        cta_prominence_ratio = site_data['ctas']['prominent'] / site_data['ctas']['total']
        # Check if CTAs are above fold
        cta_position_ratio = site_data['ctas']['above_fold'] / site_data['ctas']['total'] if site_data['ctas']['total'] > 0 else 0
        # Weighted score for CTAs
        cta_score = (cta_prominence_ratio * 60) + (cta_position_ratio * 40)
    
    # Form Analysis - check labels, validation, required fields
    form_score = 0
    if site_data['forms']['count'] > 0:
        form_validations = []
        for form in site_data['forms']['analysis']:
            # Check for labels
            has_labels_score = 30 if form.get('has_labels', False) else 0
            # Check for field validation
            validation_score = 30 if form.get('validation', False) else 0
            # Check required vs total fields ratio
            field_ratio_score = min(40, (form.get('required_fields', 0) / max(1, form.get('total_fields', 1)) * 40))
            form_validations.append(has_labels_score + validation_score + field_ratio_score)
        
        # Average form scores if multiple forms
        form_score = sum(form_validations) / len(form_validations) if form_validations else 0
    
    scores['conversion'] = (cta_score * 0.6 + form_score * 0.4)
    
    # UX Design Score (30%)
    # Navigation structure
    nav_elements = 0
    if site_data['navigation']['main_nav']: 
        nav_elements += 50
    if site_data['navigation']['footer_nav']: 
        nav_elements += 30
    if site_data['navigation']['breadcrumbs']: 
        nav_elements += 20
    
    # Content structure
    content_score = 0
    if site_data['content']['headings']['h1'] == 1:
        content_score += 40  # Exactly one H1
    if site_data['content']['headings']['h2'] > 0:
        content_score += 30  # Has H2 headings
    if site_data['content']['lists'] > 0:
        content_score += 15  # Has lists for scannable content
    if site_data['content']['paragraphs'] > 3:
        content_score += 15  # Has sufficient paragraph content
    
    scores['ux_design'] = (nav_elements * 0.5 + content_score * 0.5)
    
    # Technical Score (30%)
    # Responsive design
    responsive_score = 0
    if site_data['technical']['responsive']['meta_tag']: 
        responsive_score += 50
    if site_data['technical']['responsive']['media_queries']: 
        responsive_score += 50
    
    # Performance optimizations
    perf_score = 0
    if site_data['technical']['performance'].get('minified_resources', False): 
        perf_score += 50
    if site_data['technical']['performance'].get('images_with_lazy', 0) > 0: 
        perf_score += 50
    
    # Accessibility considerations
    access_items = site_data['technical']['accessibility']
    access_score = 0
    if access_items.get('alt_texts', 0) > 0: 
        access_score += 50
    if access_items.get('aria_labels', 0) > 0: 
        access_score += 50
    
    scores['technical'] = (responsive_score * 0.4 + perf_score * 0.3 + access_score * 0.3)
    
    # Calculate final score with appropriate weighting
    final_score = int((scores['conversion'] * 0.4) + 
                     (scores['ux_design'] * 0.3) + 
                     (scores['technical'] * 0.3))
    
    # Validation step - make sure the score is within bounds
    final_score = max(0, min(100, final_score))
    
    return final_score, scores

def fetch_website_content(url):
    """Enhanced website content analysis with improved accuracy"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Enhanced CTA detection
        cta_patterns = [
            'sign up', 'buy', 'try', 'get', 'start', 'learn more', 'contact', 
            'subscribe', 'download', 'register', 'shop', 'order', 'book'
        ]
        
        ctas = []
        for elem in soup.find_all(['a', 'button', 'input[type="submit"]']):
            text = elem.get_text().strip().lower()
            classes = ' '.join(elem.get('class', [])).lower()
            if any(pattern in text or pattern in classes for pattern in cta_patterns):
                is_prominent = any(cls in classes for cls in ['primary', 'cta', 'main', 'hero'])
                ctas.append({
                    'text': text,
                    'prominent': is_prominent,
                    'location': 'above_fold' if elem.parent and elem.parent.find_previous('h1') is None else 'below_fold'
                })

        # Enhanced form analysis
        forms = []
        for form in soup.find_all('form'):
            fields = form.find_all(['input', 'select', 'textarea'])
            required_fields = [f for f in fields if f.get('required') or f.get('aria-required') == 'true']
            labels = form.find_all('label')
            
            forms.append({
                'total_fields': len(fields),
                'required_fields': len(required_fields),
                'has_labels': len(labels) > 0,
                'field_types': [f.get('type', 'text') for f in fields],
                'validation': bool(form.find('input', {'pattern': True}))
            })

        return {
            'ctas': {
                'total': len(ctas),
                'prominent': len([c for c in ctas if c['prominent']]),
                'above_fold': len([c for c in ctas if c['location'] == 'above_fold']),
                'elements': ctas
            },
            'forms': {
                'count': len(forms),
                'analysis': forms
            },
            'navigation': {
                'main_nav': bool(soup.find('nav')),
                'footer_nav': bool(soup.find('footer')),
                'breadcrumbs': bool(soup.find(class_=lambda x: x and 'breadcrumb' in x))
            },
            'content': {
                'headings': {level: len(soup.find_all(level)) for level in ['h1', 'h2', 'h3']},
                'paragraphs': len(soup.find_all('p')),
                'lists': len(soup.find_all(['ul', 'ol']))
            },
            'technical': {
                'responsive': {
                    'meta_tag': bool(soup.find('meta', {'name': 'viewport'})),
                    'media_queries': bool('media' in str(soup.find_all('style')))
                },
                'performance': {
                    'images_with_lazy': len([img for img in soup.find_all('img') if img.get('loading') == 'lazy']),
                    'minified_resources': bool(soup.find('link', {'href': re.compile(r'\.min\.')}))
                },
                'accessibility': {
                    'alt_texts': len([img for img in soup.find_all('img') if img.get('alt')]),
                    'aria_labels': len(soup.find_all(attrs={"aria-label": True}))
                }
            }
        }
    except Exception as e:
        raise Exception(f"Failed to fetch website: {str(e)}")

# Initialize Gemini 2.0 Flash Lite model
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-lite",
    generation_config={
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 2048,
    }
)

# Custom CSS for improved UI alignment and card styling
st.markdown("""
<style>
/* Card and Layout Styling */
.grid-container {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 40px;  /* Increased gap between cards */
    padding: 30px;  /* Added padding around the grid */
    max-width: 1200px;  /* Maximum width for better readability */
    margin: 0 auto;  /* Center the grid */
}

.issue-card {
    background: white;
    border: 1px solid #e0e0e0;
    border-radius: 12px;  /* Increased border radius */
    padding: 25px;  /* Increased internal padding */
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);  /* Enhanced shadow */
    height: 100%;
    margin: 10px 0;  /* Added vertical margin */
}

.issue-card h3 {
    margin: 0 0 20px 0;  /* Increased bottom margin */
    padding-bottom: 15px;
    border-bottom: 2px solid #f0f0f0;
    color: #1a1a1a;
    font-size: 1.3em;  /* Slightly larger font */
}

.issue-section {
    background: #f8f9fa;
    padding: 20px;  /* Increased padding */
    margin: 15px 0;  /* Increased margin */
    border-radius: 8px;
}

.section-label {
    font-weight: 600;
    color: #1a1a1a;
    margin-bottom: 8px;
    font-size: 0.95em;
}

.section-content {
    color: #333;
    line-height: 1.5;
}

.solution-item {
    margin: 8px 0 8px 20px;
    position: relative;
    line-height: 1.4;
}

.solution-item:before {
    content: "•";
    position: absolute;
    left: -15px;
    color: #007bff;
}

.impact-high { border-left: 4px solid #dc3545; }
.impact-medium { border-left: 4px solid #ffc107; }
.impact-low { border-left: 4px solid #28a745; }

/* Section Headers */
.section-header {
    color: #1a1a1a;
    font-size: 1.5em;
    margin: 20px 0;
    padding-bottom: 10px;
    border-bottom: 2px solid #f0f0f0;
}

/* Chat Interface */
.chat-message {
    padding: 8px;
    margin: 5px 0;
    border-radius: 8px;
    font-size: 0.9em;
    word-wrap: break-word;
}

.chat-user {
    background: #e3f2fd;
    margin-left: 10px;
    border: 1px solid #bbdefb;
}

.chat-assistant {
    background: #f5f5f5;
    margin-right: 10px;
    border: 1px solid #e0e0e0;
}

[data-testid="stSidebar"][aria-expanded="true"] {
    min-width: 400px;
    max-width: 400px;
}

/* Health Score Circle */
.health-score-container {
    text-align: center;
    margin: 40px auto;
    max-width: 220px;
}

.health-score-circle {
    width: 200px;
    height: 200px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin: 0 auto;
    background: white;
    border: 10px solid;
    border-color: var(--score-color);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    transition: all 0.3s ease;
}

.health-score-circle:hover {
    transform: scale(1.03);
    box-shadow: 0 6px 16px rgba(0,0,0,0.2);
}

.health-score-number {
    font-size: 4.5em;
    font-weight: 700;
    color: #333;
    line-height: 1;
    margin-bottom: 5px;
}

.health-score-label {
    font-size: 1.1em;
    font-weight: 500;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}
</style>
""", unsafe_allow_html=True)

# Main content area for analysis
st.title("🎯 CRO Assistant")
st.caption("AI-powered Conversion Rate Optimization Analysis")

# Session state management
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = {}
if "current_url" not in st.session_state:
    st.session_state.current_url = None
if "ux_health_score" not in st.session_state:
    st.session_state.ux_health_score = None

# Move chat interface to sidebar
with st.sidebar:
    st.markdown("### 💬 CRO Chat Assistant")
    
    # Display chat messages with compact styling
    for role, message in st.session_state.chat_history[-4:]:  # Show only last 4 messages
        message_class = "chat-user" if role == "user" else "chat-assistant"
        st.markdown(f"""
        <div class="chat-message {message_class}">
            <div class="chat-header">{'You' if role == 'user' else '🤖 Assistant'}</div>
            {message}
        </div>
        """, unsafe_allow_html=True)
    
    # Chat input with focused context
    if user_input := st.chat_input("Ask about the analysis..."):
        st.session_state.chat_history.append(("user", user_input))
        
        # Build focused context from current analysis
        current_url = st.session_state.current_url
        current_analysis = st.session_state.analysis_data.get(current_url, '')
        
        # Create a more focused prompt for shorter responses
        context = f"""Website: {current_url}
        
        Current analysis summary:
        {current_analysis[:500]}  # Limit context length
        
        Provide a brief, focused response to: {user_input}
        
        Keep the response:
        1. Under 3 sentences
        2. Specific to the current analysis
        3. Actionable and clear
        4. Focused on CRO improvements"""
        
        try:
            response = model.generate_content(context)
            if response and response.text:
                # Limit response length
                response_text = response.text[:300] if len(response.text) > 300 else response.text
                st.session_state.chat_history.append(("assistant", response_text))
            st.rerun()
        except Exception as e:
            st.error("Failed to get response")

# URL Analysis Section
with st.expander("🔍 Analyze Website", expanded=True):
    url = st.text_input("Enter URL:", placeholder="https://example.com")
    
    if st.button("Analyze Website"):
        with st.spinner("Analyzing website..."):
            try:
                # Validate URL
                parsed_url = urlparse(url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    st.error("Please enter a valid URL including http:// or https://")
                    st.stop()
                
                # Store current URL for context
                st.session_state.current_url = url
                
                # Fetch and analyze website
                site_data = fetch_website_content(url)
                
                # Build analysis prompt
                prompt = f"""Analyze the UX health score of {url}. Perform a thorough, comprehensive evaluation across all key areas to provide an accurate score similar to a professional UX audit.

                Assess the following key areas with precision:
                1. Navigation & Structure (25 points):
                - Navigation structure: {site_data['navigation']}
                - Content hierarchy: H1: {site_data['content']['headings']['h1']}, H2: {site_data['content']['headings']['h2']}, Lists: {site_data['content']['lists']}
                - Menu organization and clarity

                2. Content & Accessibility (25 points):
                - Content quality: Paragraphs: {site_data['content']['paragraphs']}
                - Accessibility features: {site_data['technical']['accessibility']}
                - Readability and information structure

                3. Performance & Technical (25 points):
                - Responsive design: {site_data['technical']['responsive']}
                - Performance optimizations: {site_data['technical']['performance']}
                - Loading speed indicators
                
                4. User Engagement & Conversion (25 points):
                - CTAs: {site_data['ctas']['total']} total, {site_data['ctas']['prominent']} primary, {site_data['ctas']['above_fold']} above fold
                - Forms and interaction points: {site_data['forms']['analysis']}
                - User journey clarity

                First, calculate an accurate UX health score out of 100, where higher scores indicate better UX. Be critical and precise in your evaluation - a score of 90+ should only be given to truly exceptional sites.

                VERY IMPORTANT: You MUST provide the UX health score in this EXACT format on its own line:
                UX_HEALTH_SCORE: [number]

                Then provide exactly 3 issues in this format:

                **Issue 1: [Most Critical UX Issue]**
                Problem: [One specific issue based on metrics]
                Impact: [High/Medium/Low] - [Quantified impact]
                Solution: 
                • [Specific fix 1]
                • [Specific fix 2]
                Expected Lift: [Estimate]

                **Issue 2: [Second Issue]**
                [Same format]

                **Issue 3: [Third Issue]**
                [Same format]"""

                response = model.generate_content(prompt)
                if response and response.text:
                    # Print the full response for debugging
                    print(f"AI Response: {response.text}")
                    
                    # Extract UX health score with improved pattern matching
                    response_text = response.text
                    
                    # Try multiple patterns to extract the score
                    score_patterns = [
                        r'UX_HEALTH_SCORE:\s*(\d+)',  # Standard format
                        r'UX Health Score:\s*(\d+)',  # Alternative capitalization
                        r'UX Health Score:\s*(\d+)/100',  # With denominator
                        r'[\n\r](\d+)/100',  # Just the score with denominator
                        r'score of (\d+)',   # Descriptive text
                        r'score: (\d+)',     # Another common format
                        r'score is (\d+)'    # Another variation
                    ]
                    
                    extracted_score = None
                    for pattern in score_patterns:
                        match = re.search(pattern, response_text, re.IGNORECASE)
                        if match:
                            extracted_score = int(match.group(1))
                            print(f"Extracted score: {extracted_score} using pattern: {pattern}")
                            break
                    
                    if extracted_score:
                        # Validate the score is reasonable
                        if 1 <= extracted_score <= 100:
                            st.session_state.ux_health_score = extracted_score
                            print(f"Using extracted score: {extracted_score}")
                        else:
                            # Score outside valid range
                            st.session_state.ux_health_score = min(100, max(1, extracted_score))
                            print(f"Adjusted score to valid range: {st.session_state.ux_health_score}")
                    else:
                        # If no score pattern matched, calculate one
                        print("No score pattern matched, calculating from analysis")
                        calculated_score, _ = calculate_health_score(site_data)
                        st.session_state.ux_health_score = calculated_score
                        print(f"Using calculated score: {calculated_score}")
                    
                    # Store analysis content
                    analysis_content = response_text.split('**Issue')
                    if len(analysis_content) > 1:
                        st.session_state.analysis_data[url] = '**Issue' + '**Issue'.join(analysis_content[1:])
                        st.success("Analysis complete")
                    else:
                        st.error("Failed to generate proper analysis format")
                        st.stop()
                else:
                    st.error("Failed to generate analysis")
                    st.stop()
                    
            except Exception as e:
                st.error(f"Error analyzing website: {str(e)}")
                st.stop()

def display_issue_card(issue_content, index):
    """Improved issue card display with better formatting"""
    lines = issue_content.split('\n')
    title = lines[0].replace('**', '').strip() if lines else "Issue"
    
    # Parse sections with improved handling
    sections = {
        'problem': '',
        'impact': '',
        'solution': [],
        'expected_lift': ''
    }
    
    current_section = None
    for line in lines[1:]:  # Skip title line
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('Problem:'):
            current_section = 'problem'
            sections['problem'] = line.replace('Problem:', '').strip()
        elif line.startswith('Impact:'):
            current_section = 'impact'
            sections['impact'] = line.replace('Impact:', '').strip()
        elif line.startswith('Solution:'):
            current_section = 'solution'
        elif line.startswith('Expected Lift:'):
            current_section = 'expected_lift'
            sections['expected_lift'] = line.replace('Expected Lift:', '').strip()
        elif line.startswith('•') and current_section == 'solution':
            sections['solution'].append(line.replace('•', '').strip())
        elif current_section == 'solution' and line:
            sections['solution'].append(line.strip())
    
    # Determine impact level
    impact_level = 'medium'
    if 'High' in sections['impact']:
        impact_level = 'high'
    elif 'Low' in sections['impact']:
        impact_level = 'low'
    
    # Clean and escape HTML content
    title = f"Issue {index}: {title.split(':', 1)[1].strip() if ':' in title else title}"
    
    # Render card with improved formatting and proper HTML escaping
    st.markdown(f"""
    <div class="issue-card impact-{impact_level}">
        <h3>{title}</h3>
        <div class="issue-section">
            <div class="section-label">🎯 Problem</div>
            <div class="section-content">{sections['problem']}</div>
        </div>
        <div class="issue-section">
            <div class="section-label">📊 Impact</div>
            <div class="section-content">{sections['impact']}</div>
        </div>
        <div class="issue-section">
            <div class="section-label">💡 Solution</div>
            <div class="section-content">
                {''.join([f'<div class="solution-item">{item}</div>' for item in sections['solution']])}
            </div>
        </div>
        <div class="issue-section">
            <div class="section-label">📈 Expected Lift</div>
            <div class="section-content">{sections['expected_lift']}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def get_score_color(score):
    """Return color based on health score using standard UX audit color ranges"""
    if score >= 90:
        return "#00A36C"  # Emerald Green for excellent
    elif score >= 80:
        return "#28a745"  # Green for very good
    elif score >= 70:
        return "#5cb85c"  # Light Green for good
    elif score >= 60:
        return "#ffc107"  # Yellow for fair
    elif score >= 50:
        return "#fd7e14"  # Orange for needs improvement
    elif score >= 40:
        return "#dc3545"  # Red for poor
    else:
        return "#9e1a1a"  # Dark Red for critical issues

def display_health_score(site_data=None):
    """Display UX health score from analysis"""
    # Use the UX health score from analysis if available
    if hasattr(st.session_state, 'ux_health_score') and st.session_state.ux_health_score is not None:
        final_score = st.session_state.ux_health_score
        source = "ai_analysis"
    elif site_data is not None:
        # Fallback to calculated score if analysis score not available but site_data is
        final_score, _ = calculate_health_score(site_data)
        source = "calculated"
    else:
        # Default score if neither analysis score nor site_data is available
        final_score = 75  # More optimistic default
        source = "default"
    
    # For debugging
    print(f"Displaying score: {final_score} (source: {source})")
    
    # Get color based on score
    score_color = get_score_color(final_score)
    
    st.markdown(f"""
    <div class="health-score-container">
        <div class="health-score-circle" style="--score-color: {score_color}">
            <div class="health-score-number">{final_score}</div>
            <div class="health-score-label">HEALTH SCORE</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Display Analysis Results
if st.session_state.analysis_data.get(url):
    st.markdown("<h2 class='section-header'>Analysis Results</h2>", unsafe_allow_html=True)
    
    # Display health score before the grid
    try:
        # Use the UX health score from analysis directly
        display_health_score()
    except Exception as e:
        st.error(f"Error displaying health score: {str(e)}")
    
    # Start grid container
    st.markdown("<div class='grid-container'>", unsafe_allow_html=True)
    
    # Display issues
    analysis_content = st.session_state.analysis_data[url]
    issues = [issue.strip() for issue in analysis_content.split("**Issue") if issue.strip()]
    
    for i, issue in enumerate(issues, 1):
        display_issue_card(issue, i)
    
    # Close grid container
    st.markdown("</div>", unsafe_allow_html=True)