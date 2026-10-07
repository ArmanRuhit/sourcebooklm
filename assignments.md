# ChaibookLM — Assignment

**Course:** GenAI with JS 2026 · **Tag:** GenAI

## Timeline

- **Start:** 22 Jul 2026, 9:30 pm
- **Due:** 1 Jan 2027, 12:29 am
- **Eval Begins:** 1 Jan 2027, 1:00 am
- **Eval Ends:** 1 Feb 2027, 12:29 am

## Instructions

Build an AI-powered research assistant inspired by **Gemini Notebook** that allows users to upload multiple knowledge sources, ask questions grounded in those sources, and receive answers with proper citations.

The objective of this assignment is to understand how modern RAG (Retrieval Augmented Generation) systems work by building an end-to-end application that can ingest, index, retrieve and answer questions from multiple source types.

Your application should support multiple notebooks or workspaces where each notebook can contain multiple knowledge sources.

### Your application should support the following source types:

- PDF
- Plain Text
- Website URL
- YouTube Video
- VTT / Transcript file

For each uploaded source:

- Extract the content
- Chunk the content
- Generate embeddings
- Store embeddings in a vector database
- Track indexing status
- Allow the source to be removed or re-indexed

Your UI should clearly indicate:

- Source is uploading
- Source is indexing
- Source is ready for querying

Each notebook should maintain its own isolated knowledge base.

### Querying

Users should be able to ask natural language questions.

Your system should:

- Retrieve relevant chunks
- Send retrieved context to the LLM
- Generate grounded answers
- Display citations for every answer
- Allow users to inspect the original source that produced the answer

The user should never receive an answer without knowing where it came from.

### Source Viewer

Selecting a citation should open the original source.

Examples:

- PDF opens at the relevant section
- Website opens or previews
- YouTube opens at the referenced timestamp if possible
- Text source highlights the relevant section
- Transcript highlights the cited chunk

### Bonus

- Given list of YouTube videos/ playlists as sources help the user learn a concept by pin-pointing the concepts with roadmap that are personalized based on the sources.
- Create a Podcast out of your sources in which a male/female voice-over comes for your documents on which you can listen

### Mock up

![ChaibookLM mock up 1](https://masterji-app.s3.ap-south-1.amazonaws.com/chat-uploads/bc99fe5d-0dac-4cb9-8985-30e83bb20a1f/1784736970439-fxh6hxj6iyr-chat-image-1784736969330.webp)

![ChaibookLM mock up 2](https://masterji-app.s3.ap-south-1.amazonaws.com/chat-uploads/bc99fe5d-0dac-4cb9-8985-30e83bb20a1f/1784736978670-3yalbjzjwd2-chat-image-1784736977546.webp)

## Submission Instructions

- Public GitHub Repository
- Live Deployment
- README
- Demo Video

## Evaluation Parameters

### 1. Notebook Management (10 Marks)

- Multiple notebooks
- Create, rename and delete notebooks
- Notebook isolation
- Clean UX

### 2. Source Ingestion (20 Marks)

- Supports multiple source types
- Upload flow works correctly
- Indexing pipeline works
- Status indicators are shown
- Source removal works

### 3. RAG Pipeline (20 Marks)

- Chunking strategy
- Embedding generation
- Vector search
- Metadata handling
- Retrieval quality

### 4. AI Responses (15 Marks)

- Responses are grounded
- Streaming responses
- Good prompt construction
- Minimal hallucinations
- Proper formatting

### 5. Citations and Source Attribution (15 Marks)

- Every answer includes citations
- Users can inspect original sources
- Metadata is preserved correctly
- Citation UX is clear

### 6. Architecture and Code Quality (10 Marks)

- Clean folder structure
- Separation of concerns
- Reusable components
- Error handling
- Maintainable code

### 7. UI and User Experience (10 Marks)

- Responsive design
- Loading states
- Empty states
- Smooth interactions
- Clean notebook experience

### 8. README and Documentation (10 Marks)

- Clear setup instructions
- Architecture explanation
- Retrieval flow documented
- Environment variables listed
- Project is easy to run

### 9. Demo Video (10 Marks)

- Features demonstrated clearly
- End-to-end flow shown
- Technical decisions explained
- Video is easy to follow

### 10. Overall Engineering Thoughtfulness (10 Marks)

- Good system design
- Practical implementation choices
- Retrieval quality considered
- Production-oriented thinking
- Clear understanding of modern RAG systems

**Max Marks: 100**
