import os
import streamlit as st
import openai
import pandas as pd
from datetime import datetime

# Try importing jira, with graceful fallback if not installed
try:
    from jira import JIRA

    JIRA_AVAILABLE = True
except ImportError:
    JIRA_AVAILABLE = False

# Configure page
st.set_page_config(page_title="Jira Test Case Generator", layout="wide")
st.title("AI Test Case Generator with Jira Integration")

# Check if jira package is installed
if not JIRA_AVAILABLE:
    st.error("""
    The 'jira' package is not installed. Please install it using:
    ```
    pip install jira
    ```
    Then restart this application.
    """)

# Application state
if 'generated_test_cases' not in st.session_state:
    st.session_state.generated_test_cases = {}
if 'fetched_tickets' not in st.session_state:
    st.session_state.fetched_tickets = []

# Load environment variables if available
default_jira_url = os.environ.get("JIRA_URL", "")
default_jira_email = os.environ.get("JIRA_EMAIL", "")
default_jira_project = os.environ.get("JIRA_PROJECT", "")
default_openai_api_key = os.environ.get("OPENAI_API_KEY", "")

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")

    # OpenAI Configuration
    st.subheader("OpenAI Settings")
    openai_api_key = st.text_input("OpenAI API Key", type="password", value=default_openai_api_key)
    ai_model = st.selectbox("AI Model", ["gpt-3.5-turbo", "gpt-4"], index=0)

    # Jira Configuration
    st.subheader("Jira Connection")
    jira_url = st.text_input("Jira URL", placeholder="https://your-domain.atlassian.net", value=default_jira_url)
    jira_email = st.text_input("Jira Email", placeholder="your-email@example.com", value=default_jira_email)
    jira_api_token = st.text_input("Jira API Token", type="password",
                                   help="Generate from Atlassian account settings")

    jira_project = st.text_input("Jira Project Key", placeholder="PROJ", value=default_jira_project)

    # Save configuration as environment variables
    if st.checkbox("Remember these settings", value=False):
        st.info("Settings will be saved for this session only. For permanent storage, set environment variables.")
        os.environ["JIRA_URL"] = jira_url
        os.environ["JIRA_EMAIL"] = jira_email
        os.environ["JIRA_PROJECT"] = jira_project
        os.environ["OPENAI_API_KEY"] = openai_api_key

    # Test connection button
    if st.button("Test Jira Connection"):
        if not JIRA_AVAILABLE:
            st.error("Please install the 'jira' package first")
        elif not jira_url or not jira_email or not jira_api_token:
            st.error("Please fill all Jira connection fields")
        else:
            try:
                jira = JIRA(server=jira_url, basic_auth=(jira_email, jira_api_token))
                myself = jira.myself()
                st.success(f"Connection successful! Connected as {myself['displayName']}")
            except Exception as e:
                st.error(f"Connection failed: {str(e)}")


# Functions
def connect_to_jira(jira_url, jira_email, jira_api_token):
    """Establish connection to Jira"""
    if not JIRA_AVAILABLE:
        st.error("The 'jira' package is not installed")
        return None

    if not jira_url or not jira_email or not jira_api_token:
        st.error("Please provide all Jira connection details in the sidebar")
        return None

    try:
        return JIRA(server=jira_url, basic_auth=(jira_email, jira_api_token))
    except Exception as e:
        st.error(f"Failed to connect to Jira: {str(e)}")
        return None


def fetch_jira_tickets(jira, project_key, status=None, max_results=50):
    """Fetch tickets from specified Jira project"""
    if not project_key:
        st.error("Please provide a Jira Project Key in the sidebar")
        return []

    query = f"project = {project_key}"

    if status and status != "All":
        query += f" AND status = '{status}'"

    try:
        issues = jira.search_issues(query, maxResults=max_results)
        return issues
    except Exception as e:
        st.error(f"Error fetching tickets: {str(e)}")
        return []


def get_ticket_details(jira, issue_key):
    """Get detailed information for a specific ticket"""
    try:
        issue = jira.issue(issue_key)

        # Extract fields
        details = {
            'key': issue.key,
            'summary': issue.fields.summary,
            'description': issue.fields.description or "No description provided",
            'status': issue.fields.status.name,
            'issue_type': issue.fields.issuetype.name,
            'priority': issue.fields.priority.name if hasattr(issue.fields,
                                                              'priority') and issue.fields.priority else "Not set",
            'components': [c.name for c in issue.fields.components] if hasattr(issue.fields, 'components') else [],
            'created': issue.fields.created,
            'updated': issue.fields.updated
        }

        # Try to get acceptance criteria if it exists (custom field)
        # This is tricky because custom fields vary between Jira instances
        acceptance_criteria = "No acceptance criteria provided"

        # Try common custom field names for acceptance criteria
        custom_field_names = ['customfield_10000', 'customfield_10001', 'customfield_10002',
                              'customfield_10003', 'customfield_10004', 'customfield_10005']

        for field_name in custom_field_names:
            try:
                value = getattr(issue.fields, field_name, None)
                if value and (isinstance(value, str) and 'accept' in value.lower()):
                    acceptance_criteria = value
                    break
            except:
                pass

        details['acceptance_criteria'] = acceptance_criteria

        return details
    except Exception as e:
        st.error(f"Error fetching ticket details: {str(e)}")
        return None


def generate_test_cases(ticket_details, openai_api_key, model="gpt-3.5-turbo"):
    """Generate test cases from ticket details using OpenAI API"""
    if not openai_api_key:
        st.error("OpenAI API key is required in the sidebar")
        return None

    try:
        client = openai.OpenAI(api_key=openai_api_key)
    except Exception as e:
        st.error(f"Error initializing OpenAI client: {str(e)}")
        return None

    # Create an enhanced prompt
    components_str = ", ".join(ticket_details['components']) if ticket_details['components'] else "No components"

    prompt = f"""
    You are an expert QA engineer. Based on the following Jira ticket details, generate a comprehensive set of test cases.

    TICKET KEY: {ticket_details['key']}
    SUMMARY: {ticket_details['summary']}
    DESCRIPTION: {ticket_details['description']}
    ISSUE TYPE: {ticket_details['issue_type']}
    PRIORITY: {ticket_details['priority']}
    COMPONENTS: {components_str}
    ACCEPTANCE CRITERIA: {ticket_details['acceptance_criteria']}

    For each test case, provide:
    1. Test case ID (TC-XX format)
    2. Test objective
    3. Preconditions
    4. Test steps (numbered)
    5. Expected results
    6. Priority (High/Medium/Low)

    Cover the following:
    - Positive test cases (valid inputs/scenarios)
    - Negative test cases (invalid inputs/error handling)
    - Edge cases and boundary values
    - Performance considerations (if applicable)
    - Security aspects (if applicable)
    - Integration points with other components

    Format the test cases clearly with proper categorization using markdown.
    """

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system",
                 "content": "You are a QA expert specialized in creating comprehensive test cases from Jira tickets."},
                {"role": "user", "content": prompt}
            ]
        )

        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error generating test cases: {str(e)}")
        return None


def save_test_cases_to_jira(jira, ticket_key, test_cases):
    """Save generated test cases as a comment on the original Jira ticket"""
    try:
        comment = f"*AI Generated Test Cases*\n\n{test_cases}"
        jira.add_comment(ticket_key, comment)
        return True
    except Exception as e:
        st.error(f"Error saving test cases to Jira: {str(e)}")
        return False


# Main interface
tab1, tab2, tab3, tab4 = st.tabs(["Getting Started", "Fetch Tickets", "Generate Test Cases", "Batch Processing"])

# Tab 0: Getting Started
with tab1:
    st.header("Getting Started")

    st.markdown("""
    ## Welcome to the AI Test Case Generator

    This tool helps QA engineers automatically generate test cases from Jira tickets using AI.

    ### Setup Instructions

    1. **Install Required Packages** (if not already installed):
       ```
       pip install streamlit openai jira pandas
       ```

    2. **Configure API Keys**:
       - Enter your OpenAI API key in the sidebar
       - Enter your Jira connection details

    3. **Test the Connection**:
       - Click "Test Jira Connection" in the sidebar

    ### How to Use

    1. **Fetch Tickets** tab:
       - Retrieve tickets from your Jira project

    2. **Generate Test Cases** tab:
       - Select a ticket and generate test cases

    3. **Batch Processing** tab:
       - Generate test cases for multiple tickets at once
    """)

    # Show connection status
    st.subheader("Connection Status")

    col1, col2 = st.columns(2)

    with col1:
        st.write("OpenAI API:")
        if openai_api_key:
            st.success("API Key provided")
        else:
            st.error("API Key missing")

    with col2:
        st.write("Jira Connection:")
        if all([jira_url, jira_email, jira_api_token, jira_project]):
            try:
                jira = connect_to_jira(jira_url, jira_email, jira_api_token)
                if jira:
                    st.success("Ready to connect")
                else:
                    st.error("Connection details provided but connection failed")
            except:
                st.error("Connection failed")
        else:
            st.error("Connection details incomplete")

# Tab 1: Fetch Tickets
with tab2:
    st.header("Fetch Jira Tickets")

    col1, col2 = st.columns([1, 1])

    with col1:
        status_options = ["All", "To Do", "In Progress", "Done", "Ready for QA", "Open", "Closed"]
        status_filter = st.selectbox("Filter by Status", status_options, index=0)

    with col2:
        max_results = st.number_input("Maximum Tickets", min_value=1, max_value=100, value=20)

    if st.button("Fetch Tickets"):
        if not JIRA_AVAILABLE:
            st.error("Please install the 'jira' package first")
        elif not all([jira_url, jira_email, jira_api_token, jira_project]):
            st.error("Please provide all Jira connection details in the sidebar")
        else:
            jira = connect_to_jira(jira_url, jira_email, jira_api_token)

            if jira:
                with st.spinner("Fetching tickets..."):
                    status = None if status_filter == "All" else status_filter
                    tickets = fetch_jira_tickets(jira, jira_project, status, max_results)

                    if tickets:
                        st.session_state.fetched_tickets = tickets
                        st.success(f"Fetched {len(tickets)} tickets")
                    else:
                        st.warning("No tickets found matching the criteria")

    # Display fetched tickets
    if st.session_state.fetched_tickets:
        ticket_data = []

        for issue in st.session_state.fetched_tickets:
            ticket_data.append({
                "Key": issue.key,
                "Summary": issue.fields.summary,
                "Type": issue.fields.issuetype.name,
                "Status": issue.fields.status.name,
                "Priority": issue.fields.priority.name if hasattr(issue.fields,
                                                                  'priority') and issue.fields.priority else "Not set"
            })

        df = pd.DataFrame(ticket_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No tickets fetched yet. Click 'Fetch Tickets' to retrieve tickets from Jira.")

# Tab 2: Generate Test Cases
with tab3:
    st.header("Generate Test Cases")

    # Option for working without Jira
    use_manual_input = st.checkbox("Work without Jira connection (manual input)")

    if use_manual_input:
        st.write("Enter ticket details manually:")
        manual_ticket = {
            'key': st.text_input("Ticket Key", value="MANUAL-123"),
            'summary': st.text_input("Summary", value=""),
            'description': st.text_area("Description", value=""),
            'issue_type': st.selectbox("Issue Type", ["Story", "Bug", "Task", "Epic"], index=0),
            'priority': st.selectbox("Priority", ["High", "Medium", "Low"], index=1),
            'components': [st.text_input("Components (comma separated)")],
            'acceptance_criteria': st.text_area("Acceptance Criteria")
        }

        if st.button("Generate Test Cases"):
            if not openai_api_key:
                st.error("Please provide OpenAI API key in the sidebar")
            else:
                with st.spinner("Generating test cases..."):
                    test_cases = generate_test_cases(manual_ticket, openai_api_key, ai_model)

                    if test_cases:
                        ticket_key = manual_ticket['key']
                        st.session_state.generated_test_cases[ticket_key] = test_cases
                        st.success("Test cases generated successfully!")
    else:
        # Option to enter ticket key manually or select from fetched tickets
        col1, col2 = st.columns([1, 2])

        with col1:
            input_method = st.radio("Input Method", ["Enter Ticket Key", "Select from Fetched"])

        with col2:
            if input_method == "Enter Ticket Key":
                ticket_key = st.text_input("Jira Ticket Key", placeholder="PROJ-123")
            else:
                if st.session_state.fetched_tickets:
                    ticket_options = [issue.key for issue in st.session_state.fetched_tickets]
                    ticket_key = st.selectbox("Select Ticket", ticket_options)
                else:
                    st.warning("No tickets fetched. Please go to the 'Fetch Tickets' tab first.")
                    ticket_key = None

        if ticket_key:
            if st.button("Generate Test Cases for " + ticket_key):
                if not openai_api_key:
                    st.error("Please provide OpenAI API key in the sidebar")
                elif not all([jira_url, jira_email, jira_api_token]):
                    st.error("Please provide all Jira connection details in the sidebar")
                else:
                    jira = connect_to_jira(jira_url, jira_email, jira_api_token)

                    if jira:
                        with st.spinner("Fetching ticket details..."):
                            ticket_details = get_ticket_details(jira, ticket_key)

                        if ticket_details:
                            st.subheader("Ticket Details")
                            st.write(f"**Summary:** {ticket_details['summary']}")

                            with st.expander("View full ticket details"):
                                st.write(f"**Description:** {ticket_details['description']}")
                                st.write(f"**Type:** {ticket_details['issue_type']}")
                                st.write(f"**Status:** {ticket_details['status']}")
                                st.write(f"**Priority:** {ticket_details['priority']}")
                                st.write(
                                    f"**Components:** {', '.join(ticket_details['components']) if ticket_details['components'] else 'None'}")
                                st.write(f"**Acceptance Criteria:** {ticket_details['acceptance_criteria']}")

                            with st.spinner("Generating test cases..."):
                                test_cases = generate_test_cases(ticket_details, openai_api_key, ai_model)

                                if test_cases:
                                    st.session_state.generated_test_cases[ticket_key] = test_cases
                                    st.success("Test cases generated successfully!")

    # Display generated test cases if available
    if 'key' in locals() and 'manual_ticket' in locals():
        ticket_key = manual_ticket['key']

    if 'ticket_key' in locals() and ticket_key and ticket_key in st.session_state.generated_test_cases:
        st.subheader("Generated Test Cases")
        st.markdown(st.session_state.generated_test_cases[ticket_key])

        col1, col2 = st.columns([1, 1])

        with col1:
            st.download_button(
                label="Download Test Cases",
                data=st.session_state.generated_test_cases[ticket_key],
                file_name=f"test_cases_{ticket_key}_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown"
            )

        with col2:
            if not use_manual_input and st.button("Save Test Cases to Jira"):
                if not all([jira_url, jira_email, jira_api_token]):
                    st.error("Please provide all Jira connection details in the sidebar")
                else:
                    jira = connect_to_jira(jira_url, jira_email, jira_api_token)

                    if jira:
                        with st.spinner("Saving to Jira..."):
                            success = save_test_cases_to_jira(jira, ticket_key,
                                                              st.session_state.generated_test_cases[ticket_key])

                            if success:
                                st.success("Test cases saved to Jira ticket!")

# Tab 3: Batch Processing
with tab4:
    st.header("Batch Test Case Generation")

    # Option for working without Jira
    use_manual_batch = st.checkbox("Work without Jira connection (manual batch input)")

    if use_manual_batch:
        st.write("Enter multiple ticket descriptions, one per line:")
        batch_descriptions = st.text_area("Each line should contain: TicketID | Summary | Description",
                                          height=200,
                                          help="Format: TICKET-123 | Add login feature | The user should be able to login...")

        if st.button("Generate Test Cases for Batch"):
            if not openai_api_key:
                st.error("Please provide OpenAI API key in the sidebar")
            elif not batch_descriptions:
                st.error("Please enter at least one ticket description")
            else:
                lines = batch_descriptions.strip().split('\n')
                progress_bar = st.progress(0)
                status_text = st.empty()

                for i, line in enumerate(lines):
                    parts = line.split('|')
                    if len(parts) >= 3:
                        ticket_key = parts[0].strip()
                        summary = parts[1].strip()
                        description = parts[2].strip()

                        status_text.text(f"Processing {ticket_key} ({i + 1}/{len(lines)})")

                        manual_ticket = {
                            'key': ticket_key,
                            'summary': summary,
                            'description': description,
                            'issue_type': "Story",
                            'priority': "Medium",
                            'components': [],
                            'acceptance_criteria': "Not provided"
                        }

                        test_cases = generate_test_cases(manual_ticket, openai_api_key, ai_model)
                        if test_cases:
                            st.session_state.generated_test_cases[ticket_key] = test_cases

                    progress_bar.progress((i + 1) / len(lines))

                status_text.text("All tickets processed!")
                st.success(f"Generated test cases for {len(lines)} tickets")
    else:
        st.info("This feature allows you to generate test cases for multiple tickets at once.")

        if not st.session_state.fetched_tickets:
            st.warning("No tickets fetched. Please go to the 'Fetch Tickets' tab first.")
        else:
            # Allow selection of multiple tickets
            ticket_options = {issue.key: issue.fields.summary for issue in st.session_state.fetched_tickets}
            selected_tickets = []

            st.write("Select tickets for batch processing:")

            col1, col2 = st.columns([1, 2])

            with col1:
                select_all = st.checkbox("Select All Tickets")

            if select_all:
                selected_tickets = list(ticket_options.keys())
                st.info(f"Selected all {len(selected_tickets)} tickets")
            else:
                for key, summary in ticket_options.items():
                    if st.checkbox(f"{key}: {summary}", key=f"select_{key}"):
                        selected_tickets.append(key)

            if selected_tickets:
                st.write(f"Selected {len(selected_tickets)} tickets")

                if st.button("Generate Test Cases for All Selected"):
                    if not openai_api_key:
                        st.error("Please provide OpenAI API key in the sidebar")
                    elif not all([jira_url, jira_email, jira_api_token]):
                        st.error("Please provide all Jira connection details in the sidebar")
                    else:
                        jira = connect_to_jira(jira_url, jira_email, jira_api_token)

                        if jira:
                            progress_bar = st.progress(0)
                            status_text = st.empty()

                            for i, ticket_key in enumerate(selected_tickets):
                                status_text.text(f"Processing {ticket_key} ({i + 1}/{len(selected_tickets)})")

                                ticket_details = get_ticket_details(jira, ticket_key)
                                if ticket_details:
                                    test_cases = generate_test_cases(ticket_details, openai_api_key, ai_model)
                                    if test_cases:
                                        st.session_state.generated_test_cases[ticket_key] = test_cases

                                progress_bar.progress((i + 1) / len(selected_tickets))

                            status_text.text("All tickets processed!")
                            st.success(f"Generated test cases for {len(selected_tickets)} tickets")

                            # Show results summary
                            st.subheader("Generated Test Cases Summary")
                            for key in selected_tickets:
                                if key in st.session_state.generated_test_cases:
                                    with st.expander(f"Test Cases for {key}"):
                                        st.markdown(st.session_state.generated_test_cases[key])

# Footer
st.markdown("---")
st.caption("AI Test Case Generator - Streamlining the QA process with AI")