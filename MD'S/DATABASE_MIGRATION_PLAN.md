# MongoDB Atlas Migration Plan
## Natural CI/CD Pipeline AI — Database Migration Strategy

**Version:** 1.0  
**Date:** 2026-08-25  
**Status:** Draft → Implementation  

---

## 1. Migration Overview

### 1.1 Goal
Migrate from **SQLAlchemy + SQLite/PostgreSQL** to **MongoDB Atlas** (cloud-hosted NoSQL document database) while:
- Preserving all business logic
- Maintaining the existing test suite
- Ensuring zero data loss
- Following cloud-native best practices

### 1.2 Why MongoDB Atlas?
| Criterion | SQLite/PostgreSQL | MongoDB Atlas |
|-----------|-------------------|---------------|
| **Schema flexibility** | Rigid schema | Dynamic document schema |
| **Cloud-native** | Manual setup | Fully managed |
| **Horizontal scaling** | Difficult | Built-in sharding |
| **JSON-native** | TEXT columns only | Native BSON documents |
| **Free tier** | N/A | M0 cluster (512 MB) |
| **TTL indexes** | Cron jobs | Native expiration |
| **Atlas Search** | External | Built-in full-text search |
| **Atlas Charts** | External | Native visualization |

### 1.3 Technology Stack
- **ODM:** MongoEngine (Flask integration via `flask-mongoengine`)
- **Native driver:** PyMongo (for low-level operations)
- **Migration tool:** Custom one-shot script
- **Testing:** `mongomock` for in-memory tests
- **Indexes:** Compound indexes per query pattern

---

## 2. Current Data Model (SQLAlchemy)

### 2.1 Tables to Migrate (15 total)

| # | Model | Table | Records (est.) | Critical |
|---|-------|-------|----------------|----------|
| 1 | `User` | `users` | 100-10K | YES |
| 2 | `UserProfile` | `user_profiles` | 100-10K | YES |
| 3 | `EmailOTP` | `email_otps` | 1K-100K | YES |
| 4 | `GithubConnection` | `github_connections` | 100-10K | YES |
| 5 | `AuditLog` | `audit_logs` | 10K-1M | YES |
| 6 | `Repository` | `repositories` | 100-10K | YES |
| 7 | `Project` | `projects` | 1K-100K | YES |
| 8 | `Pipeline` | `pipelines` | 1K-100K | NO (legacy) |
| 9 | `WorkflowTemplate` | `workflow_templates` | 10-100 | NO |
| 10 | `Deployment` | `deployments` | 1K-100K | YES |
| 11 | `WorkflowLog` | `workflow_logs` | 10K-1M | NO (legacy) |
| 12 | `CloudDeployment` | `cloud_deployments` | 1K-100K | YES |
| 13 | `AutomationStep` | `automation_steps` | 1K-100K | YES |
| 14 | `GeneratedWorkflow` | `generated_workflows` | 1K-100K | YES |
| 15 | `SimulationRun` | `simulation_runs` | 1K-100K | YES |
| 16 | `DeploymentServer` | `deployment_servers` | 1-100 | NO |
| 17 | `ErrorReport` | `error_reports` | 1K-100K | YES |
| 18 | `Notification` | `notifications` | 1K-100K | NO |
| 19 | `Analytics` | `analytics` | 10K-1M | NO |
| 20 | `AIPrediction` | `ai_predictions` | 1K-100K | NO |

### 2.2 Relationships (Foreign Keys)

```
User (1) ─── (N) EmailOTP
User (1) ─── (1) UserProfile
User (1) ─── (N) GithubConnection
User (1) ─── (N) AuditLog
User (1) ─── (N) Project [via created_by]
User (1) ─── (N) Repository
User (1) ─── (N) Notification
User (1) ─── (N) Pipeline
User (1) ─── (N) Deployment
User (1) ─── (N) Analytics
User (1) ─── (N) AIPrediction

Repository (1) ─── (N) Pipeline
Repository (1) ─── (N) Analytics

Project (1) ─── (N) AutomationStep
Project (1) ─── (N) GeneratedWorkflow
Project (1) ─── (N) SimulationRun

Pipeline (1) ─── (N) Deployment
Pipeline (1) ─── (N) WorkflowLog
Pipeline (1) ─── (N) ErrorReport
Pipeline (1) ─── (N) AIPrediction

Deployment (1) ─── (N) CloudDeployment
Deployment (N) ─── (1) DeploymentServer
```

### 2.3 Current SQLAlchemy Patterns

**Query types used:**
- `db.session.get(Model, id)` — primary key lookup
- `Model.query.filter_by(...)` — equality filters
- `Model.query.filter(Model.field == value)` — comparison filters
- `Model.query.filter(...).order_by(...).limit(N)` — pagination
- `Model.query.filter(...).first()` / `.all()` — fetch patterns
- `db.session.add(model)` / `db.session.delete(model)` — mutations
- `db.session.commit()` — transaction boundary

---

## 3. Target MongoDB Document Model

### 3.1 Collection Strategy

**Approach:** One collection per model with embedded sub-documents for 1:1 relationships and referenced documents for 1:N relationships.

### 3.2 Document Schemas

#### 3.2.1 `users` Collection

```json
{
  "_id": ObjectId("..."),
  "email": "user@example.com",
  "password_hash": "$argon2id$...",
  "github_id": "12345678",
  "google_id": "987654321",
  "name": "John Doe",
  "avatar_url": "https://...",
  "role": "developer",
  "email_verified": true,
  "is_admin": false,
  "created_at": ISODate("2026-01-15T..."),
  "updated_at": ISODate("2026-01-15T..."),
  
  // Embedded: UserProfile (1:1)
  "profile": {
    "github_connected": true,
    "github_access_token": "gho_...",
    "github_login": "octocat",
    "notification_email": "user@example.com",
    "created_at": ISODate("..."),
    "updated_at": ISODate("...")
  }
}
```

**Indexes:**
- `{ email: 1 }` UNIQUE
- `{ github_id: 1 }` SPARSE
- `{ google_id: 1 }` SPARSE UNIQUE
- `{ created_at: -1 }`

#### 3.2.2 `email_otps` Collection

```json
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "purpose": "verify_email",
  "code_hash": "abc123...",
  "attempts": 0,
  "expires_at": ISODate("..."),
  "consumed_at": null,
  "created_at": ISODate("...")
}
```

**Indexes:**
- `{ user_id: 1, purpose: 1, consumed_at: 1 }` (compound)
- `{ expires_at: 1 }` TTL (auto-delete after 24h)

#### 3.2.3 `github_connections` Collection

```json
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "github_id": "12345678",
  "access_token": "gho_...",
  "login": "octocat",
  "created_at": ISODate("...")
}
```

**Indexes:**
- `{ user_id: 1 }`
- `{ github_id: 1 }` UNIQUE

#### 3.2.4 `audit_logs` Collection

```json
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "action": "user.login.success",
  "resource_type": "user",
  "resource_id": "...",
  "status": "success",
  "details": { "ip": "127.0.0.1" },
  "ip_address": "127.0.0.1",
  "user_agent": "Mozilla/5.0...",
  "created_at": ISODate("...")
}
```

**Indexes:**
- `{ user_id: 1, created_at: -1 }` (compound)
- `{ action: 1, created_at: -1 }` (compound)
- `{ created_at: -1 }` (for time-range queries)

#### 3.2.5 `repositories` Collection

```json
{
  "_id": ObjectId("..."),
  "user_id": ObjectId("..."),
  "github_repo_id": "12345678",
  "name": "my-repo",
  "full_name": "octocat/my-repo",
  "visibility": "public",
  "default_branch": "main",
  "connected_at": ISODate("..."),
  "webhook_installed": false,
  "last_synced": ISODate("...")
}
```

**Indexes:**
- `{ user_id: 1, github_repo_id: 1 }` UNIQUE
- `{ full_name: 1 }`

#### 3.2.6 `projects` Collection (Phase 2)

```json
{
  "_id": ObjectId("..."),
  "created_by": ObjectId("..."),
  "repo_url": "https://github.com/...",
  "repo_owner": "octocat",
  "repo_name": "my-repo",
  "default_branch": "main",
  "status": "pending_analysis",
  "detected_stack": {
    "language": "python",
    "framework": "flask",
    "package_manager": "pip",
    "has_dockerfile": true,
    "has_tests": true,
    "has_ci": false,
    "node_version": null,
    "python_version": "3.11",
    "test_framework": "pytest",
    "lint_config": ".flake8"
  },
  "readiness_score": 85,
  "error_message": null,
  "created_at": ISODate("..."),
  "updated_at": ISODate("..."),
  "version_id": 1
}
```

**Indexes:**
- `{ created_by: 1, created_at: -1 }`
- `{ repo_owner: 1, repo_name: 1 }` (for webhook matching)
- `{ status: 1 }`

#### 3.2.7 `automation_steps` Collection (Embedded in Project)

**Decision:** Keep as separate collection for queryability.

```json
{
  "_id": ObjectId("..."),
  "project_id": ObjectId("..."),
  "step_key": "test",
  "title": "Run pytest",
  "description": "...",
  "recommended": true,
  "approved": false,
  "yaml_snippet_preview": "- run: pytest",
  "created_at": ISODate("...")
}
```

**Indexes:**
- `{ project_id: 1 }`

#### 3.2.8 `generated_workflows` Collection

```json
{
  "_id": ObjectId("..."),
  "project_id": ObjectId("..."),
  "filename": ".github/workflows/ci.yml",
  "yaml_content": "name: CI\non: [push]...",
  "pr_url": "https://github.com/.../pull/123",
  "pr_number": 123,
  "pr_status": "draft",
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

**Indexes:**
- `{ project_id: 1, created_at: -1 }`
- `{ pr_status: 1 }`

#### 3.2.9 `simulation_runs` Collection

```json
{
  "_id": ObjectId("..."),
  "project_id": ObjectId("..."),
  "injected_error_type": "syntax_error",
  "injected_file": "app.py",
  "injected_diff": "--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,2 @@\n+invalid",
  "pipeline_log": "...",
  "ai_diagnosis": "...",
  "ai_fix_diff": "...",
  "status": "running",
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

**Indexes:**
- `{ project_id: 1, created_at: -1 }`
- `{ status: 1 }`

#### 3.2.10 `deployments` Collection

```json
{
  "_id": ObjectId("..."),
  "project_id": ObjectId("..."),  // Direct reference (replaces pipeline_id)
  "pipeline_id": ObjectId("..."), // Legacy, keep for compat
  "environment": "staging",
  "status": "running",
  "deployed_at": ISODate("..."),
  "finished_at": null,
  "server_id": ObjectId("..."),
  "version_id": 1,
  
  // Embedded: CloudDeployment (1:1)
  "cloud_deployment": {
    "aws_instance_id": "i-1234...",
    "status": "running",
    "logs_url": "s3://...",
    "created_at": ISODate("...")
  }
}
```

**Indexes:**
- `{ project_id: 1, deployed_at: -1 }`
- `{ status: 1, deployed_at: -1 }`

#### 3.2.11 `deployment_servers` Collection (Legacy)

```json
{
  "_id": ObjectId("..."),
  "name": "prod-us-east-1",
  "hostname": "ec2-1-2-3-4.compute.amazonaws.com",
  "ssh_user": "ubuntu",
  "ssh_key_path": "/path/to/key",
  "region": "us-east-1",
  "created_at": ISODate("...")
}
```

#### 3.2.12 `error_reports` Collection

```json
{
  "_id": ObjectId("..."),
  "pipeline_id": ObjectId("..."),
  "project_id": ObjectId("..."),  // Add direct reference
  "title": "Health check failed",
  "description": "EC2 instance unhealthy...",
  "severity": "critical",
  "resolved": false,
  "detected_at": ISODate("...")
}
```

**Indexes:**
- `{ pipeline_id: 1, detected_at: -1 }`
- `{ project_id: 1, resolved: 1 }`
- `{ severity: 1, resolved: 1 }`

#### 3.2.13 Remaining Collections

Keep similar structure: `workflow_templates`, `pipelines`, `workflow_logs`, `notifications`, `analytics`, `ai_predictions`.

---

## 4. Migration Architecture

### 4.1 Layered Architecture

```
┌─────────────────────────────────────────┐
│   Flask Routes (auth.py, projects.py)  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   Services (analyze, deploy, github)    │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   Repository Layer (NEW)                │
│   - UserRepository                      │
│   - ProjectRepository                   │
│   - DeploymentRepository                │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   MongoDB Documents (MongoEngine)       │
│   - User, Project, Deployment, ...      │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│   MongoDB Atlas (Cloud)                 │
└─────────────────────────────────────────┘
```

### 4.2 Repository Pattern

Each domain has a repository class that encapsulates MongoDB queries:

```python
# backend/repositories/user_repository.py
from backend.models_mongo import User
from mongoengine import DoesNotExist, NotUniqueError

class UserRepository:
    @staticmethod
    def find_by_email(email: str) -> User | None:
        return User.objects(email=email.lower()).first()
    
    @staticmethod
    def find_by_id(user_id: str) -> User | None:
        try:
            return User.objects.get(id=user_id)
        except DoesNotExist:
            return None
    
    @staticmethod
    def create(email, password_hash, **kwargs) -> User:
        user = User(email=email.lower(), password_hash=password_hash, **kwargs)
        user.save()
        return user
```

---

## 5. Implementation Phases

### Phase 1: Setup & Configuration (1 day)

**Tasks:**
- [ ] Add MongoDB dependencies to `requirements.txt`
- [ ] Create MongoDB Atlas account & free M0 cluster
- [ ] Configure IP whitelist (0.0.0.0/0 for dev)
- [ ] Create database user with read/write permissions
- [ ] Get connection string: `mongodb+srv://user:pass@cluster.mongodb.net/pipeline_sh`
- [ ] Add `MONGO_URI` to `.env.example`
- [ ] Update `backend/config.py` with MongoDB settings
- [ ] Set up `flask-mongoengine` integration

**Files to modify:**
- `backend/requirements.txt`
- `backend/config.py`
- `.env.example`
- `backend/app.py` (replace SQLAlchemy init with MongoEngine init)

### Phase 2: Define Document Models (2 days)

**Tasks:**
- [ ] Create `backend/models_mongo.py` with all MongoEngine documents
- [ ] Define indexes for each document
- [ ] Add validation rules
- [ ] Add `to_dict()` methods
- [ ] Replace `JSON-serialized text` columns with native dict/list fields

**Files to create:**
- `backend/models_mongo.py` (complete rewrite as MongoEngine documents)

### Phase 3: Create Repository Layer (2 days)

**Tasks:**
- [ ] Create `backend/repositories/` package
- [ ] Implement `UserRepository`, `ProjectRepository`, etc.
- [ ] Translate SQL queries to MongoEngine queries
- [ ] Add unit tests for each repository

**Files to create:**
- `backend/repositories/__init__.py`
- `backend/repositories/user_repository.py`
- `backend/repositories/project_repository.py`
- `backend/repositories/deployment_repository.py`
- `backend/repositories/audit_repository.py`
- `backend/repositories/repository_repository.py`
- `backend/repositories/workflow_repository.py`
- `backend/repositories/simulation_repository.py`
- `backend/repositories/email_otp_repository.py`
- `backend/repositories/github_connection_repository.py`

### Phase 4: Refactor Routes & Services (3-4 days)

**Tasks:**
- [ ] Update all route handlers to use repositories
- [ ] Replace `db.session.get(Model, id)` calls
- [ ] Replace `Model.query.filter_by(...)` calls
- [ ] Replace `db.session.add()` / `db.session.commit()` patterns
- [ ] Handle ObjectId ↔ string conversions
- [ ] Update serialization (use document `.to_mongo().to_dict()`)

**Files to modify:**
- `backend/routes/auth.py`
- `backend/routes/projects.py`
- `backend/routes/github.py`
- `backend/routes/deploy.py`
- `backend/routes/pipeline.py`
- `backend/routes/simulations.py`
- `backend/routes/workflow.py`
- `backend/routes/admin.py`
- `backend/routes/analytics.py`
- `backend/services/analyze_service.py`
- `backend/services/deployment_service.py`
- `backend/services/simulation_service.py`
- `backend/services/audit_service.py`

### Phase 5: Migration Script (1-2 days)

**Tasks:**
- [ ] Create `scripts/migrate_sql_to_mongo.py`
- [ ] Read all SQLAlchemy models
- [ ] Transform and insert into MongoDB
- [ ] Handle data type conversions
- [ ] Handle foreign key references → ObjectId references
- [ ] Create indexes after migration
- [ ] Verify row counts match
- [ ] Add rollback script (`migrate_mongo_to_sql.py`)

**Files to create:**
- `scripts/migrate_sql_to_mongo.py`
- `scripts/migrate_mongo_to_sql.py` (rollback)

### Phase 6: Testing & Validation (2-3 days)

**Tasks:**
- [ ] Update test fixtures to use `mongomock`
- [ ] Update test assertions for ObjectId
- [ ] Run full test suite → 54/54 passing
- [ ] Add integration tests against real Atlas cluster
- [ ] Performance benchmarks (query latency, throughput)
- [ ] Security audit (connection encryption, IP whitelist)

### Phase 7: Production Deployment (1 day)

**Tasks:**
- [ ] Configure Atlas cluster for production (M10+ tier)
- [ ] Set up VPC peering or Private Link
- [ ] Configure automated backups
- [ ] Set up monitoring & alerts
- [ ] Update CI/CD pipeline to deploy with MongoDB env vars
- [ ] Run migration script on production data
- [ ] Verify no data loss
- [ ] Switch DNS/traffic to new deployment

---

## 6. Key Technical Decisions

### 6.1 ObjectId Handling

**Decision:** Use `bson.ObjectId` as document IDs. Convert to string at API boundary.

```python
# In models
from bson import ObjectId
from mongoengine import Document, fields

class User(Document):
    meta = {'collection': 'users'}
    # MongoEngine auto-uses ObjectId for `id` field

# In routes - convert ObjectId to string
user_id = str(user.id)  # ObjectId("...") → "..."

# In API responses
return jsonify({"user_id": str(user.id)})
```

### 6.2 Transaction Support

**Decision:** Use MongoDB transactions for multi-document operations.

```python
from mongoengine import connection
from pymongo import MongoClient

# Atlas M10+ supports transactions
with connection.get_connection().start_session() as session:
    with session.start_transaction():
        user.save()
        profile.save()
        audit_log.save()
```

**Note:** Free M0 cluster does NOT support multi-document transactions. Use atomic single-document operations where possible, or upgrade to M10 for production.

### 6.3 Password Hashing

**Decision:** Keep argon2 hashing. Store hash as string in MongoDB.

```python
from passlib.hash import argon2

# Hashing
password_hash = argon2.hash(password)

# Verification
is_valid = argon2.verify(password, user.password_hash)
```

### 6.4 JWT Token Identity

**Decision:** Store user ID as string (ObjectId hex) in JWT.

```python
from bson import ObjectId

# In login route
token = create_access_token(identity=str(user.id))
# JWT payload: {"sub": "507f1f77bcf86cd799439011"}

# In protected route
user_id_str = get_jwt_identity()  # "507f1f77bcf86cd799439011"
user = User.objects.get(id=user_id_str)
```

### 6.5 CSRF Token Storage

**Decision:** Keep CSRF tokens in Flask-JWT-Extended cookies (no DB storage needed).

### 6.6 Audit Log Performance

**Decision:** Use capped collection for audit logs to prevent unbounded growth.

```python
class AuditLog(Document):
    meta = {
        'collection': 'audit_logs',
        'indexes': [
            {'fields': ['user_id', '-created_at']},
            {'fields': ['action', '-created_at']},
            {'fields': ['-created_at']},
        ]
    }
```

### 6.7 EmailOTP Expiration

**Decision:** Use MongoDB TTL index for automatic cleanup.

```python
class EmailOTP(Document):
    meta = {
        'indexes': [
            {'fields': ['expires_at'], 'expireAfterSeconds': 0},  # TTL
        ]
    }
```

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Data loss during migration** | HIGH | Full backup before migration, test migration on staging, verify row counts |
| **ObjectId vs Integer ID mismatch** | MEDIUM | Consistent use of string IDs in API; document conversion in `to_dict()` |
| **MongoDB transactions not available on M0** | MEDIUM | Use single-document atomic operations; upgrade to M10 for prod |
| **Query pattern differences** | MEDIUM | Audit all SQL queries first; design MongoDB schema to match access patterns |
| **Test suite breakage** | HIGH | Use `mongomock` for unit tests; maintain 54/54 test pass rate |
| **Performance regression** | MEDIUM | Add appropriate indexes; benchmark before/after |
| **Connection string leakage** | HIGH | Store in env vars, never commit, rotate immediately if exposed |
| **IP whitelist misconfiguration** | MEDIUM | Use 0.0.0.0/0 only in dev; restrict to specific IPs in prod |

---

## 8. Testing Strategy

### 8.1 Unit Tests
- Use `mongomock` to mock MongoDB in-memory
- All 54 existing tests must pass
- New tests for repository layer

### 8.2 Integration Tests
- Spin up real MongoDB container (Docker) for CI
- Test against Atlas M0 cluster for staging

### 8.3 Data Migration Tests
- Round-trip test: SQL → MongoDB → verify all fields
- Count test: source row count == destination doc count
- Referential integrity test: all FK references valid

---

## 9. Cost Estimate (MongoDB Atlas)

| Tier | RAM | Storage | Price/mo | Use Case |
|------|-----|---------|----------|----------|
| **M0** (Free) | Shared | 512 MB | $0 | Dev/staging only |
| **M10** | 2 GB | 10 GB | ~$57 | Production low-traffic |
| **M20** | 4 GB | 20 GB | ~$120 | Production medium |
| **M30** | 8 GB | 40 GB | ~$240 | Production high-traffic |

**Recommendation:** Start with M0 for development, upgrade to M10 for production.

---

## 10. Rollback Plan

If migration fails or production issues arise:

1. **Keep SQL database running** during migration (dual-write)
2. **Revert code** to use SQLAlchemy (git revert)
3. **Switch connection string** back to SQL
4. **Data sync:** Any writes during dual-write are lost (acceptable if window is short)

---

## 11. Success Criteria

- [ ] All 54 backend tests pass against MongoDB
- [ ] All routes work with MongoDB backend
- [ ] Data migration script runs without errors
- [ ] Performance benchmarks show no regression
- [ ] Atlas cluster is configured with encryption at rest & in transit
- [ ] Automated backups are enabled
- [ ] Monitoring & alerts are configured
- [ ] Production deployment is successful with zero data loss

---

## 12. Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Setup | 1 day | Atlas account |
| Phase 2: Models | 2 days | Phase 1 |
| Phase 3: Repositories | 2 days | Phase 2 |
| Phase 4: Refactor | 3-4 days | Phase 3 |
| Phase 5: Migration | 1-2 days | Phase 4 |
| Phase 6: Testing | 2-3 days | Phase 5 |
| Phase 7: Production | 1 day | Phase 6 |
| **Total** | **12-15 days** | |

---

## 13. References

- [MongoDB Atlas Documentation](https://docs.atlas.mongodb.com/)
- [MongoEngine Documentation](http://mongoengine.org/)
- [Flask-MongoEngine](https://flask-mongoengine.readthedocs.io/)
- [PyMongo Documentation](https://pymongo.readthedocs.io/)
- [MongoDB Best Practices](https://docs.mongodb.com/manual/administration/production-notes/)

---

**End of Plan**
