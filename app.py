import streamlit as st
from backend.agent import QueryAgent
from backend.data_handler import DataHandler
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Olist E-commerce Data Explorer",
    page_icon="🛍️",
    layout="wide"
)

# Initialize components
@st.cache_resource
def init_components():
    data_handler = DataHandler()
    agent = QueryAgent(data_handler)
    return data_handler, agent

def main():
    st.title("🛍️ Olist E-commerce Data Explorer")
    st.markdown("""
    Ask questions about the Brazilian E-commerce data in natural language!
    
    Examples:
    - What are the top 5 product categories by revenue?
    - Show me the average order value by month
    - Which state has the most customers?
    """)
    
    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            # Only plot when a valid visualization object is present
            viz = message.get("visualization")
            if viz is not None:
                try:
                    st.plotly_chart(viz)
                except Exception:
                    # If it's not a valid Plotly figure, render it generically
                    st.write(viz)
    
    # Chat input
    if prompt := st.chat_input("Ask about the Olist data..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Get response from agent
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                data_handler, agent = init_components()
                response = agent.process_query(prompt)
                
                # Display response
                st.markdown(response["text"])
                viz = response.get("visualization")
                if viz is not None:
                    try:
                        st.plotly_chart(viz)
                    except Exception:
                        st.write(viz)
                
                # Add assistant response to chat history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response["text"],
                    "visualization": response.get("visualization", None)
                })

if __name__ == "__main__":
    main()