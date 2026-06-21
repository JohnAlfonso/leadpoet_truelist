import os
import random
import sys
import json
import asyncio
import argparse
import time
import signal

# Add parent directory to path FIRST (before Leadpoet imports)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Leadpoet.utils.cloud_db import check_email_duplicate

from sn71_db_utils import (
    sn71_db_search_company, 
    sn71_db_session_get_proxy, 
    sn71_db_update_company_check, 
    sn71_db_company_contactout_person_extract,
    sn71_db_person_get_contactperson,
    sn71_db_person_update_email,
    sn71_db_failed_person_update_email,
    sn71_db_person_insert_additional_email,
    reset_seen_for_uncompleted_persons,
    reset_flag3_for_uncompleted_companies,
    check_company_exists,
    # Non-US equivalents
    sn71_db_person_nonus_get_contactperson,
    sn71_db_person_nonus_update_email,
    sn71_db_failed_person_nonus_update_email,
    reset_seen_for_uncompleted_nonus_persons,
)
from sn71_contactout_search import (
    extract_company_from_contactout, 
    extract_person_and_process_with_company,
    search_companies_from_contactout,
    process_search_company_from_contactout,
    call_contactout_template
)
from sn71_validation import vali_check_company_base
from email_generation import (
    smart_email_generator,
    catchall_probe,
    detect_format,
    email_for_format,
    email_rank,
)
from email_format_registry import get_format, learn_format

# Add parent directory to path for validator_models (already added above for Leadpoet)
from validator_models.automated_checks import (
    submit_truelist_batch,
    poll_truelist_batch,
    check_name_email_match,
    TRUELIST_API_KEY
)

# Global tracking for graceful shutdown
in_progress_person_ids = set()  # Track person IDs currently being processed (US)
in_progress_nonus_person_ids = set()  # Track person IDs currently being processed (non-US)
in_progress_company_websites = set()  # Track company websites currently being extracted
shutdown_requested = False  # Flag for graceful shutdown

def signal_handler(signum, frame):
    """Handle Ctrl+C (SIGINT) gracefully for both company and person workflows"""
    global shutdown_requested
    shutdown_requested = True
    print(f"\n\n⚠️  Interrupt received (Ctrl+C). Finishing current batch and cleaning up...")
    print(f"⚠️  Press Ctrl+C again to force exit (not recommended)")
    
    # Change handler to force exit on second Ctrl+C
    signal.signal(signal.SIGINT, lambda s, f: sys.exit(1))

async def main_company(process):
    global in_progress_company_websites, shutdown_requested
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 Starting company extraction workflow...")
    print("   Press Ctrl+C to stop gracefully\n")
    
    try:
        while True:
            
            # Check for shutdown signal
            if shutdown_requested:
                print("🛑 Shutdown requested, exiting main loop...")
                break
            
            print ("=" * 100)
            
            # step1: get the company from db with rep_score high (WITH LOCKING)
            company = sn71_db_search_company(lock_for_processing=True)
            if not company:
                # No companies available (all locked by other processes or completed)
                print("⏳ No available companies. Waiting 10 seconds...")
                call_contactout_template(process)
                time.sleep(30)
                continue
            
            # Track this company as in-progress
            website = company['website']
            in_progress_company_websites.add(website)
            
            # step2: company check
            # ret, reason = await vali_check_company_base(website)
            # if ret:
            #     print (f"✅ {website} - company base check success")
            # else:
            #     sn71_db_update_company_check(company_check=0, company_check_reason="vali_check_company_base failed", domain=website)
            #     print (f"❌ {website} - company base check failed - reason: {reason}")
                
            #     # Remove from in-progress (failure already set flag3=NULL by sn71_db_update_company_check)
            #     in_progress_company_websites.discard(website)
            #     continue
            
            # step3: find company info from contactout with step1 result
            companyName = company['business']
            companyDomain = company['website']
            ret = extract_company_from_contactout(companyName=companyName, companyDomain=companyDomain, process=process)
            if ret:
                print (f"✅ {website} - company extract success")
                # Success is handled by extract_company_from_contactout calling sn71_db_update_company_check
            else:
                print (f"❌ {website} - company extract failed")
                # Failure should also be handled there, but ensure it's removed from tracking
            
            # Remove from in-progress set after completion (success or failure)
            in_progress_company_websites.discard(website)
            time.sleep(random.uniform(5.0, 10.0))
    except KeyboardInterrupt:
        print(f"\n⚠️  Keyboard interrupt detected during company extraction...")
    except Exception as e:
        print(f"\n❌ Unexpected error in company workflow: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always cleanup on exit
        print(f"\n🛑 Shutting down company extraction gracefully...")
        
        # Reset flag3 for uncompleted companies
        reset_flag3_for_uncompleted_companies(in_progress_company_websites)
        
        print(f"✅ Company extraction shutdown complete!")

async def main_person(process):
    global shutdown_requested
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    print("🚀 Starting person extraction workflow...")
    print("   Press Ctrl+C to stop gracefully after current company completes\n")
    
    try:
        while True:
            # Check for shutdown signal
            if shutdown_requested:
                print("🛑 Shutdown requested, exiting person extraction loop...")
                break
            
            print ("=" * 100)
            
            # STEP1: get the company from db WITH LOCKING (prevents race conditions)
            # company = sn71_db_search_company(website='kitemedia.com')
            company = sn71_db_search_company(contact=True, lock_for_processing=True)
            if not company:
                # No companies available (all locked by other processes or completed)
                print("⏳ No available companies. Waiting 5 seconds...")
                call_contactout_template(process)
                time.sleep(30)
                continue
            
            print(f"🔒 Locked company for processing: {company['website']}")
            
            # check company info
            contact_info = company.get("contact_info", {})
            if not contact_info:
                sn71_db_company_contactout_person_extract(company['website'], 0)
                continue
            
            companyName = contact_info['companyName']
            companyIds = contact_info['companyId']
            print (companyName, companyIds)
            # exit()
            # STEP2: find person info from contactout with step1 result (companyName, companyDomain)
            ret = extract_person_and_process_with_company(company=companyName, companyIds=companyIds, process=process)
            if ret:
                print (f"✅ {company['website']} - company persons extract success")
            else:
                print (f"❌ {company['website']} - company persons extract failed")
            
            success = 1 if ret else 0
            sn71_db_company_contactout_person_extract(company['website'], success)
            time.sleep(random.uniform(5.0, 10.0))
    except KeyboardInterrupt:
        print(f"\n⚠️  Keyboard interrupt detected during person extraction...")
    except Exception as e:
        print(f"\n❌ Unexpected error in person workflow: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n🛑 Shutting down person extraction gracefully...")
        print(f"✅ Person extraction shutdown complete!")
    
    return ""

async def prepare_batch():
    """
    Phase 1: Generate emails and check duplicates.
    Returns: (persons, all_emails, email_to_person_map, gen_time, sentinels) or None
    """
    start_time = time.time()
    
    # 1. Get top 10 persons without email from database
    persons = sn71_db_person_get_contactperson()
    if not persons:
        print("⚠️  No persons found without email")
        return None
    
    print(f"\n📋 Processing {len(persons)} persons:")
    for i, p in enumerate(persons, 1):
        print(f"   {i}. {p.get('first_name')} {p.get('last_name')} @ {p.get('c_website')} (rep score: {p.get('resp_score')})")
    
    # 2. Generate possible emails for all persons
    print(f"\n📧 Generating email variations...")
    email_to_person_map = {}  # {email: person_record}
    all_emails = []
    
    for person in persons:
        first_name = person.get('first_name', '')
        last_name = person.get('last_name', '')
        company_domain = person.get('c_website', '')
        
        if not first_name or not last_name or not company_domain:
            print(f"   ⚠️  Skipping person {person.get('id')}: missing name or domain")
            continue
        
        full_name = f"{first_name} {last_name}"
        
        # Generate email variations
        work_emails = smart_email_generator(full_name, company_domain, max_results=30)
        print(f"   👤 {full_name} @ {company_domain}: {len(work_emails)} variations generated")
        
        # 3. Check for duplicates before adding to batch
        # Run duplicate checks in thread pool to avoid blocking event loop
        valid_emails = []
        # loop = asyncio.get_event_loop()
        
        for email in work_emails:
            # Run synchronous check_email_duplicate in thread pool
            # is_duplicate = await loop.run_in_executor(None, check_email_duplicate, email)
            # if is_duplicate:
            #     print(f"      ⚠️  Duplicate: {email}")
            #     continue
            valid_emails.append(email)
            email_to_person_map[email.lower()] = person
        
        all_emails.extend(valid_emails)
        print(f"      ✅ {len(valid_emails)} non-duplicate emails added to batch")
    
    if not all_emails:
        print("\n❌ No valid emails to verify (all duplicates or no emails generated)")
        return None

    # Catch-all detection: one sentinel (guaranteed-nonexistent) address per domain.
    # If TrueList passes the sentinel, that domain accepts everything and real
    # guesses there cannot be confirmed by SMTP.
    sentinels = {}  # {sentinel_email_lower: domain}
    for domain in {p.get('c_website', '') for p in email_to_person_map.values() if p.get('c_website')}:
        probe = catchall_probe(domain)
        sentinels[probe.lower()] = domain
        all_emails.append(probe)

    gen_time = time.time() - start_time
    print(f"\n📊 Total emails to verify: {len(all_emails)} ({len(sentinels)} catch-all probes)")
    print(f"   ⏱️  Generation time: {gen_time:.2f}s")

    return (persons, all_emails, email_to_person_map, gen_time, sentinels)


async def verify_batch(all_emails, email_to_person_map):
    """
    Phase 2: Submit to TrueList and poll for results.
    Returns: results dict or None if failed
    """
    print(f"\n{'='*100}")
    print("📤 Submitting batch to TrueList API...")
    
    try:
        batch_id = await submit_truelist_batch(all_emails)
        print(f"   ✅ Batch submitted: {batch_id}")
        
        # Poll for results
        results = await poll_truelist_batch(batch_id)
        print(f"   ✅ Batch completed: {len(results)} results received")
        return results
        
    except Exception as e:
        print(f"   ❌ Batch verification failed: {e}")
        return None


async def _apply_verification_results(persons, results, email_to_person_map, sentinels,
                                      update_email_fn, failed_email_fn):
    """Shared Phase-3 logic for US and non-US batches.

    - Detects catch-all domains from sentinel probes.
    - Picks the best confirmed address per person (learned format > name match > rank).
    - Learns each company's format from confirmed addresses for future batches.

    update_email_fn(person_id, email) and failed_email_fn(person_id) select the
    correct table (sn71_person vs sn71_person_nonus).
    """
    sentinels = sentinels or {}
    sentinel_set = set(sentinels.keys())

    # 1. Catch-all domains: sentinel address came back as deliverable.
    catchall_domains = set()
    for s_email, domain in sentinels.items():
        r = results.get(s_email) or results.get(s_email.lower())
        if r and r.get("passed"):
            catchall_domains.add((domain or "").lower())
    if catchall_domains:
        print(f"   🪤 Catch-all domains: {len(catchall_domains)}/{len(sentinels)} "
              f"→ {', '.join(sorted(catchall_domains))}")

    batch_person_ids = {p['id'] for p in persons}
    pid_to_person = {p['id']: p for p in persons}

    # 2. Group confirmed (passed) addresses per person, ignoring sentinels/strangers.
    passed_by_person = {}
    for email, result in results.items():
        el = email.lower()
        if el in sentinel_set or not result.get("passed"):
            continue
        person = email_to_person_map.get(el)
        if not person or person.get('id') not in batch_person_ids:
            continue
        passed_by_person.setdefault(person['id'], []).append(el)

    passed_count = 0
    failed_count = 0
    catchall_unconfirmed = 0
    learned_count = 0
    valid_email_total = 0

    for pid, person in pid_to_person.items():
        first = person.get('first_name', '') or ''
        last = person.get('last_name', '') or ''
        full_name = f"{first} {last}".strip()
        domain = (person.get('c_website') or '').lower()
        passed_emails = passed_by_person.get(pid, [])

        # --- Catch-all domain: SMTP can't confirm. Use a learned format if we have one. ---
        if domain in catchall_domains:
            fmt = get_format(domain)
            guess = email_for_format(full_name, domain, fmt) if fmt else None
            if guess:
                update_email_fn(pid, guess)
                passed_count += 1
                valid_email_total += 1
                print(f"   🪤 {full_name} @ {domain}: catch-all → learned '{fmt}' → {guess}")
            else:
                catchall_unconfirmed += 1
                failed_email_fn(pid)
            continue

        # --- Normal domain: nothing verified ---
        if not passed_emails:
            failed_count += 1
            failed_email_fn(pid)
            continue

        # --- Normal domain: choose the best confirmed address ---
        ranked = sorted(passed_emails, key=lambda e: email_rank(full_name, e))
        best = ranked[0]

        learned_fmt = get_format(domain)
        if learned_fmt:
            for cand in ranked:
                if detect_format(full_name, cand) == learned_fmt:
                    best = cand
                    break
        elif len(ranked) > 1:
            # Several mailboxes accepted; prefer the one that matches the name.
            for cand in ranked:
                try:
                    ok, _ = await check_name_email_match(
                        {"first": first, "last": last, "email": cand})
                except Exception:
                    ok = False
                if ok:
                    best = cand
                    break

        update_email_fn(pid, best)
        passed_count += 1
        valid_email_total += len(passed_emails)
        extra = f" [+{len(passed_emails) - 1} more accepted]" if len(passed_emails) > 1 else ""
        print(f"   ✅ {full_name} @ {domain}: {best} (PRIMARY){extra}")

        # Learn this company's format for future batches.
        fmt = detect_format(full_name, best)
        if fmt:
            learn_format(domain, fmt)
            learned_count += 1

    print(f"\n   📊 Persons in batch: {len(persons)}")
    print(f"   ✅ Confirmed: {passed_count}")
    print(f"   ❌ Failed (normal domain): {failed_count}")
    print(f"   🪤 Catch-all, unconfirmed: {catchall_unconfirmed}")
    print(f"   🧠 Company formats learned: {learned_count}")
    print(f"   📧 Total valid emails found: {valid_email_total}")
    return passed_count


async def update_database(persons, results, email_to_person_map, sentinels=None):
    """Phase 3 (US): update sn71_person with verification results."""
    print(f"\n{'='*100}")
    print("💾 Processing results and updating database...")
    await _apply_verification_results(
        persons, results, email_to_person_map, sentinels,
        sn71_db_person_update_email, sn71_db_failed_person_update_email)


async def main_e_check():
    """
    Pipelined email check workflow:
    - Batch N: Generate emails while Batch N-1 is being verified on TrueList
    - This overlaps 100s generation with 150s TrueList check
    - Reduces total time from 250s to ~150s per batch
    
    Supports graceful shutdown on Ctrl+C - resets 'seen' flag for uncompleted persons.
    """
    global in_progress_person_ids, shutdown_requested
    
    # Register Ctrl+C handler
    signal.signal(signal.SIGINT, signal_handler)
    
    batch_num = 0
    next_batch_task = None  # Task for preparing next batch
    
    try:
        while True:
            # Check for shutdown request
            if shutdown_requested:
                print(f"\n⚠️  Shutdown requested. Cancelling pending batch preparation...")
                if next_batch_task:
                    next_batch_task.cancel()
                    try:
                        await next_batch_task
                    except asyncio.CancelledError:
                        pass
                break
            
            # If we already started preparing next batch (during previous TrueList check), use it
            if next_batch_task:
                print(f"\n⏳ Waiting for batch preparation to complete...")
                batch_data = await next_batch_task
                next_batch_task = None
            else:
                # First batch - prepare it now
                batch_data = await prepare_batch()
            
            if not batch_data:
                print(f"\n⏳ No persons to process. Waiting 5 seconds before retry...")
                await asyncio.sleep(5)
                continue
            
            # Now we have batch data, increment counter
            batch_num += 1
            cycle_start = time.time()
            
            print("=" * 100)
            print(f"🔄 BATCH #{batch_num} - Starting email verification workflow...")
            
            persons, all_emails, email_to_person_map, gen_time, sentinels = batch_data

            # Track these person IDs as in-progress
            current_person_ids = {p['id'] for p in persons}
            in_progress_person_ids.update(current_person_ids)
            
            # Start preparing NEXT batch in parallel with TrueList verification
            print(f"\n{'='*100}")
            print(f"🚀 Starting NEXT batch preparation in parallel...")
            next_batch_task = asyncio.create_task(prepare_batch())
            
            # Meanwhile, verify CURRENT batch on TrueList
            verify_start = time.time()
            results = await verify_batch(all_emails, email_to_person_map)
            verify_time = time.time() - verify_start
            
            if not results:
                print(f"   ⚠️  Skipping database update due to verification failure")
                # Keep persons in in_progress_person_ids for cleanup
                continue
            
            # Update database with results
            await update_database(persons, results, email_to_person_map, sentinels)
            
            # Remove completed persons from tracking (successfully processed)
            in_progress_person_ids.difference_update(current_person_ids)
            
            # Timing summary
            cycle_time = time.time() - cycle_start
            print(f"\n{'='*100}")
            print(f"✅ BATCH #{batch_num} completed!")
            print(f"   ⏱️  Generation time: {gen_time:.2f}s")
            print(f"   ⏱️  Verification time: {verify_time:.2f}s")
            print(f"   ⏱️  Total cycle time: {cycle_time:.2f}s (with parallel preparation)")
            print("=" * 100)
    
    except KeyboardInterrupt:
        print(f"\n⚠️  Keyboard interrupt detected during processing...")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always cleanup on exit
        print(f"\n🛑 Shutting down gracefully...")
        
        # Cancel pending batch preparation
        if next_batch_task and not next_batch_task.done():
            print(f"   🔄 Cancelling pending batch preparation...")
            next_batch_task.cancel()
            try:
                await next_batch_task
            except asyncio.CancelledError:
                print(f"   ✅ Batch preparation cancelled")
        
        # Reset seen flag for uncompleted persons
        reset_seen_for_uncompleted_persons(in_progress_person_ids)
        
        print(f"✅ Shutdown complete. Goodbye!")
    
    return True



async def prepare_batch_nonus():
    """
    Phase 1 (non-US): Generate emails and check duplicates for non-US persons.
    Returns: (persons, all_emails, email_to_person_map, gen_time, sentinels) or None
    """
    start_time = time.time()

    # 1. Get top persons without email from sn71_person_nonus
    persons = sn71_db_person_nonus_get_contactperson()
    if not persons:
        print("⚠️  No non-US persons found without email")
        return None

    print(f"\n📋 Processing {len(persons)} non-US persons:")
    for i, p in enumerate(persons, 1):
        print(f"   {i}. {p.get('first_name')} {p.get('last_name')} @ {p.get('c_website')} (rep score: {p.get('resp_score')})")

    # 2. Generate possible emails for all persons
    print(f"\n📧 Generating email variations...")
    email_to_person_map = {}  # {email: person_record}
    all_emails = []

    for person in persons:
        first_name = person.get('first_name', '')
        last_name = person.get('last_name', '')
        company_domain = person.get('c_website', '')

        if not first_name or not last_name or not company_domain:
            print(f"   ⚠️  Skipping non-US person {person.get('id')}: missing name or domain")
            continue

        full_name = f"{first_name} {last_name}"

        work_emails = smart_email_generator(full_name, company_domain, max_results=30)
        print(f"   👤 {full_name} @ {company_domain}: {len(work_emails)} variations generated")

        valid_emails = []
        for email in work_emails:
            valid_emails.append(email)
            email_to_person_map[email.lower()] = person

        all_emails.extend(valid_emails)
        print(f"      ✅ {len(valid_emails)} emails added to batch")

    if not all_emails:
        print("\n❌ No valid emails to verify for non-US persons")
        return None

    sentinels = {}  # {sentinel_email_lower: domain}
    for domain in {p.get('c_website', '') for p in email_to_person_map.values() if p.get('c_website')}:
        probe = catchall_probe(domain)
        sentinels[probe.lower()] = domain
        all_emails.append(probe)

    gen_time = time.time() - start_time
    print(f"\n📊 Total non-US emails to verify: {len(all_emails)} ({len(sentinels)} catch-all probes)")
    print(f"   ⏱️  Generation time: {gen_time:.2f}s")

    return (persons, all_emails, email_to_person_map, gen_time, sentinels)


async def update_database_nonus(persons, results, email_to_person_map, sentinels=None):
    """Phase 3 (non-US): update sn71_person_nonus with verification results."""
    print(f"\n{'='*100}")
    print("💾 Processing results and updating non-US database...")
    await _apply_verification_results(
        persons, results, email_to_person_map, sentinels,
        sn71_db_person_nonus_update_email, sn71_db_failed_person_nonus_update_email)


async def process_us_once():
    """Run a single US email-check cycle: prepare → verify → update.

    Used as a fallback by the non-US loop when no non-US persons are available.
    Returns True if a US batch was processed (even if verification failed),
    False if there were no US persons to process either.
    """
    global in_progress_person_ids

    batch_data = await prepare_batch()
    if not batch_data:
        return False

    persons, all_emails, email_to_person_map, gen_time, sentinels = batch_data
    current_person_ids = {p['id'] for p in persons}
    in_progress_person_ids.update(current_person_ids)

    print("=" * 100)
    print("🔄 US BATCH (interleaved while non-US queue is empty) - verifying...")

    results = await verify_batch(all_emails, email_to_person_map)
    if not results:
        print("   ⚠️  Skipping US database update due to verification failure")
        return True  # work was attempted; leave persons tracked for cleanup

    await update_database(persons, results, email_to_person_map, sentinels)
    in_progress_person_ids.difference_update(current_person_ids)
    return True


async def main_e_check_nonus():
    """
    Pipelined email check workflow for non-US persons (sn71_person_nonus).

    Mirrors main_e_check() but reads/writes to the non-US tables:
      sn71_person_nonus  (persons)
      sn71_company_nonus (companies, joined for resp_score)

    When the non-US queue is empty, runs one US batch (process_us_once) and then
    retries non-US — so the worker never idles while US work remains.

    Supports graceful shutdown on Ctrl+C.
    """
    global in_progress_nonus_person_ids, in_progress_person_ids, shutdown_requested

    signal.signal(signal.SIGINT, signal_handler)

    batch_num = 0
    next_batch_task = None

    try:
        while True:
            if shutdown_requested:
                print(f"\n⚠️  Shutdown requested. Cancelling pending non-US batch preparation...")
                if next_batch_task:
                    next_batch_task.cancel()
                    try:
                        await next_batch_task
                    except asyncio.CancelledError:
                        pass
                break

            if next_batch_task:
                print(f"\n⏳ Waiting for non-US batch preparation to complete...")
                batch_data = await next_batch_task
                next_batch_task = None
            else:
                batch_data = await prepare_batch_nonus()

            if not batch_data:
                print(f"\n⏳ No non-US persons to process. Running one US batch, then retrying non-US...")
                processed_us = await process_us_once()
                if not processed_us:
                    print(f"⏳ No US persons either. Waiting 5 seconds before retry...")
                    await asyncio.sleep(5)
                continue

            batch_num += 1
            cycle_start = time.time()

            print("=" * 100)
            print(f"🔄 NON-US BATCH #{batch_num} - Starting email verification workflow...")

            persons, all_emails, email_to_person_map, gen_time, sentinels = batch_data

            current_person_ids = {p['id'] for p in persons}
            in_progress_nonus_person_ids.update(current_person_ids)

            print(f"\n{'='*100}")
            print(f"🚀 Starting NEXT non-US batch preparation in parallel...")
            next_batch_task = asyncio.create_task(prepare_batch_nonus())

            verify_start = time.time()
            results = await verify_batch(all_emails, email_to_person_map)
            verify_time = time.time() - verify_start

            if not results:
                print(f"   ⚠️  Skipping database update due to verification failure")
                continue

            await update_database_nonus(persons, results, email_to_person_map, sentinels)

            in_progress_nonus_person_ids.difference_update(current_person_ids)

            cycle_time = time.time() - cycle_start
            print(f"\n{'='*100}")
            print(f"✅ NON-US BATCH #{batch_num} completed!")
            print(f"   ⏱️  Generation time: {gen_time:.2f}s")
            print(f"   ⏱️  Verification time: {verify_time:.2f}s")
            print(f"   ⏱️  Total cycle time: {cycle_time:.2f}s (with parallel preparation)")
            print("=" * 100)

    except KeyboardInterrupt:
        print(f"\n⚠️  Keyboard interrupt detected during non-US processing...")
    except Exception as e:
        print(f"\n❌ Unexpected error in non-US echeck workflow: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n🛑 Shutting down non-US email check gracefully...")

        if next_batch_task and not next_batch_task.done():
            print(f"   🔄 Cancelling pending non-US batch preparation...")
            next_batch_task.cancel()
            try:
                await next_batch_task
            except asyncio.CancelledError:
                print(f"   ✅ Non-US batch preparation cancelled")

        reset_seen_for_uncompleted_nonus_persons(in_progress_nonus_person_ids)

        # Also release any US persons picked up by interleaved process_us_once()
        if in_progress_person_ids:
            reset_seen_for_uncompleted_persons(in_progress_person_ids)

        print(f"✅ Non-US shutdown complete. Goodbye!")

    return True


async def main_collect(process, start_year, end_year, start_revenue=0):
    """
    Collect company info from ContactOut.

    Outer loop : year  from start_year  to end_year  (step 1)
                 yearFoundedFrom = year, yearFoundedTo = year
    Inner loop : revenue band (revenueMin, revenueMax) starting at start_revenue
                 with step 100 each iteration.
                 Stops iterating revenue when a band returns 0 companies
                 (then moves to the next year).
    Each revenue+year combo is paginated through all available pages.
    """
    REVENUE_STEP = 100

    total_processed = 0
    total_success = 0
    total_skipped = 0

    for year in range(start_year, end_year + 1):
        print(f"\n{'#'*100}")
        print(f"📅 Processing year: {year}")
        print(f"{'#'*100}")

        rev_min = start_revenue
        year_revenue_processed = 0
        retry_count = 0

        while True:
            rev_max = rev_min + REVENUE_STEP

            print(f"\n{'='*100}")
            print(f"💰 Revenue band: {rev_min} - {rev_max}  |  Year: {year}")

            current_page = 1
            processed_count = 0
            skipped_count = 0
            success_count = 0
            found_any = False  # Track whether page-1 had any results

            while True:
                print(f"\n  🔍 Searching page {current_page} (year={year}, rev={rev_min}-{rev_max})...")
                success, companies, meta = search_companies_from_contactout(
                    "United States", process,
                    page=current_page,
                    revenue_min=rev_min,
                    revenue_max=rev_max,
                    year_from=str(year),
                    year_to=str(year)
                )

                if not success or not companies:
                    print(f"  ⚠️  No companies on page {current_page} — stopping pagination for this band")
                    break
                
                last_page = meta.get('last_page', 1)
                print(f"  🎫🎫🎫  Found {len(companies)} companies on page {current_page} (last page: {last_page})")
                print(f"🎨🎨🎨🎨🎨 {last_page}")
                if last_page > 400:
                    print(f"  ⚠️⚠️⚠️⚠️⚠️  Last page {last_page} exceeds limit, capping at 400 to avoid excessive pagination")
                    last_page = 400
                found_any = True

                for company in companies:
                    try:
                        print(f"\n    Processing company: {company.get('companyName', 'Unknown')} ({company.get('domain', 'No domain')})")
                        # website = company.get("domain", "")

                        # if (check_company_exists(website)):
                        #     print(f"   🍁 🍁 🍁  Company already exists in database, skipping: {website}")
                        #     skipped_count += 1
                        #     time.sleep(0.5)
                        #     continue

                        # ret, reason = await vali_check_company_base(website)
                        # if ret:
                        #     print (f"✅ {website} - company base check success")
                        # else:
                        #     print (f"❌ {website} - company base check failed - reason: {reason}")
                        #     continue

                        result = process_search_company_from_contactout(company)
                        processed_count += 1

                        if result:
                            success_count += 1
                        else:
                            skipped_count += 1

                        # Rate limiting between companies
                        

                    except KeyboardInterrupt:
                        print("\n\n⚠️  Interrupted by user")
                        raise
                    except Exception as e:
                        print(f"    ❌ Error processing {company.get('companyName', 'Unknown')}: {e}")
                        processed_count += 1
                        skipped_count += 1
                        continue
                time.sleep(random.uniform(5.0, 10.0))
                # Pagination check
                if current_page >= last_page:
                    print(f"  ✅ Reached last page ({last_page}) for band {rev_min}-{rev_max}")
                    break

                current_page += 1

            # Band summary
            print(f"\n  📊 Band {rev_min}-{rev_max} | year {year}: "
                  f"processed={processed_count}, added={success_count}, skipped={skipped_count}")
            total_processed += processed_count
            total_success += success_count
            total_skipped += skipped_count
            year_revenue_processed += processed_count

            if not found_any:
                retry_count += 1
                if retry_count >= 3:
                    # This revenue band had no companies → stop revenue loop for this year
                    print(f"  🔚 Revenue band {rev_min}-{rev_max} returned no companies — "
                        f"moving to next year")
                    break
            elif found_any:
                retry_count = 0  

            # Advance to next revenue band
            rev_min = rev_max

        print(f"\n📅 Year {year} complete: {year_revenue_processed} companies processed")

    print(f"\n{'#'*100}")
    print(f"✅ Collection Complete!  (years {start_year}-{end_year})")
    print(f"   Total Processed: {total_processed}")
    print(f"   Successfully Added: {total_success}")
    print(f"   Skipped (Existing/No Contacts): {total_skipped}")
    print(f"{'#'*100}\n")
    while True:
        call_contactout_template(process)
        time.sleep(600)
    return True

if __name__ == "__main__":
    print (f"{__name__} is called.")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", required=True, choices=["company", "person", "echeck", "echeck_nonus", "collect"], help="Type of process to run")
    parser.add_argument("--process")  # NOT required here
    parser.add_argument("--start_year", type=int, help="Year founded: start of range (required for collect)")
    parser.add_argument("--end_year",   type=int, help="Year founded: end of range   (required for collect)")
    parser.add_argument("--start_revenue", type=int, default=0,
                        help="Revenue loop starting value in millions (default: 0, used only for collect)")

    args = parser.parse_args()

    print("Type:", args.type)
    print("Process:", args.process)

    # logic rules
    if args.type in ("company", "person", "collect"):
        if not args.process:
            parser.error("--process is required when --type is company, person, or collect")

    if args.type == "collect":
        if args.start_year is None or args.end_year is None:
            parser.error("--start_year and --end_year are required when --type is collect")
        if args.start_year > args.end_year:
            parser.error("--start_year must be <= --end_year")

    if args.type == "company":
        asyncio.run(main_company(args.process))

    elif args.type == "person":
        asyncio.run(main_person(args.process))

    elif args.type == "echeck":
        asyncio.run(main_e_check())  # or just main_e_check()
    elif args.type == "echeck_nonus":
        asyncio.run(main_e_check_nonus())
    elif args.type == "collect":
        asyncio.run(main_collect(args.process, args.start_year, args.end_year, args.start_revenue))