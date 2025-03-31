import os
import streamlit as st
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import json

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
        'content': 0,  # Content structure and hierarchy
        'engagement': 0,  # CTAs and forms
        'accessibility': 0  # Accessibility and technical
    }
    
    # Content Structure Score (35%)
    content_score = 0
    headings = site_data['content']['headings']
    paragraphs = site_data['content']['paragraphs']
    
    # Heading hierarchy (15 points)
    if headings['h1'] == 1:
        content_score += 5  # Exactly one H1
    if headings['h2'] > 0:
        content_score += 5  # Has H2 headings
    if headings.get('h3', 0) > 0:
        content_score += 5  # Has H3 headings
    
    # Heading-to-paragraph ratio (10 points)
    total_headings = headings['h1'] + headings['h2'] + headings.get('h3', 0)
    if paragraphs > 0:
        heading_ratio = total_headings / paragraphs
        if 0.2 <= heading_ratio <= 0.4:
            content_score += 10
        elif 0.1 <= heading_ratio < 0.2:
            content_score += 5
    
    # List structure (10 points)
    if site_data['content']['lists'] > 0:
        list_ratio = site_data['content']['lists'] / max(1, paragraphs)
        if 0.1 <= list_ratio <= 0.3:
            content_score += 10
        elif list_ratio > 0:
            content_score += 5
    
    scores['content'] = content_score
    
    # Engagement Score (35%)
    engagement_score = 0
    
    # CTA Analysis (20 points)
    ctas = site_data['ctas']
    if ctas['total'] > 0:
        # Primary CTA ratio (10 points)
        primary_ratio = ctas['primary'] / ctas['total']
        if 0.1 <= primary_ratio <= 0.3:
            engagement_score += 10
        elif primary_ratio > 0:
            engagement_score += 5
        
        # Above fold placement (10 points)
        if ctas['above_fold'] > 0:
            above_fold_ratio = ctas['above_fold'] / ctas['total']
            if above_fold_ratio >= 0.3:
                engagement_score += 10
            else:
                engagement_score += int(above_fold_ratio * 30)
    
    # Form Analysis (15 points)
    forms = site_data['forms']
    if forms['count'] > 0:
        # Form validation (7.5 points)
        validation_score = forms['total_validation_score'] * 7.5
        
        # Form accessibility (7.5 points)
        accessibility_score = forms['total_accessibility_score'] * 7.5
        
        engagement_score += validation_score + accessibility_score
    
    scores['engagement'] = engagement_score
    
    # Accessibility Score (30%)
    accessibility_score = 0
    access_data = site_data['technical']['accessibility']
    
    # Image alt texts (10 points)
    if access_data['alt_texts'] > 0:
        accessibility_score += 10
    
    # ARIA attributes (10 points)
    aria_score = 0
    if access_data['aria_labels'] > 0:
        aria_score += 3
    if access_data['aria_describedby'] > 0:
        aria_score += 3
    if access_data['role_attributes'] > 0:
        aria_score += 2
    if access_data['lang_attribute']:
        aria_score += 2
    accessibility_score += aria_score
    
    # Form accessibility (10 points)
    if forms['count'] > 0:
        form_access_score = min(10, access_data['form_labels'] * 2)
        accessibility_score += form_access_score
    
    scores['accessibility'] = accessibility_score
    
    # Calculate final score with appropriate weighting
    final_score = int(
        (scores['content'] * 0.35) +
        (scores['engagement'] * 0.35) +
        (scores['accessibility'] * 0.30)
    )
    
    # Ensure score is within bounds
    final_score = max(0, min(100, final_score))
    
    # Add detailed scoring information for debugging
    print(f"Detailed Scores:")
    print(f"Content Score: {scores['content']}/35")
    print(f"Engagement Score: {scores['engagement']}/35")
    print(f"Accessibility Score: {scores['accessibility']}/30")
    print(f"Final Score: {final_score}/100")
    
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
        
        # Enhanced CTA detection with visual hierarchy
        cta_patterns = [
            'sign up', 'buy', 'try', 'get', 'start', 'learn more', 'contact', 
            'subscribe', 'download', 'register', 'shop', 'order', 'book'
        ]
        
        primary_classes = ['primary', 'cta', 'main', 'hero', 'btn-primary', 'button-primary']
        secondary_classes = ['secondary', 'btn-secondary', 'button-secondary']
        
        ctas = []
        for elem in soup.find_all(['a', 'button', 'input[type="submit"]']):
            text = elem.get_text().strip().lower()
            classes = ' '.join(elem.get('class', [])).lower()
            style = elem.get('style', '').lower()
            
            if any(pattern in text or pattern in classes for pattern in cta_patterns):
                # Check visual prominence
                is_primary = any(cls in classes for cls in primary_classes)
                is_secondary = any(cls in classes for cls in secondary_classes)
                has_contrast = 'color' in style or 'background' in style
                
                # Calculate prominence score
                prominence_score = 0
                if is_primary:
                    prominence_score += 3
                if is_secondary:
                    prominence_score += 2
                if has_contrast:
                    prominence_score += 1
                
                # Check position
                is_above_fold = elem.parent and elem.parent.find_previous('h1') is None
                is_in_hero = any(cls in classes for cls in ['hero', 'banner', 'header'])
                
                ctas.append({
                    'text': text,
                    'prominence_score': prominence_score,
                    'is_primary': is_primary,
                    'is_secondary': is_secondary,
                    'location': 'hero' if is_in_hero else ('above_fold' if is_above_fold else 'below_fold'),
                    'has_contrast': has_contrast
                })

        # Sort CTAs by prominence score
        ctas.sort(key=lambda x: (-x['prominence_score'], x['location'] != 'hero', x['location'] != 'above_fold'))

        # Enhanced form analysis
        forms = []
        for form in soup.find_all('form'):
            fields = form.find_all(['input', 'select', 'textarea'])
            required_fields = [f for f in fields if f.get('required') or f.get('aria-required') == 'true']
            labels = form.find_all('label')
            
            # Enhanced validation and accessibility checks
            field_analysis = []
            for field in fields:
                field_type = field.get('type', 'text')
                field_id = field.get('id', '')
                field_name = field.get('name', '')
                
                # Find associated label
                label = None
                if field_id:
                    label = form.find('label', {'for': field_id})
                if not label and field_name:
                    label = form.find('label', {'for': field_name})
                
                # Check validation attributes
                validations = {
                    'required': field.get('required') is not None or field.get('aria-required') == 'true',
                    'pattern': field.get('pattern') is not None,
                    'minlength': field.get('minlength') is not None,
                    'maxlength': field.get('maxlength') is not None,
                    'min': field.get('min') is not None,
                    'max': field.get('max') is not None,
                    'step': field.get('step') is not None
                }
                
                # Check accessibility attributes
                accessibility = {
                    'has_label': label is not None,
                    'has_placeholder': field.get('placeholder') is not None,
                    'has_aria_label': field.get('aria-label') is not None,
                    'has_aria_describedby': field.get('aria-describedby') is not None,
                    'has_error_message': bool(form.find(id=field.get('aria-describedby', '')))
                }
                
                field_analysis.append({
                    'type': field_type,
                    'validations': validations,
                    'accessibility': accessibility,
                    'validation_score': sum(1 for v in validations.values() if v),
                    'accessibility_score': sum(1 for a in accessibility.values() if a)
                })
            
            # Calculate form scores
            validation_score = sum(f['validation_score'] for f in field_analysis) / (len(field_analysis) * 3) if field_analysis else 0
            accessibility_score = sum(f['accessibility_score'] for f in field_analysis) / (len(field_analysis) * 3) if field_analysis else 0
            
            forms.append({
                'total_fields': len(fields),
                'required_fields': len(required_fields),
                'field_analysis': field_analysis,
                'validation_score': validation_score,
                'accessibility_score': accessibility_score,
                'has_submit': bool(form.find(['input', 'button'], {'type': 'submit'})),
                'has_error_handling': bool(form.find(class_=lambda x: x and any(err in x.lower() for err in ['error', 'invalid', 'alert'])))
            })

        # Enhanced accessibility analysis
        accessibility_data = {
            'alt_texts': len([img for img in soup.find_all('img') if img.get('alt')]),
            'aria_labels': len(soup.find_all(attrs={"aria-label": True})),
            'aria_describedby': len(soup.find_all(attrs={"aria-describedby": True})),
            'aria_required': len(soup.find_all(attrs={"aria-required": True})),
            'role_attributes': len(soup.find_all(attrs={"role": True})),
            'tab_index': len(soup.find_all(attrs={"tabindex": True})),
            'lang_attribute': bool(soup.find('html', attrs={"lang": True})),
            'skip_links': bool(soup.find('a', href="#main-content")),
            'form_labels': sum(1 for form in forms for field in form['field_analysis'] if field['accessibility']['has_label'])
        }

        return {
            'ctas': {
                'total': len(ctas),
                'prominent': len([c for c in ctas if c['prominence_score'] >= 3]),
                'above_fold': len([c for c in ctas if c['location'] in ['hero', 'above_fold']]),
                'primary': len([c for c in ctas if c['is_primary']]),
                'secondary': len([c for c in ctas if c['is_secondary']]),
                'elements': ctas[:5]  # Return top 5 most prominent CTAs
            },
            'forms': {
                'count': len(forms),
                'analysis': forms,
                'total_validation_score': sum(form['validation_score'] for form in forms) / len(forms) if forms else 0,
                'total_accessibility_score': sum(form['accessibility_score'] for form in forms) / len(forms) if forms else 0
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
                'accessibility': accessibility_data
            }
        }
    except Exception as e:
        raise Exception(f"Failed to fetch website: {str(e)}")

# Initialize Gemini 2.0 Flash Lite model
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    generation_config={
        "temperature": 0.2,
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
                prompt = f"""
You are conducting a **detailed, customized website analysis** of {url}.  
Your primary task is to identify **UNIQUE, SITE-SPECIFIC issues** that are particular to THIS website, not generic UX problems.

🚨 **CRITICAL INSTRUCTIONS:**  
- NEVER report the same generic issues (like "needs more CTAs" or "missing ARIA labels") that could apply to any website
- Each insight MUST be unique to {url} and based on specific elements you identify
- DO NOT mention common issues like CTAs, form validation, or ARIA attributes UNLESS they represent a critical, specific problem on this exact site
- AVOID template responses - each analysis must be completely customized

---

### **Forensic Analysis Approach:**
1. **Examine UNIQUE Content Patterns**  
   - What is unusual or specific about THIS site's content?
   - How does this specific site handle information hierarchy?
   - Look for content gaps or unclear messaging SPECIFIC to this business/organization

2. **Site-Specific User Journey Evaluation**  
   - What path would a user take on THIS particular site?
   - What SPECIFIC interactive elements on THIS site create friction?
   - Identify conversion obstacles UNIQUE to this site

3. **Custom Interaction Analysis**  
   - Are there site-specific functionality problems?
   - Does this particular site have unique navigation challenges?
   - Examine THIS site's specific implementation of forms, search, or other interactive elements

4. **Site-Specific Technical Assessment**  
   - What technical issues affect THIS site that wouldn't apply to others?
   - Are there performance problems SPECIFIC to this site's implementation?
   - Identify technical issues unique to this specific site's architecture

During your analysis, reference these specific metrics ONLY if relevant to a real problem:
H1: {site_data['content']['headings']['h1']}, H2: {site_data['content']['headings']['h2']}, H3: {site_data['content']['headings']['h3']}
Paragraphs: {site_data['content']['paragraphs']}, Lists: {site_data['content']['lists']}
CTAs: {site_data['ctas']['total']} total, {site_data['ctas']['primary']} primary, {site_data['ctas']['above_fold']} above fold
Forms: Count={site_data['forms']['count']}, Validation={site_data['forms']['total_validation_score']:.2f}/1.0
Alt texts: {site_data['technical']['accessibility']['alt_texts']}, ARIA: {site_data['technical']['accessibility']['aria_labels']}

---

### **Custom Findings Format:**
💡 **Step 1: Calculate a UX Health Score (0-100) based on THIS specific website.**  
**UX_HEALTH_SCORE: [number]**  

💡 **Step 2: Identify 3 COMPLETELY DIFFERENT issues unique to {url}.**  
Each insight must follow this format but address entirely different aspects of the site:

**Insight 1: [Specific Issue Unique to This Site]**
- **Observation:** [Describe a specific element or pattern ONLY found on this site]  
- **Impact:** [High/Medium/Low] – [Explain site-specific consequences]  
- **Suggested Fix:** 
  • [Customized solution targeting this specific site's implementation]
  • [Alternative approach specifically for this site]  
- **Expected Improvement:** [Explain improvements specific to this site's goals]

**Insight 2: [Different Issue Area - Must Not Overlap With Insight 1]**
- Must focus on a COMPLETELY DIFFERENT aspect than Insight 1
- Should examine a different part of the user journey or functionality

**Insight 3: [Third Unique Area - Must Not Overlap With Insights 1 & 2]**
- Must focus on a COMPLETELY DIFFERENT aspect than Insights 1 & 2
- Should represent a third distinct problem area

🚨 **ABSOLUTELY CRITICAL:**
- Your analysis MUST be unique to {url} - mentioning specific pages, elements, content, and functionality by name
- Each insight MUST address a completely different aspect of the website
- Insights MUST be based on actual problems, not theoretical issues
- If you cannot find 3 completely different issues, focus on providing 1-2 GENUINELY unique insights rather than inventing generic problems
"""

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
                    analysis_content = response_text.split('**Insight')
                    if len(analysis_content) > 1:
                        st.session_state.analysis_data[url] = '**Insight' + '**Insight'.join(analysis_content[1:])
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
    """Improved issue card display with better parsing and formatting"""
    lines = issue_content.split('\n')
    title = lines[0].replace('**', '').strip() if lines else "Insight"
    
    # Parse sections with improved handling for the new format
    sections = {
        'observation': '',
        'impact': '',
        'suggested_fix': [],
        'expected_improvement': ''
    }
    
    current_section = None
    for i, line in enumerate(lines[1:]):  # Skip title line
        line = line.strip()
        if not line:
            continue
            
        # More robust section detection
        if re.search(r'(?i)\*?\*?observation\s*:|\bObservation\b', line):
            current_section = 'observation'
            sections['observation'] = re.sub(r'(?i)\*?\*?observation\s*:|^\s*-\s*\*?\*?observation\s*:', '', line).strip()
            # If observation is empty, check next line
            if not sections['observation'] and i+2 < len(lines):
                sections['observation'] = lines[i+2].strip()
                
        elif re.search(r'(?i)\*?\*?impact\s*:|\bImpact\b', line):
            current_section = 'impact'
            sections['impact'] = re.sub(r'(?i)\*?\*?impact\s*:|^\s*-\s*\*?\*?impact\s*:', '', line).strip()
            
        elif re.search(r'(?i)\*?\*?suggested\s*fix\s*:|^\s*-\s*\*?\*?suggested\s*fix', line):
            current_section = 'suggested_fix'
            # Don't add the section header to the content
            
        elif re.search(r'(?i)\*?\*?expected\s*improvement\s*:|^\s*-\s*\*?\*?expected\s*improvement', line):
            current_section = 'expected_improvement'
            sections['expected_improvement'] = re.sub(r'(?i)\*?\*?expected\s*improvement\s*:|^\s*-\s*\*?\*?expected\s*improvement\s*:', '', line).strip()
            
        # Content handling for current section
        elif current_section == 'observation' and not sections['observation']:
            sections['observation'] = line
            
        elif current_section == 'impact' and not sections['impact']:
            sections['impact'] = line
            
        elif current_section == 'suggested_fix':
            # Handle bullet points and regular lines
            if line.startswith('•') or line.startswith('-') or re.match(r'^\d+\.', line):
                cleaned_line = re.sub(r'^[•\-\d\.]+\s*', '', line).strip()
                if cleaned_line:
                    sections['suggested_fix'].append(cleaned_line)
            elif line and not re.search(r'(?i)expected\s*improvement', line):
                sections['suggested_fix'].append(line)
                
        elif current_section == 'expected_improvement' and not sections['expected_improvement']:
            sections['expected_improvement'] = line
    
    # If sections are missing, try to extract them from the whole content
    if not sections['observation']:
        match = re.search(r'(?i)observation\s*:(.*?)(?:impact|$)', issue_content, re.DOTALL)
        if match:
            sections['observation'] = match.group(1).strip()
            
    if not sections['impact']:
        match = re.search(r'(?i)impact\s*:(.*?)(?:suggested fix|$)', issue_content, re.DOTALL)
        if match:
            sections['impact'] = match.group(1).strip()
            
    if not sections['suggested_fix']:
        match = re.search(r'(?i)suggested fix\s*:(.*?)(?:expected improvement|$)', issue_content, re.DOTALL)
        if match:
            content = match.group(1).strip()
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('•') or line.startswith('-'):
                    sections['suggested_fix'].append(re.sub(r'^[•\-]+\s*', '', line).strip())
                elif line:
                    sections['suggested_fix'].append(line)
                    
    if not sections['expected_improvement']:
        match = re.search(r'(?i)expected improvement\s*:(.*?)$', issue_content, re.DOTALL)
        if match:
            sections['expected_improvement'] = match.group(1).strip()
    
    # Ensure HTML entities are properly escaped
    for key in ['observation', 'impact', 'expected_improvement']:
        sections[key] = sections[key].replace('<', '&lt;').replace('>', '&gt;')
    
    sections['suggested_fix'] = [item.replace('<', '&lt;').replace('>', '&gt;') for item in sections['suggested_fix']]
    
    # Determine impact level
    impact_level = 'medium'
    if 'High' in sections['impact']:
        impact_level = 'high'
    elif 'Low' in sections['impact']:
        impact_level = 'low'
    
    # Clean and create title
    title = f"Insight {index}: {title.split(':', 1)[1].strip() if ':' in title else title}"
    
    # Ensure we have content for each section
    if not sections['observation']:
        sections['observation'] = "No specific observation provided"
    if not sections['impact']:
        sections['impact'] = "Impact level not specified"
    if not sections['suggested_fix']:
        sections['suggested_fix'] = ["No specific fixes suggested"]
    if not sections['expected_improvement']:
        sections['expected_improvement'] = "No specific improvement metrics provided"
    
    # Render card with improved formatting
    st.markdown(f"""
    <div class="issue-card impact-{impact_level}">
        <h3>{title}</h3>
        <div class="issue-section">
            <div class="section-label">🔍 Observation</div>
            <div class="section-content">{sections['observation']}</div>
        </div>
        <div class="issue-section">
            <div class="section-label">📊 Impact</div>
            <div class="section-content">{sections['impact']}</div>
        </div>
        <div class="issue-section">
            <div class="section-label">💡 Suggested Fix</div>
            <div class="section-content">
                {''.join([f'<div class="solution-item">{item}</div>' for item in sections['suggested_fix']])}
            </div>
        </div>
        <div class="issue-section">
            <div class="section-label">📈 Expected Improvement</div>
            <div class="section-content">{sections['expected_improvement']}</div>
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
    issues = [issue.strip() for issue in analysis_content.split("**Insight") if issue.strip()]
    
    for i, issue in enumerate(issues, 1):
        display_issue_card(issue, i)
    
    # Close grid container
    st.markdown("</div>", unsafe_allow_html=True)

def enhanced_website_analysis(url):
    """Comprehensive website analysis using Selenium, Lighthouse, BeautifulSoup and Requests"""
    results = {
        'structure': {},
        'engagement': {},
        'performance': {},
        'accessibility': {},
        'security': {}
    }
    
    # 1. Security checks with Requests
    try:
        response = requests.get(url, timeout=10)
        results['security']['https'] = url.startswith('https')
        results['security']['status_code'] = response.status_code
        results['security']['headers'] = {
            'content-security-policy': 'Content-Security-Policy' in response.headers,
            'strict-transport-security': 'Strict-Transport-Security' in response.headers,
            'x-xss-protection': 'X-XSS-Protection' in response.headers
        }
    except Exception as e:
        results['security']['error'] = str(e)
    
    # 2. Selenium for rendering and interaction analysis
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    
    driver = webdriver.Chrome(options=options)
    try:
        start_time = time.time()
        driver.get(url)
        load_time = time.time() - start_time
        results['performance']['load_time'] = load_time
        
        # Check for console errors
        logs = driver.get_log('browser')
        results['performance']['console_errors'] = [log for log in logs if log['level'] == 'SEVERE']
        
        # Check for broken images
        images = driver.find_elements_by_tag_name('img')
        broken_images = []
        for img in images:
            if img.get_attribute('naturalWidth') == '0':
                broken_images.append(img.get_attribute('src'))
        results['performance']['broken_images'] = broken_images
        
        # Check for forms and interaction elements
        results['engagement']['forms'] = len(driver.find_elements_by_tag_name('form'))
        results['engagement']['buttons'] = len(driver.find_elements_by_tag_name('button'))
        results['engagement']['links'] = len(driver.find_elements_by_tag_name('a'))
        
        # Get page HTML for BeautifulSoup (which is already implemented in the app)
        html = driver.page_source
        
    except Exception as e:
        results['error'] = str(e)
    finally:
        driver.quit()
    
    # 3. Use Lighthouse API for comprehensive metrics
    # Note: This would require setting up Lighthouse programmatically
    # or using an API service that provides Lighthouse metrics
    
    return results
