import streamlit as st
import ollama 
import sys_msgs
from bs4 import BeautifulSoup
import trafilatura
import requests

def initialize_session_state():
    if 'assistant_convo' not in st.session_state:
        st.session_state.assistant_convo = [sys_msgs.assistant_msg]
    if 'messages' not in st.session_state:
        st.session_state.messages = []

def search_or_not():
    sys_msg = sys_msgs.search_or_not_msg
    
    response = ollama.chat(
        model='llama3.1:8b',
        messages=[{'role':'system','content':sys_msg}, st.session_state.assistant_convo[-1]]
    )
    
    content = response['message']['content']
    st.sidebar.write(f'Search decision: {content}')
    
    return 'true' in content.lower()

def query_generator():
    sys_msg = sys_msgs.query_msg
    query_msg = f'CREATE A SEARCH QUERY FOR THIS PROMPT: \n{st.session_state.assistant_convo[-1]}'
    
    response = ollama.chat(
        model='llama3.1:8b',
        messages=[{'role':'system','content':sys_msg}, {'role':'user','content':query_msg}]
    )
    
    return response['message']['content']

def duckduckgo_search(query):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
    }
    url = f'https://html.duckduckgo.com/html/?q={query}'
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    
    for i, result in enumerate(soup.find_all('div', class_='result'), start=1):
        if i > 10:
            break
        
        title_tag = result.find('a', class_='result__a')
        if not title_tag:
            continue
        
        link = title_tag['href']
        snippet_tag = result.find('a', class_='result__snippet')
        snippet = snippet_tag.text.strip() if snippet_tag else 'No description available'

        results.append({
            'id': i,
            'link': link,
            'search_description': snippet
        })
        
    return results

def best_search_result(s_results, query):
    sys_msg = sys_msgs.best_search_msg
    best_msg = f'SEARCH_RESULTS: {s_results} \nUSER_PROMPT: {st.session_state.assistant_convo[-1]} \nSEARCH_QUERY: {query}'
    
    for _ in range(2):
        try:
            response = ollama.chat(
                model='llama3.1:8b',
                messages=[{'role': 'system', 'content': sys_msg}, {'role': 'user', 'content': best_msg}]
            )
            return int(response['message']['content'])
        except:
            continue
    
    return 0

def scrape_webpage(url):
    try:
        downloaded = trafilatura.fetch_url(url=url)
        return trafilatura.extract(downloaded, include_formatting=True, include_links=True)
    except Exception as e:
        return None

def contains_data_needed(search_content, query):
    sys_msg = sys_msgs.contains_data_msg
    needed_prompt = f'PAGE_TEXT: {search_content} \nUSER_PROMPT: {st.session_state.assistant_convo[-1]} \nSEARCH_QUERY: {query}'
    
    response = ollama.chat(
        model='llama3.1:8b',
        messages=[{'role':'system', 'content': sys_msg}, {'role':'user', 'content': needed_prompt}]
    )
    
    return 'true' in response['message']['content'].lower()

def ai_search():
    with st.spinner('Searching the web...'):
        st.sidebar.write('Generating search query...')
        search_query = query_generator()
        
        if search_query[0] == '"':
            search_query = search_query[1:-1]
        
        st.sidebar.write(f'Search query: {search_query}')
        
        search_results = duckduckgo_search(search_query)
        context_found = False
        context = None
        
        while not context_found and len(search_results) > 0:
            best_result = best_search_result(s_results=search_results, query=search_query)
            try:
                page_link = search_results[best_result]['link']
                st.sidebar.write(f'Checking source: {page_link}')
            except:
                st.sidebar.write('Failed to select best result, trying again...')
                continue
            
            page_text = scrape_webpage(page_link)
            search_results.pop(best_result)
            
            if page_text and contains_data_needed(search_content=page_text, query=search_query):
                context = page_text
                context_found = True
                
        return context

def get_assistant_response(prompt, context=None):
    if context:
        prompt = f'SEARCH RESULT: {context} \n\nUSER PROMPT: {prompt}'
    else:
        prompt = f'USER PROMPT: {prompt}'
    
    st.session_state.assistant_convo.append({'role': 'user', 'content': prompt})
    
    with st.spinner('Thinking...'):
        response = ollama.chat(
            model='llama3.1:8b',    
            messages=st.session_state.assistant_convo
        )
    
    assistant_response = response['message']['content']
    st.session_state.assistant_convo.append({'role': 'assistant', 'content': assistant_response})
    return assistant_response

def main():
    st.title("AI Search Assistant")
    initialize_session_state()
    
    # Sidebar for debug info
    st.sidebar.title("Debug Information")
    
    # Chat interface
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # User input
    if prompt := st.chat_input("What would you like to know?"):
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Add to conversation history
        st.session_state.assistant_convo.append({'role': 'user', 'content': prompt})
        
        # Check if search is needed
        if search_or_not():
            context = ai_search()
            st.session_state.assistant_convo = st.session_state.assistant_convo[:-1]
            
            if not context:
                error_msg = ("I was unable to find reliable information from my web search. "
                           "Would you like me to try searching again or respond without web search context?")
                with st.chat_message("assistant"):
                    st.markdown(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                return
        else:
            context = None
        
        # Get and display assistant response
        assistant_response = get_assistant_response(prompt, context)
        with st.chat_message("assistant"):
            st.markdown(assistant_response)
        st.session_state.messages.append({"role": "assistant", "content": assistant_response})

if __name__ == '__main__':
    main()