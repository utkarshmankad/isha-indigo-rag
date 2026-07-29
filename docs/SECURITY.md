# Security Documentation for ISHA IndiGo RAG Assistant

## Overview

This document describes the security measures implemented in the ISHA IndiGo RAG Assistant to protect against common vulnerabilities and misuse.

## Security Architecture

ISHA implements multiple layers of security:

1. **Input Validation & Sanitization** - Prevents injection attacks and validates user queries
2. **Prompt Injection Defense** - Protects LLM prompts from manipulation
3. **Rate Limiting** - Prevents API abuse and cost escalation
4. **Secret Management** - Proper .gitignore configuration and environment variable usage
5. **CORS Configuration** - Controlled cross-origin access

---

## 1. Input Validation & Sanitization (S1-T3)

### Implemented Features

#### PII Detection
- Detects and warns about Personally Identifiable Information (PII)
- PII types detected:
  - **PNR** - Passenger Name Record (12-digit pattern)
  - **Email** - Email address patterns
  - **Phone** - Phone number patterns
  - **Maiden Name** - Mother's maiden name patterns
  - **Passport** - Passport number patterns

#### Attack Pattern Detection
Detects and blocks:
- **Nested curly braces** - Potential output escaping attempts
- **SQL Injection** - SELECT/INSERT/UPDATE/DELETE syntax
- **Bash Execution** - Command structure patterns
- **Forbidden Content** - Malware, ransomware, phishing, backdoor references

#### Query Length Validation
- Minimum: 3 characters
- Maximum: 2000 characters
- Warning: Queries below 50 characters

### Implementation

```python
from src.security.validator import QueryValidator

results = QueryValidator.validate_input(query, airline)
if not results.is_valid:
    st.error(results.reason)
```

---

## 2. Prompt Injection Defense (S1-T4)

### Features

#### User Query Protection
Scans for:
- "ignore previous instructions"
- "forget what I said"
- "override previous"
- System manipulation keywords
- Extraction attempts (role:, instructions:, etc.)

#### Context Protection
- Detects hidden instructions in retrieved context
- Blocks prompt extraction via role: or instructions: prefixes

#### System Prompt Hardening
- Enforced structure with double newlines
- Required delimiters
- Clear system prompt template
- Internal statement before citations

### Implementation

```python
from src.security.prompt_protection import PromptGuard

# Protection in retriever
prompt = PromptGuard.wrap_system_prompt(
    context=context,
    user_question="",
    airline=airline,
    contact=contact
)
```

---

## 3. Rate Limiting (S1-T5)

### Configuration

| Limit Type | Rate | Scope | Default |
|------------|------|-------|---------|
| Session | 30 queries/minute | Per Streamlit session | 30 QPM |
| Session | 500 queries/hour | Per Streamlit session | 500 QPH |
| Global | 100 queries/minute | All sessions combined | 100 QPM |
| Global | 1000 queries/hour | All sessions combined | 1000 QPH |

### How It Works

- Track queries in `session_state`
- Calculate new queries based on oldest query timestamp
- Automatic cleanup of expired queries
- Returns remaining quota on success

### Integration

```python
from src.security.rate_limiter import RateLimiter

rate_result = RateLimiter.check_rate_limit()
if not rate_result.is_allowed:
    st.error(rate_result.reason)
    return  # Block query processing
```

---

## 4. Secret Management (S1-T2)

### .gitignore Protection

All sensitive files are excluded:

```
.env                      # Environment variables
.env.local                # Local overrides
.env.*                    # All env files except .env.example
*.key                     # API keys
*.pem                     # Private keys
*_api_key.txt             # API key files
.secrets.toml             # Streamlit secrets
logs/                     # Log files
```

### Environment Variables

Required credentials loaded from environment:

```bash
OPENAI_API_KEY=sk-...      # For embeddings and answer generation
ANTHROPIC_API_KEY=sk-ant-... # For Claude answers (optional)
QDRANT_URL=https://...     # Qdrant Cloud URL
QDRANT_API_KEY=tk-...      # Qdrant authentication
```

### Best Practices

1. Never commit `.env` files
2. Use `.env.example` as template
3. Rotate API keys regularly
4. Use separate credentials for dev/staging/prod
5. Use Streamlit secrets for production deployments

---

## 5. CORS Configuration (S1-T6)

### Streamlit Defaults

Streamlit handles CORS automatically with the following defaults:
- **CORS_ALLOW_REREQUEST**: True (allows reruns from same origin)
- **Server headers**: Streamlit app headers

### Configuration

For production deployments:

**Streamlit Community Cloud:**
- Public repository
- Secrets configured in `.streamlit/secrets.toml`
- App hosted on `share.streamlit.io`

**Self-hosted deployment:**
- Configure Streamlit CORS settings in `streamlit.toml`:
  ```toml
  [server]
  corsAllowCORS = false  # Only allow specific origins if needed
  corsAllowOrigins = ["https://yourdomain.com"]
  ```

### XSS Prevention

- User input is typed as Markdown with limited HTML
- No raw HTML storage
- `render_sources` uses proper Markdown rendering
- PII is detected and warned but not displayed in UI

---

## Security Checklist

### Development Setup
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in all API keys
- [ ] Run `start.sh --reset` to populate Qdrant
- [ ] Verify `.gitignore` excludes all secrets

### Testing
- [ ] Validate queries: `QueryValidator.validate_input()`
- [ ] Test prompt injection attempts
- [ ] Verify rate limits block excessive queries
- [ ] Check PII detection with test data

### Production Deployment
- [ ] Use Streamlit secrets (`.streamlit/secrets.toml`)
- [ ] Enable HTTPS
- [ ] Rotate API keys
- [ ] Set up monitoring and alerts
- [ ] Test migration after upgrading dependencies

---

## Attack Scenarios & Mitigations

| Attack Type | Risk | Mitigation | Status |
|-------------|------|------------|--------|
| SQL Injection | High | Query validation, sanitization | ✅ S1-T3 |
| Prompt Injection | High | PromptGuard wrappers, system template | ✅ S1-T4 |
| API Abuse | High | Rate limiting, session throttling | ✅ S1-T5 |
| Secret Leak | Critical | .gitignore, env variables | ✅ S1-T2 |
| XSS attacks | Medium | Markdown rendering, HTML stripping | ✅ Reviewed |
| PII Exposure | Medium | PII detection, masking | ✅ S1-T3 |
| Cost Escalation | High | Rate limiting, token monitoring | ✅ S1-T5 |

---

## Future Security Enhancements

Sprints 2-4 include additional improvements:

### Sprint 2: Reliability & Observability
- Circuit breakers for LLM API calls
- Detailed logging without sensitive data
- Health check endpoints
- Error boundaries for graceful degradation

### Sprint 3: Code Quality & Testing
- Dependency audits
- Increased test coverage
- Code security reviews

### Sprint 4: Performance & Scale
- Cache layer for common queries
- Connection pooling for vector store
- Load testing and benchmarks
- Backup and restore strategy

---

## Incident Response

### If an API Key is Exposed:

1. **Rotate immediately**: Generate new keys and update all secrets
2. **Check logs**: Look for unauthorized access via access logs
3. **Notify users**: If credentials shared publicly
4. **Audit usage**: Review API usage for anomalous patterns

### If PII is Detected:

1. **Do not store**: Ensure no PII persisted to storage
2. **Block future**: Ensure PII filtering active
3. **Log incident**: Document date, pattern, user
4. **Monitor**: Watch for repeated attempts

### If Rate Limiting is Bypassed:

1. **Increase limits**: Temporarily raise QPM limits
2. **Implement proxy cache**: For high-traffic queries
3. **Add IP blocking**: For repeated abuse
4. **Contact provider**: If under DDoS attack

---

## API Key Rotation

When rotating keys:

```bash
# 1. Generate new keys
# 2. Update .env
OPENAI_API_KEY=sk-proj-new-key
QDRANT_API_KEY=new-qkey

# 3. Redeploy if using secrets
# 4. Test all functionality
# 5. Remove old key from API provider console
```

---

## Support & Contact

For security-related questions:
- Email: [your email]
- Report vulnerabilities: [vulnerability reporting process]

---

**Last Updated**: 2026-07-30
**Version**: 0.1.0
**Status**: Sprint 1 Complete — All critical security measures implemented