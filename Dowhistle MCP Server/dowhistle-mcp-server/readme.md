# DoWhistle MCP Server

## Submission Details

*   **Team Name**: DoWhistle
*   **Team Members**: Raja Appachi , Nishanth M, Mithran Raja, Nitin Murali
*   **Hackathon Theme**: Theme 2 - Agents and tools need a reliable interface layer—secure, permissioned, and observable—to interact with real-world APIs.


## Project Structure

```
mcp-server/
├── config/
│   └── settings.py              # Configuration management
├── utils/
│   └── http_client.py          # HTTP client with retry logic
├── agents/
│   ├── __init__.py
│   ├── search.py               # Search functionality
│   ├── auth.py                 # Authentication tools
│   ├── whistle.py              # Whistle management
│   └── user.py                 # User settings management
├── tests/
│   ├── __init__.py
│   ├── test_agents.py          # Agent tests
│   └── conftest.py             # Test configuration
├── app.py                      # Entry point
├── pyproject.toml              # Dependencies
├── Dockerfile                  # Container configuration
├── docker-compose.yml          # Multi-container setup
├── .env.example                # Environment variables template
└── README.md                   # Documentation
```

## Agents and Tools

### 1. Search Agent (`agents/search.py`)
- **Tool**: `search`
- **Purpose**: Search functionality through Express API

### 2. Authentication Agent (`agents/auth.py`)
- **Tools**: 
  - `sign_in`: User authentication
  - `verify_otp`: OTP verification
  - `resend_otp`: Resend OTP code
- **Purpose**: Handle all authentication flows

### 3. Whistle Agent (`agents/whistle.py`)
- **Tools**:
  - `create_whistle`: Create new whistle reports  
  - `list_whistles`: List whistles with pagination
- **Purpose**: Complete whistle management

### 4. User Agent (`agents/user.py`)
- **Tools**:  
  - `toggle_visibility`: Control user visibility
  
- **Purpose**: User preference management

## Installation and Setup

### Prerequisites
- Python 3.11+
- Access to your Express.js API
- Docker (optional)

### Local Development

1. **Clone and setup**:
```bash
git clone https://github.com/OneWhistle/dowhistle-mcp-server
cd dowhistle-mcp-server

uv sync

source .venv/bin/activate  # On Windows: .venv\Scripts\activate

```

1. **Configuration**:
```bash
cp env.example .env
# Edit .env with your settings
```

1. **Run the server**:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 
```

### Docker Deployment

1. **Build and run**:
```bash
docker compose up -d --build 
(or)

docker-compose up --build 
```

2. **Production deployment**:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Configuration

All configuration is managed through environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `EXPRESS_API_BASE_URL` | Your Express API base URL | `https://dowhistle.herokuapp.com/v3` |
| `PORT` | MCP server port | `8000` |
| `OPENAI_API_KEY` | OPENAI_API_KEY authentication key | `None` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_RETRIES` | API request retry count | `3` |
| `RETRY_DELAY` | Retry delay in seconds | `1.0` |
| `RATE_LIMIT_PER_MINUTE` | Rate limit per minute | `60` |

---


## Demo Video

https://www.youtube.com/watch?v=wOn_jo6Re60

## What We'd Do with More Time

With more time, we would focus on:

**Develop a dedicated web and mcp-client**: 

- **DoWhistle-MCP-Gateway**: Containing the MCP Client and integration with OpenAI for agentic capabilities.

Repo: [DoWhistle-MCP-Gateway](https://github.com/OneWhistle/dowhistle-mcp-gateway)

- **DoWhistle-MCP-Web**: Housing the ChatBot interface for user interaction.

Repo: [DoWhistle-MCP-Web](https://github.com/OneWhistle/dowhistle-mcp-web)

## Smithery Link for MCP Server

👉 [Smithery dowhistle-mcp-server](https://smithery.ai/server/@mr-nishanth/dowhistle-mcp-server)


