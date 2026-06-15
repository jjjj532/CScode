# Phase 4: 高级特性 — Auth, Sharing, ACP, Enterprise

**Build Order:** Tasks 4.1–4.4 are independent and can be parallelized.

---

### Task 4.1: Auth/OAuth — Token management, OAuth flows

**Files:**
- Create: `src/cscode/auth/__init__.py`
- Create: `src/cscode/auth/tokens.py` — Token storage with encryption
- Create: `src/cscode/auth/github.py` — GitHub OAuth provider
- Create: `src/cscode/auth/openai_oauth.py` — OpenAI OAuth provider
- Create: `tests/test_auth_tokens.py`
- Create: `tests/test_auth_github.py`
- Create: `tests/test_auth_openai.py`

**Dependency:** Phase 1 (EventBus)

---

### Task 4.2: Session Sharing — Serialization, links, access control

**Files:**
- Create: `src/cscode/sharing/__init__.py`
- Create: `src/cscode/sharing/serializer.py` — Session export/import
- Create: `src/cscode/sharing/links.py` — Share link generation
- Create: `src/cscode/sharing/manager.py` — Share lifecycle management
- Create: `tests/test_sharing.py`

**Dependency:** Phase 1 (SessionManager, storage)

---

### Task 4.3: ACP Protocol — Agent Communication Protocol

**Files:**
- Create: `src/cscode/acp/__init__.py`
- Create: `src/cscode/acp/protocol.py` — ACP message types and routing
- Create: `src/cscode/acp/router.py` — Cross-agent message routing
- Create: `tests/test_acp.py`

**Dependency:** Phase 1 (EventBus)

---

### Task 4.4: Enterprise Features — Remote config, MDM, audit

**Files:**
- Create: `src/cscode/enterprise/__init__.py`
- Create: `src/cscode/enterprise/remote_config.py` — `.well-known` config
- Create: `src/cscode/enterprise/policies.py` — IAM-style policy engine
- Create: `src/cscode/enterprise/audit.py` — Audit logging
- Create: `tests/test_enterprise.py`

**Dependency:** Phase 1 (PermissionService)

---

### Task 4.5: Phase 4 final verification
