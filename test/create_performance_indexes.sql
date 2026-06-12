-- Performance Indexes for sn71_person and sn71_company tables
-- Run these to significantly improve query performance
-- Using CONCURRENTLY to avoid locking tables during index creation

-- ============================================================================
-- sn71_person table indexes
-- ============================================================================

-- Index for email lookups (duplicate checking)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_person_email 
ON sn71_person(email);

-- Composite index for person existence checks
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_person_name_website 
ON sn71_person(first_name, last_name, c_website);

-- Partial index for unseen persons (WHERE seen IS NULL)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_person_seen_null 
ON sn71_person(seen) 
WHERE seen IS NULL;

-- Index for email IS NULL queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_person_email_null 
ON sn71_person(email) 
WHERE email IS NULL;

-- Composite index for the main query in sn71_db_person_get_contactperson
-- Covers: email IS NULL, seen IS NULL, JOIN on c_website
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_person_email_seen_website 
ON sn71_person(c_website, email, seen);


-- ============================================================================
-- sn71_company table indexes
-- ============================================================================

-- Primary lookup index for website
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_website 
ON sn71_company(website);

-- Index for reputation score sorting (DESC NULLS LAST)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_resp_score 
ON sn71_company(resp_score DESC NULLS LAST);

-- Index for company_check status
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_check 
ON sn71_company(company_check);

-- Composite index for filtering in sn71_db_search_company
-- NOTE: Removed contact_info because JSONB is too large for composite index
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_filters 
ON sn71_company(m_description, company_check);

-- Index for flag1 (used in contactout person extraction)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_flag1 
ON sn71_company(flag1);

-- Composite index for the main company search query
-- Covers: m_description IS NULL, company_check, resp_score sorting
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_search 
ON sn71_company(m_description, company_check, resp_score DESC NULLS LAST);

-- JSONB index for employeesCount lookups in contact_info
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_contact_employees 
ON sn71_company(((contact_info->>'employeesCount')::int));


-- ============================================================================
-- sn71_session table indexes (if needed)
-- ============================================================================

-- Index for process-based proxy lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_process 
ON sn71_session(process);

-- Index for username lookups
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_session_username 
ON sn71_session(username);


-- ============================================================================
-- Verify indexes were created
-- ============================================================================

-- Run this query to check which indexes exist:
-- SELECT 
--     schemaname, 
--     tablename, 
--     indexname, 
--     indexdef 
-- FROM pg_indexes 
-- WHERE tablename IN ('sn71_person', 'sn71_company', 'sn71_session')
-- ORDER BY tablename, indexname;


-- ============================================================================
-- Analyze tables to update statistics (important for query planner)
-- ============================================================================

ANALYZE sn71_person;
ANALYZE sn71_company;
ANALYZE sn71_session;


-- ============================================================================
-- NOTES:
-- ============================================================================
-- 1. CONCURRENTLY means indexes are built without blocking table access
-- 2. Run ANALYZE after creating indexes to update query planner statistics
-- 3. Monitor index usage with: 
--    SELECT * FROM pg_stat_user_indexes WHERE relname IN ('sn71_person', 'sn71_company');
-- 4. If an index creation fails, drop it and retry:
--    DROP INDEX CONCURRENTLY IF EXISTS idx_name;
