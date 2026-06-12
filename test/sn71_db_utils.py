import requests
import psycopg
import json
from typing import List, Dict, Any
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

# Global connection pool for performance
DB_POOL = ConnectionPool(
    "dbname=mydb user=myuser password=wonvhse1923741indiw83hfbixe92fnsbex9 host=95.217.116.91 port=5432",
    min_size=1,
    max_size=20,
    timeout=30,
    max_lifetime=3600,  # Recycle connections after 1 hour
    max_idle=600,        # Close idle connections after 10 minutes
    reconnect_timeout=5, # Retry failed connections for 5 seconds
    check=ConnectionPool.check_connection  # Check connection health before use
)

def sanitize_null_chars(value: Any) -> Any:
    """
    Remove NUL characters recursively so PostgreSQL text/jsonb writes won't fail.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: sanitize_null_chars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_null_chars(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_null_chars(item) for item in value)
    return value

def split_full_name(full_name: str):
    parts = full_name.strip().split()
    if len(parts) != 2:
        return None, None  # or raise an error if you’re feeling spicy
    first_name, last_name = parts
    return first_name, last_name

def is_exist_person_in_db(full_name, companyDomain):
    first_name, last_name = split_full_name(full_name)
    if not first_name or not last_name:
        print("❌ ❌ ❌ ❌ ❌ Invalid full name format")
        return True
    
    sql_sn71_person = """
    SELECT id
    FROM sn71_person
    WHERE
        first_name = %s
        AND last_name = %s
        AND c_website = %s
    LIMIT 1
    """
    
    with DB_POOL.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql_sn71_person, (first_name, last_name, companyDomain))
            persons = cur.fetchall()
    print(f"🔍 🔍 🔍 🔍 🔍  Checking existence for {full_name} at {companyDomain}: {'FOUND' if persons else 'NOT FOUND'}")
    return len(persons) > 0

def reset_seen_for_uncompleted_persons(in_progress_person_ids):
    """
    Reset seen=0 for persons that were marked but not completed.
    Called on Ctrl+C or graceful exit.
    """
    if not in_progress_person_ids:
        return
    
    print(f"\n\n{'='*100}")
    print(f"🔄 Resetting 'seen' flag for {len(in_progress_person_ids)} uncompleted persons...")
    
    with DB_POOL.connection() as conn:
        try:
            person_ids_list = list(in_progress_person_ids)
            
            sql = """
            UPDATE sn71_person
            SET seen = 0
            WHERE id = ANY(%s)
            """
            
            with conn.cursor() as cur:
                cur.execute(sql, (person_ids_list,))
                conn.commit()
            
            print(f"✅ Reset complete: {len(person_ids_list)} persons can be reprocessed")
        except Exception as e:
            print(f"❌ Error resetting seen flag: {e}")

def reset_flag3_for_uncompleted_companies(in_progress_company_websites):
    """
    Reset flag3=NULL for companies that were marked but not completed.
    Called on Ctrl+C or graceful exit during company extraction workflow.
    
    Args:
        in_progress_company_websites: Set of company websites currently being processed
    """
    if not in_progress_company_websites:
        return
    
    print(f"\n\n{'='*100}")
    print(f"🔄 Resetting 'flag3' for {len(in_progress_company_websites)} uncompleted companies...")
    
    with DB_POOL.connection() as conn:
        try:
            company_websites_list = list(in_progress_company_websites)
            
            sql = """
            UPDATE sn71_company
            SET flag3 = NULL
            WHERE website = ANY(%s) AND flag3 = '1' AND company_check IS NULL
            """
            
            with conn.cursor() as cur:
                cur.execute(sql, (company_websites_list,))
                conn.commit()
            
            print(f"✅ Reset complete: {len(company_websites_list)} companies can be reprocessed")
        except Exception as e:
            print(f"❌ Error resetting flag3: {e}")
    
    print("="*100)
    
def fetch_emails_from_db(limit: int = 100) -> List[Dict]:
    """
    Fetch emails from database that need verification.
    
    Args:
        limit: Maximum number of emails to fetch
    
    Returns:
        List of dict rows with email, id, etc.
    """
    print(f"📊 Fetching up to {limit} emails from database...")
    
    sql = """
    SELECT *
    FROM sn71_person
    WHERE
        seen IS NULL
        AND lead_check IS NULL
        AND email_check = 0
    LIMIT %s
    """
    
    with DB_POOL.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()
    
    print(f"   ✅ Fetched {len(rows)} emails from database")
    return rows

def update_email_check_status(email: str, status: int):
    """
    Update email_check status in database.
    
    Args:
        email: Email address to update
        status: 1 for passed, 0 for failed
    """
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE sn71_person
                SET email_check = %s
                WHERE email = %s
                """,
                (int(status), email)
            )
            conn.commit()
            
def update_batch_results(results: Dict[str, dict]):
    """
    Update database with batch verification results.
    
    Args:
        results: Dict mapping email -> result dict
    """
    print(f"\n💾 Updating database with results...")
    
    passed_count = 0
    failed_count = 0
    retry_count = 0
    
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            for email, result in results.items():
                if result.get("passed"):
                    # Email validation passed
                    cur.execute(
                        """
                        UPDATE sn71_person
                        SET email_check = 1
                        WHERE email = %s
                        """,
                        (email,)
                    )
                    passed_count += 1
                elif result.get("needs_retry"):
                    # Email needs retry - don't update (leave as 0)
                    retry_count += 1
                else:
                    # Email validation failed
                    cur.execute(
                        """
                        UPDATE sn71_person
                        SET email_check = 0
                        WHERE email = %s
                        """,
                        (email,)
                    )
                    failed_count += 1
            
            conn.commit()
    
    print(f"   ✅ Updated database:")
    print(f"      - Passed: {passed_count}")
    print(f"      - Failed: {failed_count}")
    print(f"      - Needs retry: {retry_count}")

def sn71_update_person_contactinfo(person, ret = False, work_email = ""):
    
    c_name = person.get('company', '')
    c_website = person.get('companyDomain', '')
    email = work_email
    confidence = 90
    first_name, last_name = split_full_name(person.get('fullName', ''))
    if not first_name or not last_name:
        return
    # position = ''
    # position_raw = ''
    # seniority = ''
    # department = ''
    # linkedin = 'https://linkedin.com/in/' + person.get('liVanity', '')
    # twitter = ''
    # phone_number = ''
    # contactout_location = person.get('locality', '')
    # contactout_experience = person.get('experience', [])
    # contactout_currentcompanyexperience = person.get('currentCompanyExperience', '')
    # duplicate_check = 'f'
    sources_domain = 'contactout'
    # email_check = 1 if ret else 0
    
    # data = {
    #     "c_name": c_name,
    #     "c_website": c_website,
    #     "email": email,
    #     "confidence": confidence,
    #     "first_name": first_name,
    #     "last_name": last_name,
    #     "position": position,
    #     "position_raw": position_raw,
    #     "seniority": seniority,
    #     "department": department,
    #     "linkedin": linkedin,
    #     "twitter": twitter,
    #     "phone_number": phone_number,
    #     "email_duplicate_check": duplicate_check,
    #     'contactout_location': contactout_location,
    #     'contactout_experience': contactout_experience,
    #     'contactout_currentcompanyexperience': contactout_currentcompanyexperience,
    #     'sources_domain': sources_domain,
    # }
    
    # print ("---------------------------------")
    # print (contactout_experience)
    # print ("---------------------------------")
    
    sql = """
    INSERT INTO sn71_person (
        c_name, c_website, first_name, last_name, sources_domain, contactout_info
    )
    VALUES (
        %s, %s, %s, %s, %s, %s
    )
    """
    
    safe_person = sanitize_null_chars(person)
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (
                c_name,
                c_website,
                first_name,
                last_name,
                sources_domain,
                Json(safe_person),
            ))
            conn.commit()
    
    return True

def sn71_update_company_contactinfo(company_contactinfo, domain):
    
    sql = """
    UPDATE sn71_company
    SET
        contact_info = %s::jsonb
    WHERE
        website = %s;
    """
    
    safe_company_contactinfo = sanitize_null_chars(company_contactinfo)
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (json.dumps(safe_company_contactinfo), domain)
            )
        conn.commit()
    
    print (f"************** update {domain} ***************")
    
    return True

# def sn71_update_company_contactinfo(company_contactinfo, domain):
#     conn = psycopg.connect(
#         dbname="mydb",
#         user="myuser",
#         password="strongpassword",
#         host="95.217.116.91",
#         port=5432,
#         row_factory=psycopg.rows.dict_row,
#     )

#     sql = """
#     INSERT INTO sn71_company (
#         business,
#         website,
#         country,
#         source,
#         industry,
#         contact_info
#     )
#     VALUES (%s, %s, %s, %s, %s, %s)
#     ON CONFLICT (website)
#     DO UPDATE SET
#         contact_info = EXCLUDED.contact_info
#     RETURNING id;
#     """

#     with conn.cursor() as cur:
#         cur.execute(
#             sql,
#             (
#                 company_contactinfo["companyName"],
#                 domain,
#                 company_contactinfo["countryCode"],
#                 company_contactinfo["source"],
#                 company_contactinfo["industry"],
#                 Json(company_contactinfo),
#             ),
#         )
#         row = cur.fetchone()
#         conn.commit()

#     conn.close()
#     return row

def sn71_db_update_company_check(company_check, company_check_reason, domain):
    """
    Update company check status and flag3.
    
    Args:
        company_check: 1=success (set flag3='0' for completed), 0=failure (set flag3=NULL for retry)
    """
    # Set flag3 based on company_check: '0'=completed (success), NULL=available for retry (failure)
    flag3_value = '0' if company_check == 1 else None
    
    sql = """
    UPDATE sn71_company
    SET
        company_check = %s,
        company_check_reason = %s,
        flag3 = %s
    WHERE
        website = %s;
    """
    
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (company_check, company_check_reason, flag3_value, domain)
            )
        conn.commit()
    
    return True

def     sn71_db_search_company(website = "", contact=False, lock_for_processing=False):
    """
    Get company from database.
    
    Args:
        website: Specific website to search for
        contact: If True, search for companies ready for person extraction (uses flag1)
        lock_for_processing: If True, use SELECT FOR UPDATE SKIP LOCKED to prevent
                           race conditions in multi-process environments
                           - For contact=True: locks with flag1
                           - For contact=False: locks with flag3 (company extraction workflow)
    
    Returns:
        Company record dict or None
    """
    if not website:
        if contact:
            print("🧨🧨🧨🧨🧨 Searching for company ready for person extraction...")
            sql = """
                SELECT *
                FROM sn71_company
                WHERE
                    (contact_info ->> 'employeesCount')::int BETWEEN 0 AND 1000
                    AND flag1 IS NULL
                    AND company_check = 1
                    AND country = 'US'
                ORDER BY
                        CASE
                            WHEN source IN ('contactout-50') THEN 0
                            ELSE 1
                        END,
                    resp_score DESC NULLS LAST
                LIMIT 1
            """
            # sql = """
            #     SELECT *
            #     FROM sn71_company
            #     WHERE
            #         flag1 IS NULL
            #         AND company_check = 1
            #         AND country = 'US'
            #         AND hq_info IS NOT NULL
            #     ORDER BY resp_score DESC NULLS LAST
            #     LIMIT 1
            # """
            
            # Add row-level locking for multi-process safety
            if lock_for_processing:
                sql += " FOR UPDATE SKIP LOCKED"
            
            params = None
        else:
            current_value_count = 0
            # with DB_POOL.connection() as conn:
            #     with conn.cursor(row_factory=dict_row) as cur:
            #         cur.execute("""
            #         SELECT count(p.id) as count
            #             FROM sn71_person p
            #             INNER JOIN sn71_company c ON p.c_website = c.website
            #             WHERE p.email IS NULL
            #                 AND p.seen IS NULL
            #                 AND c.company_check = 1
            #         """)
            #         result = cur.fetchone()
            #         current_value_count = result['count'] if result else 0
            sql = ""
            # Company extraction workflow - use flag3 for locking
            current_value_count = 500
            # print("🎇🎇🎇🎇🎇 Common extraction...")
            # sql = """
            #     SELECT *
            #     FROM sn71_company
            #     WHERE
            #         m_description IS NULL
            #         AND company_check IS NULL
            #         AND contact_info IS NULL
            #         AND country = 'US'
            #         AND flag3 IS NULL
            #     ORDER BY
            #         resp_score DESC NULLS LAST
            #     LIMIT 1
            # """
            if current_value_count > 1000:
                print("💎💎💎💎💎 high extraction...")
                sql = """
                    SELECT *
                    FROM sn71_company
                    WHERE
                        m_description IS NULL
                        AND company_check IS NULL
                        AND contact_info IS NULL
                        AND country = 'US'
                        AND flag3 IS NULL
                        AND resp_score > 0
                    ORDER BY
                        CASE
                            WHEN source IN ('hunter.io-1-50-small', 'hunter.io-50-50', 'hunter.io-50', 'contactout-50') THEN 0
                            ELSE 1
                        END,
                        resp_score DESC NULLS LAST
                    LIMIT 1
                """
            else:
                print("🥦🥦🥦🥦🥦 low extraction...")
                sql = """
                    SELECT *
                    FROM sn71_company
                    WHERE
                        m_description IS NULL
                        AND company_check IS NULL
                        AND contact_info IS NULL
                        AND country = 'US'
                        AND flag3 IS NULL
                    ORDER BY
                        CASE
                            WHEN source IN ('hunter.io-50-200', 'hunter.io-50-500', 'hunter.io-50-1000', 'hunter.io-50-10000', 'hunter.io-50-10001+') THEN 0
                            ELSE 1
                        END,
                        resp_score DESC NULLS LAST
                    LIMIT 1
                """
            
            # print("🥩🥩🥩🥩🥩 restore extraction...")
            # sql = """
            #     SELECT *
            #     FROM sn71_company
            #     WHERE
            #         m_description IS NULL
            #         AND company_check = 0
            #         AND contact_info IS NULL
            #         AND country = 'US'
            #         AND flag3 IS NULL
            #         AND company_check_reason like 'vali_check_company_base failed'
			# 	ORDER BY
            #         resp_score DESC NULLS LAST
            #     LIMIT 1
            # """
            
            # Add row-level locking for multi-process safety
            if lock_for_processing:
                sql += " FOR UPDATE SKIP LOCKED"
            
            params = None
    else:
        sql = """
        SELECT *
        FROM sn71_company
        WHERE
            website = %s
        LIMIT 1
        """
        params = (website,)
    
    with DB_POOL.connection() as conn:
        with conn.transaction():
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                rows = cur.fetchone()
                
                # If locked for processing, immediately mark as in-progress
                if lock_for_processing and rows:
                    if contact:
                        # Person extraction workflow - use flag1
                        update_sql = """
                        UPDATE sn71_company
                        SET flag1 = -1
                        WHERE website = %s AND flag1 IS NULL
                        """
                        cur.execute(update_sql, (rows['website'],))
                    elif not website:
                        # Company extraction workflow - use flag3
                        update_sql = """
                        UPDATE sn71_company
                        SET flag3 = '1'
                        WHERE website = %s AND flag3 IS NULL
                        """
                        cur.execute(update_sql, (rows['website'],))
                        print(f"🔒 Locked company for extraction: {rows['website']}")
    
    if rows:
        print(f"@@@@@@@@ ID: {rows['id']}, Website: {rows['website']} @@@@@@@@@")
    else:
        print("⚠️  No company found matching the criteria")
    
    return rows

def sn71_db_session_get_proxy(process=""):
    if process:
        sql = """
        SELECT *
        FROM sn71_session
        WHERE process = %s
        """
        params = (process,)
    else:
        sql = """
        SELECT *
        FROM sn71_session
        """
        params = None

    with DB_POOL.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)

            rows = cur.fetchall()

    return rows

def sn71_db_session_save_token(xsrf_token, xsrf_expires, contactout_session, contactout_expires, co_premium_user, proxy_username):
    
    sql = """
    UPDATE sn71_session
    SET
        "XSRF_TOKEN" = %s,
        "expires" = %s,
        "contactout_seesion" = %s,
        "co_premium_user" = %s
    WHERE username = %s
    """

    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    xsrf_token,
                    xsrf_expires,
                    contactout_session,
                    co_premium_user,
                    proxy_username,
                )
            )
            conn.commit()
    
    return True


# ==============================================================================
# DATABASE FUNCTIONS
# ==============================================================================

def check_company_exists(website):
    """
    Check if company already exists in database by website.
    
    Args:
        website: Company domain/website to check
    
    Returns:
        bool: True if exists, False otherwise
    """
    check_sql = "SELECT id FROM sn71_company WHERE website = %s"
    
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(check_sql, (website,))
            existing = cur.fetchone()
            return existing is not None

def sn71_db_company_insert_company_with_contactinfo(company_contactinfo, domain):

    # Check if website already exists
    check_sql = "SELECT id FROM sn71_company WHERE website = %s"
    
    safe_company_contactinfo = sanitize_null_chars(company_contactinfo)
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            # Insert new company
            sql = """
            INSERT INTO sn71_company (business, website, country, source, industry, resp_score, contact_info)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (website) DO NOTHING;
            """
            
            cur.execute(sql, (
                safe_company_contactinfo["companyName"], 
                safe_company_contactinfo["domain"], 
                safe_company_contactinfo["countryCode"], 
                "contactout-50", 
                safe_company_contactinfo["industry"], 
                36,
                Json(safe_company_contactinfo)
            ))
            
            # Check if row was actually inserted (rowcount=1) or conflict occurred (rowcount=0)
            inserted = cur.rowcount > 0
            conn.commit()
            
            if inserted:
                print("=🎈 🎈 🎈====== new insert =========")
            else:
                print("=🍄 🍄 🍄====== company already exists (conflict) =========")
            
            return inserted

def sn71_db_company_contactout_person_extract(website, success):
    
    sql = """
    UPDATE sn71_company
    SET
        flag1 = %s
    WHERE
        website = %s;
    """
    print (f"************** update contactout person extract {website} to {success} ***************")
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (success, website)
            )
        conn.commit()
    
    return True

def sn71_db_person_get_contactperson():
    """
    Get top 10 persons without email, sorted by company reputation score.
    
    Finds person rows from sn71_person where email is NULL and seen IS NULL,
    joins with sn71_company on company website/name,
    and returns top 10 sorted by company resp_score (descending).
    
    After fetching, marks those 10 persons as seen=1 to prevent duplicate processing
    in multi-process environments.
    
    Returns:
        List[Dict]: Top 10 person records with company info, or empty list
    """
    # Join sn71_person with sn71_company on website
    # Filter for persons without email and not yet seen
    # Sort by company reputation score (descending)
    # Limit to top 30
    sql = """
        SELECT 
            p.id, p.c_name, p.c_website, p.first_name, p.last_name, p.contactout_info,
            c.resp_score, c.company_check,
            c.business as company_business,
            c.industry as company_industry
        FROM sn71_person p
        INNER JOIN sn71_company c ON p.c_website = c.website
        WHERE p.email IS NULL
            AND p.seen IS NULL
        ORDER BY 
            CASE
                WHEN c.source IN ('hunter.io-1-50-small', 'hunter.io-50-50', 'hunter.io-50', 'contactout-50') THEN 0
                ELSE 1
            END,
            c.resp_score DESC NULLS LAST
        LIMIT 950
        FOR UPDATE SKIP LOCKED
    """
    
    with DB_POOL.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            persons = cur.fetchall()
        
        # Mark these persons as seen to prevent duplicate processing
        if persons:
            person_ids = [p['id'] for p in persons]
            
            update_sql = """
            UPDATE sn71_person
            SET seen = 1
            WHERE id = ANY(%s)
            """
            
            with conn.cursor() as cur:
                cur.execute(update_sql, (person_ids,))
                conn.commit()
            
            print(f"📊 Found {len(persons)} persons without email (sorted by company reputation)")
            print(f"✅ Marked {len(person_ids)} persons as seen=1")
        else:
            print(f"📊 Found 0 persons without email")
    
    return persons


def sn71_db_person_update_email(person_id, email):
    """
    Update email for a person in sn71_person table.
    
    Args:
        person_id: ID of the person to update
        email: Validated email address
    
    Returns:
        bool: True if successful, False if email already exists
    """
    # First check if email already exists
    check_sql = "SELECT id FROM sn71_person WHERE email = %s"
    
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(check_sql, (email,))
            existing = cur.fetchone()
            
            if existing:
                print(f"      ⚠️  Email {email} already exists (person_id={existing[0]}), skipping update for person {person_id}")
                return False
            
            # Safe to update
            sql = """
            UPDATE sn71_person
            SET email = %s, email_check = 1
            WHERE id = %s
            """
            cur.execute(sql, (email, person_id))
            conn.commit()
    
    return True


def sn71_db_failed_person_update_email(person_id):
    """
    Update email for a person in sn71_person table.
    
    Args:
        person_id: ID of the person to update
        email: Validated email address
    
    Returns:
        bool: True if successful, False if email already exists
    """
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            # Safe to update
            sql = """
            UPDATE sn71_person
            SET sources_uri = 'pending'
            WHERE id = %s
            """
            cur.execute(sql, (person_id,))
            conn.commit()
    
    return True


def sn71_db_person_insert_additional_email(person_record, email):
    """
    Insert a new person record with additional valid email.
    Duplicates the original person record but with a new valid email.
    
    Args:
        person_record: Original person dict from database
        email: Additional validated email address
    
    Returns:
        int: New person ID, or None if insert failed (e.g., duplicate email)
    """
    # First check if email already exists
    check_sql = "SELECT id FROM sn71_person WHERE email = %s"
    
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(check_sql, (email,))
            existing = cur.fetchone()
            
            if existing:
                print(f"      ⚠️  Email {email} already exists (person_id={existing[0]}), skipping insert")
                return None
            
            # Safe to insert
            sql = """
            INSERT INTO sn71_person (
                c_name, c_website, email, confidence, sources_domain,
                first_name, last_name, position, position_raw,
                seniority, department, linkedin, contactout_info, email_check
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            RETURNING id
            """
            
            cur.execute(sql, (
                person_record.get('c_name'),
                person_record.get('c_website'),
                email,
                person_record.get('confidence', 90),
                person_record.get('sources_domain', 'contactout'),
                person_record.get('first_name'),
                person_record.get('last_name'),
                person_record.get('position'),
                person_record.get('position_raw'),
                person_record.get('seniority'),
                person_record.get('department'),
                person_record.get('linkedin'),
                Json(person_record.get('contactout_info')) if person_record.get('contactout_info') else None
            ))
            result = cur.fetchone()
            conn.commit()
    
    return result[0] if result else None


# ==============================================================================
# NON-US DATABASE FUNCTIONS (sn71_company_nonus / sn71_person_nonus)
# ==============================================================================

def reset_seen_for_uncompleted_nonus_persons(in_progress_person_ids):
    """
    Reset seen=0 for non-US persons that were marked but not completed.
    Called on Ctrl+C or graceful exit.
    """
    if not in_progress_person_ids:
        return

    print(f"\n\n{'='*100}")
    print(f"🔄 Resetting 'seen' flag for {len(in_progress_person_ids)} uncompleted non-US persons...")

    with DB_POOL.connection() as conn:
        try:
            person_ids_list = list(in_progress_person_ids)

            sql = """
            UPDATE sn71_person_nonus
            SET seen = 0
            WHERE id = ANY(%s)
            """

            with conn.cursor() as cur:
                cur.execute(sql, (person_ids_list,))
                conn.commit()

            print(f"✅ Reset complete: {len(person_ids_list)} non-US persons can be reprocessed")
        except Exception as e:
            print(f"❌ Error resetting seen flag (nonus): {e}")


def sn71_db_person_nonus_get_contactperson():
    """
    Get top persons without email from sn71_person_nonus, sorted by company reputation score.

    Finds person rows where email IS NULL and seen IS NULL,
    joins with sn71_company_nonus on company website,
    and returns up to 950 rows sorted by company resp_score (descending).

    After fetching, marks those persons as seen=1 to prevent duplicate processing
    in multi-process environments.

    Returns:
        List[Dict]: Person records with company info, or empty list
    """
    sql = """
        SELECT
            p.id, p.c_name, p.c_website, p.first_name, p.last_name, p.contactout_info,
            NULL::real as resp_score, c.company_check,
            c.business as company_business,
            c.llm_industry as company_industry
        FROM sn71_person_nonus p
        INNER JOIN sn71_company_nonus c ON p.c_website = c.domain
        WHERE p.email IS NULL
            AND p.seen IS NULL
        ORDER BY
            c.fetch_time DESC NULLS LAST
        LIMIT 400
        FOR UPDATE SKIP LOCKED
    """

    with DB_POOL.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            persons = cur.fetchall()

        if persons:
            person_ids = [p['id'] for p in persons]

            update_sql = """
            UPDATE sn71_person_nonus
            SET seen = 1
            WHERE id = ANY(%s)
            """

            with conn.cursor() as cur:
                cur.execute(update_sql, (person_ids,))
                conn.commit()

            print(f"📊 Found {len(persons)} non-US persons without email (sorted by company reputation)")
            print(f"✅ Marked {len(person_ids)} non-US persons as seen=1")
        else:
            print(f"📊 Found 0 non-US persons without email")

    return persons


def sn71_db_person_nonus_update_email(person_id, email):
    """
    Update email for a person in sn71_person_nonus table.

    Args:
        person_id: ID of the person to update
        email: Validated email address

    Returns:
        bool: True if successful, False if email already exists
    """
    check_sql = "SELECT id FROM sn71_person_nonus WHERE email = %s"

    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(check_sql, (email,))
            existing = cur.fetchone()

            if existing:
                print(f"      ⚠️  Email {email} already exists (person_id={existing[0]}), skipping update for non-US person {person_id}")
                return False

            sql = """
            UPDATE sn71_person_nonus
            SET email = %s, email_check = 1
            WHERE id = %s
            """
            cur.execute(sql, (email, person_id))
            conn.commit()

    return True


def sn71_db_failed_person_nonus_update_email(person_id):
    """
    Mark a non-US person as having no valid email found (sources_uri = 'pending').

    Args:
        person_id: ID of the person to update

    Returns:
        bool: True if successful
    """
    with DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            sql = """
            UPDATE sn71_person_nonus
            SET sources_uri = 'pending'
            WHERE id = %s
            """
            cur.execute(sql, (person_id,))
            conn.commit()

    return True


if __name__ == "__main__":
    print (f"{__name__} is called")